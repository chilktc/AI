# Stories 수신 인프라 + TIER 4 대기 메커니즘 설계

**날짜:** 2026-04-14  
**상태:** 승인됨  
**관련 Plan:** Plan #34 (Stories 수신 인프라 확장)

---

## 1. 목적

Script Personalizer(TIER 4)가 실행되기 전, 백엔드로부터 Stories 데이터(사용자가 선택한 키워드/제목/설명)를 수신하여 개인화 로직에 반영한다.

Stories 데이터는 백엔드가 사용자 입력 완료 후 **반드시** 전송한다. 데이터가 도착하지 않는 경우는:
1. 사용자가 아직 입력 중 → 대기 (정상)
2. 백엔드 에러 → 감지 불가, 5분 타임아웃 후 에러 반환

---

## 2. 전체 흐름

```
[Backend] POST /api/stories/select
    │  { session_id, keywords, title, description }
    ▼
StoriesStore.set_stories(session_id, data) → asyncio.Event.set()

─────────────── 동시 진행 ───────────────
[AI Pipeline]
TIER 0 → TIER 1 → TIER 2 → TIER 3
                                │
                                ▼
                   wait_for_stories_node
                   Event.wait(timeout=300s)  ← settings 기반
                        │              │
                   데이터 도착       5분 초과
                        │              │
                        ▼              ▼
                 script_personalizer  에러 반환
                 (TIER 4)             (next_step: "stories_timeout")
                        │
                        ▼
                 StoriesStore.delete_session(session_id)
```

**핵심 설계 원칙:**
- TIER 1~3은 Stories 데이터와 무관하게 정상 진행
- 대기는 TIER 3 완료 후 TIER 4 진입 직전에만 발생
- Stories 데이터가 TIER 4 진입 전에 도착해도 즉시 통과 (Event 이미 set 상태)
- asyncio.Event 패턴은 기존 CRISIS 취소 메커니즘과 동일

---

## 3. 데이터 스키마

### POST /api/stories/select 요청

```python
class StoriesSelectRequest(BaseModel):
    session_id: str
    keywords: list[str]
    title: str
    description: str
```

### AgentState 신규 필드

```python
# src/models/agent_state.py (Protected — 3인 합의 필요)
stories_context: dict | None
# 형태:
# {
#     "keywords": ["직장", "갈등", ...],
#     "title": "...",
#     "description": "..."
# }
```

---

## 4. 컴포넌트 상세

### 4-1. `src/api/stories_store.py` (신규)

```python
# asyncio.Event per session_id 관리
# get-or-create 패턴으로 도착 순서 무관하게 동작

class StoriesStore:
    _store: dict[str, {"event": asyncio.Event, "data": dict | None}]

    def set_stories(session_id: str, data: dict) -> None:
        """POST 수신 시 호출. 데이터 저장 + Event.set()"""
        # get-or-create: stories가 먼저 도착해도 안전
        if session_id not in _store:
            _store[session_id] = {"event": asyncio.Event(), "data": None}
        _store[session_id]["data"] = data
        _store[session_id]["event"].set()

    async def wait_for_stories(session_id: str, timeout: float) -> dict | None:
        """TIER 4 노드에서 호출. 타임아웃 시 None 반환"""
        if session_id not in _store:
            _store[session_id] = {"event": asyncio.Event(), "data": None}
        entry = _store[session_id]
        try:
            await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
            return entry["data"]
        except asyncio.TimeoutError:
            return None

    def delete_session(session_id: str) -> None:
        """파이프라인 완료 후 호출. 메모리 누수 방지"""
        _store.pop(session_id, None)
```

### 4-2. `src/api/routes/stories.py` (신규)

```
POST /api/stories/select
  - StoriesStore.set_stories(session_id, data) 호출
  - 200 OK 반환
  - 존재하지 않는 session_id: 404
  - 잘못된 페이로드: 422 (Pydantic 자동)
```

### 4-3. `src/graph/workflow.py` (Protected — 수정)

```python
async def wait_for_stories_node(state: AgentState) -> dict[str, Any]:
    """TIER 3 완료 후 TIER 4 진입 전 Stories 데이터 대기."""
    session_id = state["session_id"]
    timeout = get_settings().stories.wait_timeout_seconds  # 기본 300

    data = await stories_store.wait_for_stories(session_id, timeout)
    stories_store.delete_session(session_id)

    if data is None:
        return {"next_step": "stories_timeout"}

    return {"stories_context": data}

# 노드 흐름 변경:
# 기존: batch_validator → script_personalizer
# 변경: batch_validator → wait_for_stories → script_personalizer
#                                  └→ (stories_timeout) → error_node
```

### 4-4. `config/settings.yaml` (수정)

```yaml
stories:
  wait_timeout_seconds: 300  # 5분
```

---

## 5. 에러 처리

| 상황 | 처리 |
|------|------|
| 정상 수신 (TIER 4 전) | Event 이미 set → wait_for_stories 즉시 반환, 파이프라인 계속 |
| 정상 수신 (TIER 4 대기 중) | Event.set() → wait 해제, 파이프라인 계속 |
| 5분 타임아웃 | `stories_context: None`, `next_step: "stories_timeout"` → 파이프라인 종료 |
| 잘못된 페이로드 | 422 자동 반환, Event 미설정 → 대기 유지 |
| 존재하지 않는 session_id | 404 반환 |
| 백엔드 에러 | POST 미도착 → 5분 후 타임아웃으로 처리 (감지 불가, 허용된 한계) |

---

## 6. 수정/제거 파일 목록

| 파일 | 작업 | Protected |
|------|------|-----------|
| `src/api/stories_store.py` | **신규 생성** | — |
| `src/api/routes/stories.py` | **신규 생성** | — |
| `src/models/agent_state.py` | `stories_context: dict \| None` 필드 추가 | ✅ 3인 합의 |
| `src/graph/workflow.py` | `wait_for_stories_node` 추가, 라우팅 수정 | ✅ 3인 합의 |
| `config/settings.yaml` | `stories.wait_timeout_seconds: 300` 추가 | — |
| `src/api/routes/sessions.py` | 스텁 코드 제거 (아래 참조) | — |

### sessions.py 제거 대상

기존 `/{session_id}/personalization-context` 스텁이 신규 구현으로 대체된다:

- `_personalization_context_store` 변수 (30번째 줄)
- `PersonalizationContextRequest` 클래스 (33~39번째 줄)
- `receive_personalization_context()` 엔드포인트 (91~118번째 줄)

제거 후 `sessions.py`는 세션 생성/종료 기능만 유지.

---

## 7. 기존 코드와의 관계

| 기존 (스텁) | 신규 |
|------------|------|
| `_personalization_context_store` | `StoriesStore` (asyncio.Event 포함) |
| `POST /sessions/{id}/personalization-context` | `POST /api/stories/select` |
| 파이프라인 연결 없음 (TODO) | `wait_for_stories_node`로 TIER 4 연결 |
| `PersonalizationContextRequest` | `StoriesSelectRequest` |

---

## 8. 미결 사항

- `src/api/main.py` 또는 라우터 등록 파일에 `stories` 라우터 추가 필요 (구현 시 확인)
- Script Personalizer 내부에서 `stories_context` 활용 로직은 별도 구현 (개발자1 담당)

---

*작성: 2026-04-14 — Stories 수신 인프라 + TIER 4 대기 메커니즘 설계*

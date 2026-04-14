# Plan #34: stories 데이터 수신 인프라 점검 및 수정

**상태**: ⛔ Plan #35로 대체 (PR #110 구현 완료)
**마지막 업데이트**: 2026-04-14 14:30

## Context

백엔드가 `POST http://10.7.11.10:8000/api/stories/select`로 AI 서버에 stories 데이터를 **푸시**한다.
요청 본문: `session_id(str)`, `keywords(list[str])`, `title(str)`, `description(str)`.

데이터는 DB에 별도 저장하지 않고 받은 그대로 활용한다.

### 타이밍

```
TIER 0-1 실행 (로딩1)
  ↓
TIER 1 완료 → Content Analyzer가 백엔드에 keywords/description 전송
  ↓
백엔드가 POST /api/stories/select 호출 ← 데이터 도착 (로딩1 완료 후)
  ↓
TIER 2 시작 (로딩2)
```

LangGraph는 연속 실행이므로, 수신 데이터를 실행 중 파이프라인에 전달하려면 **in-memory 임시 보관**이 필요하다 (DB 저장 아님).

---

## 현황

| 항목 | 상태 | 비고 |
|------|------|------|
| `POST /api/stories/select` | **미존재** | 백엔드 호출 경로에 대응하는 엔드포인트 없음 |
| `client.py:load_stories()` (309-354행) | 방향 반대 | AI→백엔드 GET. 호출처 없는 죽은 코드 |
| `sessions.py:receive_personalization_context()` | 동일 스키마, 다른 경로 | 경로: `/api/sessions/{id}/personalization-context`. 스키마(session_id, keywords, title, description)와 in-memory store 패턴은 동일 |
| Episode Memory | 무관 | Pinecone 벡터 검색 전용. stories 데이터와 직접 관련 없음 |
| 활용 에이전트 | **미정** | 어느 에이전트에서 읽을지, AgentState 필드 주입 여부 모두 미결정 |

---

## 수정 계획

### Task 1: `POST /api/stories/select` 수신 엔드포인트 생성
**파일**: `src/api/routes/stories.py` (신규)

백엔드가 호출하는 수신 엔드포인트. 데이터를 in-memory store에 session_id 키로 보관.

```python
router = APIRouter()
_stories_store: dict[str, dict[str, Any]] = {}

class StoriesSelectRequest(BaseModel):
    session_id: str
    keywords: list[str]
    title: str
    description: str

@router.post("/select")
async def receive_stories(request: StoriesSelectRequest) -> dict:
    _stories_store[request.session_id] = request.model_dump()
    return {"success": True}

def get_stories_context(session_id: str) -> dict[str, Any] | None:
    """session_id로 stories 데이터를 조회한다 (1회 소비, pop)."""
    return _stories_store.pop(session_id, None)
```

### Task 2: 라우터 등록
**파일**: `src/api/routes/__init__.py` — stories import 추가
**파일**: `src/api/main.py` (200행 부근)

```python
from src.api.routes import stories
app.include_router(stories.router, prefix="/api/stories", tags=["Stories"])
```
→ 결과 경로: `POST /api/stories/select`

### Task 3: `load_stories()` 삭제
**파일**: `src/api/client.py` (309-354행)

방향이 반대(AI→백엔드 GET)인 죽은 코드. 호출처 없음 확인 완료. 삭제한다.

### Task 4: `sessions.py` personalization-context 정리
**파일**: `src/api/routes/sessions.py`

`PersonalizationContextRequest`, `_personalization_context_store`, `receive_personalization_context()` 제거.
동일 스키마·동일 목적이 `POST /api/stories/select`로 이동했으므로 중복 코드 삭제.

### Task 5: 테스트
**파일**: `tests/api/test_stories.py` (신규)

- `POST /api/stories/select` 정상 수신 → 200 + store 저장 검증
- `get_stories_context()` → 데이터 반환 + 소비(pop) 검증
- 존재하지 않는 session_id → None 반환
- 필수 필드 누락 → 422 검증

---

## 미결정 사항 (이번 작업 범위 외)

- **활용 에이전트**: 어떤 에이전트가 `get_stories_context()`를 호출할지 미정
- **AgentState 주입**: `personalization_context` 필드 추가 여부 미정
- **파이프라인 주입 시점**: TIER 2 진입 전 주입 vs 개별 에이전트 내부 조회 미정

→ 이번 작업은 **수신 인프라(엔드포인트 + store + 접근 함수)**만 구현. 활용 로직은 결정 후 별도 작업.

---

## 수정 대상 파일

| 파일 | 변경 유형 |
|------|----------|
| `src/api/routes/stories.py` | **신규** — 수신 엔드포인트 + store + 접근 함수 |
| `src/api/routes/__init__.py` | stories import 추가 |
| `src/api/main.py` | 라우터 등록 1줄 |
| `src/api/client.py` | `load_stories()` 삭제 (46행) |
| `src/api/routes/sessions.py` | personalization-context 관련 코드 제거 |
| `tests/api/test_stories.py` | **신규** — 테스트 4건 |

---

## 검증

```bash
pytest tests/api/test_stories.py -v
pytest tests/ -v
grep -r "load_stories" src/
grep -r "personalization_context_store" src/
```

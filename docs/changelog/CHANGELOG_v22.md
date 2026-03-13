# 변경이력 v22

> 날짜: 2026-03-11

---

## v22: 팟캐스트 데이터 저장 + 에이전트 데이터 전달 유틸리티 + 문서 갱신

### 배경

v21에서 저장소 추상화(Zone C + Zone D)를 구현한 후, 팟캐스트 에피소드 생성 시
데이터가 프론트엔드 응답에만 포함되고 **백엔드 DB에 저장되지 않는 문제**를 해결한다.
또한 개별 에이전트가 파이프라인 실행 중 결과를 백엔드에 전달할 수 있는
**공통 유틸리티(AgentDataPublisher)**를 구현한다.

1. **팟캐스트 데이터 저장**: `BackgroundTasks`로 에피소드 메타+세그먼트, 감정 로그, 시각화 메타를 비동기 3단계 저장
2. **AgentDataPublisher**: 에이전트 내 SaveRequest 보일러플레이트를 캡슐화하는 공통 유틸리티
3. **API_SPEC.md 갱신**: 대화모드 API 제거 + 팟캐스트 스키마를 실제 구현(external_schemas.py)과 일치
4. **PROJECT_STRUCTURE.md 갱신**: src/api/ 트리를 실제 파일 시스템과 일치

**원칙**: Protected 파일(agent_state.py, message.py, contracts.py, workflow.py) 수정 없음.
Shared Infrastructure(base_agent.py, llm_client.py, prompt_loader.py, loader.py) 기존 시그니처 변경 없음.

---

### 신규 파일 (2개)

| 파일 | 내용 |
|------|------|
| `src/api/publisher.py` | AgentDataPublisher — 에이전트 데이터 전달 공통 유틸리티 |
| `tests/api/test_publisher.py` | AgentDataPublisher 단위 테스트 (12개 케이스) |

### 수정 파일 (2개)

| 파일 | 변경 내용 |
|------|----------|
| `src/api/routes/podcasts.py` | `_save_episode_bundle()` + BackgroundTasks 비동기 저장 추가 (이전 버전에서 구현) |
| `src/api/backend_resources.py` | `RESOURCE_PODCAST_EPISODE` 상수 확정 |

### 문서 갱신 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `docs/architecture/API_SPEC.md` | v1.0→v1.1. 대화모드 API(섹션 1,2,4) 제거. 팟캐스트 스키마를 external_schemas.py 기준으로 갱신. 에러 응답 구조 변경(ErrorResponse) |
| `docs/architecture/PROJECT_STRUCTURE.md` | src/api/ 트리: 3파일→8파일+routes/. tests/api/ 트리 추가. 설명 섹션 갱신 |
| `docs/changelog/INDEX.md` | v22 행 추가 |
| `docs/INDEX.md` | v22 행 추가 |

---

### 주요 아키텍처

#### 팟캐스트 데이터 저장 흐름

```
POST /api/v1/podcasts/episodes
    │
    ├── 1. LangGraph 파이프라인 실행 (TIER 0→1→2→3→4)
    │       └── final_state 반환
    │
    ├── 2. 응답 데이터 구성
    │       ├── _build_episode_data(final_state) → PodcastEpisodeData
    │       ├── _extract_emotion(final_state)    → EmotionSummary | None
    │       └── _extract_safety_alert(final_state) → SafetyAlertData | None
    │
    ├── 3. HTTP 응답 반환 (PodcastEpisodeResponse)
    │       └── 프론트엔드에 즉시 전달
    │
    └── 4. BackgroundTasks 비동기 저장 (_save_episode_bundle)
            ├── (1) 에피소드 메타 + 세그먼트 → RESOURCE_PODCAST_EPISODE
            ├── (2) 감정 로그              → RESOURCE_EMOTION_LOG (emotion 있을 때만)
            └── (3) 시각화 메타            → RESOURCE_VISUALIZATION (visual_data 있을 때만)

            각 단계는 독립적 try/except로 감싸져 있어
            하나가 실패해도 다른 저장은 계속 진행됨
```

#### AgentDataPublisher 구조

```
AgentDataPublisher
    │
    ├── __init__(client=None)
    │       └── mock 주입 가능 (테스트 시)
    │
    ├── _get_client()
    │       └── lazy import: from src.api.main import backend_client
    │           (podcasts.py의 _save_episode_bundle과 동일 패턴)
    │
    └── publish(resource, data, user_id, session_id, ...)
            │
            ├── SaveRequest 생성 (user_id, session_id, type, data, timestamp)
            ├── await client.save(resource, request)
            │       └── @with_retry(3회) 자동 재시도 (BackendClient 내장)
            │
            ├── 성공 → logger.info + return True
            └── 실패 → logger.warning + return False (예외 미전파)
```

에이전트에서의 활용 (향후 적용):
```python
# 에이전트의 process() 메서드 내에서 호출
publisher = AgentDataPublisher()
await publisher.publish(
    resource=RESOURCE_EMOTION_LOG,
    data=emotion_vectors,
    user_id=state.get("user_id", ""),
    session_id=state.get("session_id", ""),
)
return {"emotion_vectors": emotion_vectors}  # 기존 return 그대로
```

파이프라인 내 동작 근거:
- 모든 에이전트의 process()가 async 함수이므로 await 호출 가능
- TIER 1 병렬 Fan-out에서 각 에이전트가 독립 코루틴이므로 안전
- publish() 실패 시 False 반환하고 에이전트 return에 영향 없음
- workflow.py(Protected) 수정 불필요 — 에이전트 내부 변경만

#### API_SPEC.md 주요 변경

```
v1.0 → v1.1 변경 요약:

삭제:
  - 섹션 1: 대화 요청 (POST /api/v1/conversations)
  - 섹션 2: 대화 스트리밍 SSE (GET /api/v1/conversations/stream)
  - 섹션 4: 대화 히스토리 조회 (GET /api/v1/history/conversations)
  - 카테고리 표의 Conversation 행

변경:
  - Request: mode 필드 제거, user_input → topic + description, preferences 갱신, tracing 추가
  - Response: code/message/data 래퍼 → 평탄 구조 (success + episode + emotion + ...)
  - segments[].segment_type: intro/body/reflection/closing → opening/education/practical/closing
  - emotion: primary_emotion_kr, secondary_emotions, tone_recommendation 추가
  - Error: ErrorResponse 구조 (success=false + error.code/message/field + tracing)
  - 에피소드 목록: duration_sec → total_duration_minutes
  - 감정 추이: mode, episode_id 추가
  - 공통 에러: INVALID_MODE 제거, PIPELINE_ERROR → PIPELINE_TIMEOUT
```

---

### 검증 결과

```
$ python3 -m pytest tests/api/test_publisher.py -v
12 passed in 0.45s

$ python3 -c "from src.api.publisher import AgentDataPublisher"
(성공 — import 오류 없음)
```

---

*Production 코드 변경: publisher.py 1개 추가 | Protected 파일 수정: 없음*

*마지막 업데이트: 2026-03-11*

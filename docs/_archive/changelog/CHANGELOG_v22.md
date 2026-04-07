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

---

## 팀 기여 (Team Contributions)

> 같은 기간 다른 개발자가 머지한 PR. 해당 버전 시점에 코드베이스에 반영된 변경사항.

### PR #18 — Zone A API 코어 구현 (개발자1, Jun)

- **머지**: 2026-03-10 | **브랜치**: `jun_Zone_A`
- **규모**: +460 / -0 (6개 파일, 전량 신규)

| 파일 | 변경 |
|------|------|
| `src/api/main.py` | 신규: FastAPI 앱 엔트리포인트 — 라우터 등록, CORS, 미들웨어 설정 (137줄) |
| `src/api/routes/__init__.py` | 신규: 라우터 패키지 초기화 (9줄) |
| `src/api/routes/health.py` | 신규: 헬스체크 엔드포인트 — `GET /health`, `GET /ready` (57줄) |
| `src/api/routes/podcasts.py` | 신규: 팟캐스트 엔드포인트 — 에피소드 생성/조회 (179줄) |
| `src/api/routes/sessions.py` | 신규: 세션 관리 엔드포인트 (72줄) |
| `config/loader.py` | 수정: API 관련 설정 프로퍼티 추가 (+6줄) |

---

### PR #19 — Docker/CI 인프라 + 프롬프트 YAML + 테스트 도구 (개발자2, 한가은)

- **머지**: 2026-03-10 | **브랜치**: `feature/agents-gaeun`
- **규모**: +350 / -3 (18개 파일)

#### 인프라 (3개)

| 파일 | 변경 |
|------|------|
| `.dockerignore` | 신규: Docker 빌드 제외 목록 (27줄) |
| `docker-compose.yml` | 신규: AI 서버 컨테이너 구성 (27줄) |
| `config/settings.production.yaml` | 신규: 프로덕션 환경 설정 (13줄) |

#### 프롬프트 YAML (4개)

| 파일 | 변경 |
|------|------|
| `prompts/podcast/content_analyzer.yaml` | 신규: Content Analyzer 프롬프트 (33줄) |
| `prompts/podcast/podcast_reasoning.yaml` | 신규: Podcast Reasoning 프롬프트 (34줄) |
| `prompts/podcast/safety.yaml` | 신규: Safety Agent 프롬프트 (33줄) |
| `prompts/podcast/visualization.yaml` | 신규: Visualization Agent 프롬프트 (33줄) |

#### 수정 파일 (2개)

| 파일 | 변경 |
|------|------|
| `config/loader.py` | 수정: 프로덕션 설정 로딩 분기 추가 (+26줄) |
| `.env.example` | 수정: 환경변수 예시 확장 (+20줄) |

#### 개발/테스트 도구 (3개)

| 파일 | 변경 |
|------|------|
| `run_mem_test.py` | 신규: Memory Agent 테스트 스크립트 (57줄) |
| `run_vis_test.py` | 신규: Visualization Agent 테스트 스크립트 (28줄) |
| `mock_memory.json` | 신규: 테스트용 Mock 메모리 데이터 (22줄) |

#### 이미지 파일 (6개)

| 파일 | 변경 |
|------|------|
| `dev/live_tests/images/*.png` (6개) | Visualization Agent 테스트 결과 이미지 (~8MB 총합) |

---

### PR #20 — Episode Memory 확장 + base_memory 리팩토링 + CI (개발자2, 한가은)

- **머지**: 2026-03-11 | **브랜치**: `feature/agents-gaeun`
- **규모**: +324 / -100 (7개 파일)

| 파일 | 변경 |
|------|------|
| `src/agents/podcast/episode_memory.py` | 수정: Episode Memory Agent 대규모 확장 (+127줄) — 에피소드 검색/저장 로직 구현 |
| `src/agents/shared/base_memory.py` | 리팩토링: Memory 베이스 클래스 재구성 (+132 / -122줄) |
| `.github/workflows/ci.yml` | 수정: CI 파이프라인 설정 추가 (+10줄) |
| `mock_db.json` | 신규: 테스트용 Mock DB 데이터 (44줄) |
| `test_kt_memory.py` | 신규: Memory 통합 테스트 (35줄) |
| `test_memory_final.py` | 신규: Memory 최종 검증 테스트 (53줄) |
| `test_save_memory.py` | 신규: Memory 저장 테스트 (23줄) |

---

*마지막 업데이트: 2026-03-16*

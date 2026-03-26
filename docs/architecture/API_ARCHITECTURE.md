# API 아키텍처 — 서버 구조 & 파이프라인 실행 흐름

> [API_SPEC.md](API_SPEC.md) 문서 모음의 일부 (v2.0)

---

## 인증 방식

> **TODO(backend)**: AI ↔ Backend 서버 간 인증/인가 방식 협의 필요
> - 옵션 A: Service-to-service 토큰 (Authorization: Bearer {service_token})
> - 옵션 B: API Key 헤더 (X-API-Key)
> - 옵션 C: 내부 네트워크 신뢰 (인증 없음)

Base Url : (배포 후 확정)

## Swagger 경로

1. mind-log : (배포 후 확정)

### 미들웨어

| 순서 | 미들웨어 | 역할 |
|------|---------|------|
| 1 | CORSMiddleware | CORS 허용 (ALLOWED_ORIGINS) |
| 2 | RequestLoggingMiddleware | HTTP 요청/응답 구조화 로깅 (`X-Request-ID` 자동 부여) |

- `/health`, `/health/ready`, `/metrics` 경로는 로깅에서 제외

**관련 파일**: `src/api/middleware.py`

---

## 아키텍처 흐름

> API_FLOW.md에서 통합 (v1.2)

### 서버 시작 (Phase 0: Startup)

```
main.py lifespan 시작
    │
    ├── 1) compile_graph("unified")  →  LangGraph StateGraph 컴파일
    │       └─ 결과: compiled_graph (전역 변수)
    │
    ├── 2) BackendClient()  →  httpx.AsyncClient 기반 HTTP 클라이언트 초기화
    │       └─ 설정: base_url=BACKEND_API_URL(환경변수), timeout=api.timeout(config)
    │       └─ 결과: backend_client (전역 변수)
    │
    └── 라우터 등록:
        ├── health.router       →  /health, /health/ready (태그: "Health Check")
        ├── sessions.router     →  /api/v1/sessions (prefix)
        ├── podcasts.router     →  /api/v1/podcasts (prefix)
        └── get_metrics_router() → /metrics (Prometheus)
```

**관련 파일**: `src/api/main.py`

### 세션 생성 (Phase 1)

```
Backend 서버
    │
    ▼ POST /api/v1/sessions
AI 서버 (sessions.py::create_session)
    │
    ├── 1) sess_{uuid.hex[:12]} 생성
    ├── 2) 모드 확인 (podcast)
    │
    ▼ Response → SessionCreateResponse { session_id, mode, created_at }
Backend 서버
```

### 팟캐스트 에피소드 생성 (Phase 2: Pipeline Execution)

#### HTTP 요청 수신

```
Backend 서버
    │
    ▼ POST /api/v1/podcasts/episodes
AI 서버 (podcasts.py::create_podcast_episode)
    │
    ├── PodcastRequest 수신 (user_id, session_id, topic, description, preferences, tracing)
    ├── AgentState 초기화: { user_input, user_id, session_id, mode: "podcast" }
    └── TelemetryCallback 생성 (메트릭 수집용)
```

#### LangGraph 파이프라인 실행

```
compiled_graph.ainvoke(initial_state)
    │
    TIER 0: Intent Classifier
    │   의도 분류 + complexity_score + risk_flag
    │
    TIER 1 (병렬 Fan-out):
    ├── Safety Agent ──── CRISIS 시 → 전체 취소 → 즉시 응답
    ├── Emotion Agent
    ├── Content Analyzer
    └── Podcast Reasoning
    │       ├── Episode Memory ← 조건부 호출
    │       └── Knowledge Agent ← 조건부 호출
    │
    ↓ (Fan-in)
    │
    TIER 2 (병렬):
    ├── Script Generator
    └── Visualization (커버 이미지)
    │
    TIER 3: Batch Validator
    │   품질 검증 (실패 시 TIER 2 재시도, 최대 2회)
    │
    TIER 4: Script Personalizer
    │   톤/스타일 조정 + Safety 경고 톤
    │
    ▼ final_state (AgentState)
```

#### 중간 데이터 전달 (AgentDataPublisher)

TIER 1 병렬 실행 중, 일부 에이전트가 **파이프라인 완료를 기다리지 않고** 즉시 Backend 서버에 데이터를 전달합니다.

```
[TIER 1 실행 중]
    │
    ├── EmotionAgent.process()
    │       └── AgentDataPublisher.publish()
    │              └── BackendClient.save(RESOURCE_EMOTION_LOG, SaveRequest)
    │                     └── POST /api/v1/emotion_logs → Backend 서버
    │
    └── ContentAnalyzerAgent.process()
            └── AgentDataPublisher.publish()
                   └── BackendClient.save(RESOURCE_CONTENT_ANALYSIS, SaveRequest)
                          └── POST /api/v1/content_analyses → Backend 서버
```

**관련 파일**: `src/api/publisher.py` → `AgentDataPublisher`

#### 응답 구성

```
final_state
    │
    ├── _build_episode_data()   → PodcastEpisodeData (segments, key_insights, themes)
    ├── _extract_safety_alert() → SafetyAlertData | None  (warning/crisis 시)
    │
    ▼ SlimPodcastResponse 조립 (최소 응답)
    │
    ├── episode_id:   str (에피소드 고유 ID)
    ├── session_id:   str (세션 ID)
    ├── safety_alert: SafetyAlertData | None
    └── tracing:      RequestTracing
```

> **참고**: 이전 버전의 `PodcastEpisodeResponse`는 episode, emotion, cover_image, metadata를 모두 포함했으나,
> v25(2026-03-16)에서 `SlimPodcastResponse`로 교체됨. 상세 데이터는 Backend GET API로 조회.

#### 동기 저장

HTTP 응답 반환 **전** `_save_core_data()`에서 핵심 데이터를 DB에 동기 저장합니다.
감정 로그는 Emotion Agent가 TIER 1에서 `AgentDataPublisher`로 이미 저장하므로 여기서는 제외합니다.

```
[파이프라인 완료 후, 응답 반환 전]
    │
    ▼ await _save_core_data()
    │
    ├── (1) 에피소드 메타 + 세그먼트
    │       └── BackendClient.save(RESOURCE_PODCAST_EPISODE, SaveRequest)
    │              └── POST /api/v1/podcast_episodes → Backend 서버
    │
    └── (2) 시각화 메타 (visual_data 존재 시)
            └── BackendClient.save(RESOURCE_VISUALIZATION, SaveRequest)
                   └── POST /api/v1/visualizations → Backend 서버
```

**관련 파일**: `src/api/routes/podcasts.py` → `_save_core_data()`

### 전체 타임라인

```
시간 ──────────────────────────────────────────────────────────▶

[요청 수신]──[TIER 0]──[TIER 1 병렬]──[TIER 2 병렬]──[TIER 3]──[TIER 4]──[동기 저장]──[응답 반환]
                           │            │                                      │
                     AgentDataPublisher  │                              _save_core_data()
                     (즉시 전달)         │                              (응답 전 저장)
                           │            │                                      │
                           ▼            ▼                                      ▼
                     Backend 서버    Script Generator                    Backend 서버
                    (emotion_log,   + Visualization 병렬              (podcast_episodes,
                     content_analysis)                                  visualizations)
```

### 세션 종료 (Phase 3)

```
Backend 서버
    │
    ▼ POST /api/v1/sessions/{session_id}/close
AI 서버 (sessions.py::close_session)
    │
    ├── SessionCloseRequest 수신 (user_id, session_id, feedback)
    ├── Learning Agent 비동기 트리거 (현재 비활성)
    │
    ▼ Response → { success: true, message: "Session ... closed successfully" }
Backend 서버
```

### 예외 처리

모든 예외는 `ErrorResponse` 스키마로 통합 처리됩니다.

| 예외 | 핸들러 | HTTP Status | 에러 코드 |
|------|--------|------------|----------|
| `StarletteHTTPException` | `http_exception_handler` | 원본 코드 유지 | `NOT_FOUND`, `RATE_LIMITED`, `SERVER_ERROR` |
| `RequestValidationError` | `validation_exception_handler` | 422 | `VALIDATION_ERROR` |
| `Exception` (미처리) | `general_exception_handler` | 500 | `SERVER_ERROR` |

**관련 파일**: `src/api/main.py`

---

*[← API_SPEC.md (인덱스)](API_SPEC.md) · [수신 API →](API_ENDPOINTS_RECEIVING.md)*

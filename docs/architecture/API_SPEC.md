# Mind-Log API 기능 명세서

> **작성일**: 2026-03-03
> **버전**: v1.2
> **갱신일**: 2026-03-13
> **상태**: 팟캐스트모드 구현 완료 (대화모드 API는 향후 구현 시 추가 예정)

---

## 서버 구분

Mind-Log는 두 개의 독립 서버로 구성됩니다.

| 서버 | 프레임워크 | 포트 | 역할 |
|------|-----------|------|------|
| **AI 서버** | FastAPI + Uvicorn | 8000 | LLM 파이프라인 실행, Backend 서버 전용 API |
| **Backend 서버** | Spring Boot | 8080 | 데이터 영속화 (MySQL), 조회, 프론트엔드 API 제공 |

```
통신 흐름:
  Frontend (app-4:3000) → Backend 서버 (app-3:8080) ↔ AI 서버 (app-2:8000)
                                      ↓                        ↕
                                     DB                  AWS (배포 시)
```

- 프론트엔드는 **Backend 서버에만** 접속합니다. AI 서버와 직접 통신하지 않습니다.
- AI 서버와 양방향 통신하는 서버는 **Backend 서버** 하나뿐입니다.
- Backend 서버가 프론트엔드 요청을 수신하여 AI 서버에 전달합니다.
- AI 서버 내부에서 `BackendClient` (`src/api/client.py`)를 통해 Backend 서버와 통신합니다.
- AWS 배포 시 ALB 헬스체크 등 AWS 시스템도 AI 서버에 접근 가능합니다.

### 인증 방식

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

## 카테고리

| 카테고리 | 설명 | 방향 |
|---------|------|------|
| **Podcast** | 팟캐스트 모드 관련 API | 수신 (Backend → AI) |
| **Session** | 세션 생성/종료 API | 수신 (Backend → AI) |
| **History** | 히스토리 조회 API | Backend → Frontend (AI 미관여) |
| **User** | 사용자 프로필 API | 수신 (Backend → AI) |
| **Operational** | 헬스체크, 메트릭 | 수신 (Backend/AWS → AI) |
| **Internal** | AI → Backend 내부 저장 API | 발신 (AI → Backend) |
| **Streaming** | 실시간 이벤트 스트리밍 | AI → Frontend (SSE/WS) |
| **Common** | 공통 에러 코드 등 | — |

---

## API 목록

### ▼ 수신 API (Backend Server → AI Server)

#### Podcast

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 1 | [팟캐스트 에피소드 생성](#1-팟캐스트-에피소드-생성) | `POST` | /api/v1/podcasts/episodes | 구현 완료 | v1.1: 스키마 갱신 |

#### History

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 2 | [감정 추이 조회](#2-감정-추이-조회) | `GET` | /api/v1/users/{user_id}/emotions | 명세 완료 | v1.2: 엔드포인트 변경, user_id→PathVar |
| 3 | [에피소드 목록 조회](#3-에피소드-목록-조회) | `GET` | /api/v1/users/{user_id}/podcasts/episodes | 명세 완료 | v1.2: 엔드포인트 변경, themes→Array |
| 4 | [에피소드 단건 조회](#4-에피소드-단건-조회) | `GET` | /api/v1/users/{user_id}/podcasts/episodes/{episode_id} | 명세 완료 | v1.2: 엔드포인트 변경, 응답 구조 변경 |

#### Session

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 5 | [세션 생성](#5-세션-생성) | `POST` | /api/v1/sessions | 구현 완료 | v1.1 추가 |
| 6 | [세션 종료](#6-세션-종료) | `POST` | /api/v1/sessions/{session_id}/close | 구현 완료 | v1.1 추가 |

#### User

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 14 | [사용자 프로필 수정](#14-사용자-프로필-수정) | `PATCH` | /api/v1/users/{user_id}/profile | 명세 완료 | v1.2 추가 |

#### Operational

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 7 | [헬스체크](#7-헬스체크) | `GET` | /health, /health/ready | 구현 완료 | v1.1 추가 |
| 8 | [Prometheus 메트릭](#8-prometheus-메트릭) | `GET` | /metrics | 구현 완료 | v1.1 추가 |

### ▼ 발신 API (AI Server → Backend Server)

#### Internal

| # | 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|---|------|------|----------|------|---------|
| 9 | [에피소드 저장](#9-에피소드-저장) | `POST` | /api/v1/podcast_episodes | 명세 완료 | v1.1 추가 |
| 10 | [감정 로그 저장](#10-감정-로그-저장) | `POST` | /api/v1/emotion_logs | 명세 완료 | v1.1 추가 |
| 11 | [시각화 메타 저장](#11-시각화-메타-저장) | `POST` | /api/v1/visualizations | 명세 완료 | v1.1 추가 |
| 12 | [학습 데이터 저장](#12-학습-데이터-저장) | `POST` | /api/v1/learning | 명세 완료 | v1.1 추가 |
| 13 | [콘텐츠 분석 저장](#13-콘텐츠-분석-저장) | `POST` | /api/v1/content_analyses | 명세 완료 | v1.1 추가 |

### ▼ Common

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [공통 Error Code 명세](#공통-error-code-명세) | | | 명세 완료 | v1.2: 에러 코드 추가/변경 |
| [스트리밍 이벤트 스키마](#스트리밍-이벤트-스키마) | | | 명세 완료 | v1.2 추가 |

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
    ├── _build_episode_data()  → PodcastEpisodeData (segments, key_insights, themes)
    ├── _extract_emotion()     → EmotionSummary | None
    ├── _extract_safety_alert() → SafetyAlertData | None  (warning/crisis 시)
    └── VisualizationData      → 커버 이미지 메타 (visual_data 존재 시)
    │
    ▼ PodcastEpisodeResponse 조립
    │
    ├── episode:      PodcastEpisodeData
    ├── emotion:      EmotionSummary | None
    ├── safety_alert: SafetyAlertData | None
    ├── cover_image:  VisualizationData | None
    ├── metadata:     PodcastResponseMeta (duration_ms, intent_type, ...)
    └── tracing:      RequestTracing
```

#### 백그라운드 저장

HTTP 응답 반환 **후** BackgroundTasks에서 실행됩니다. 저장 실패가 HTTP 응답에 영향을 주지 않습니다.

```
[HTTP 응답 반환 후]
    │
    ▼ BackgroundTasks → _save_episode_bundle()
    │
    ├── (1) 에피소드 메타 + 세그먼트
    │       └── BackendClient.save(RESOURCE_PODCAST_EPISODE, SaveRequest)
    │              └── POST /api/v1/podcast_episodes → Backend 서버
    │
    ├── (2) 감정 로그 (emotion_summary 존재 시)
    │       └── BackendClient.save(RESOURCE_EMOTION_LOG, SaveRequest)
    │              └── POST /api/v1/emotion_logs → Backend 서버
    │
    └── (3) 시각화 메타 (visual_data 존재 시)
            └── BackendClient.save(RESOURCE_VISUALIZATION, SaveRequest)
                   └── POST /api/v1/visualizations → Backend 서버
```

**관련 파일**: `src/api/routes/podcasts.py` → `_save_episode_bundle()`

### 전체 타임라인

```
시간 ──────────────────────────────────────────────────────────▶

[요청 수신]──[TIER 0]──[TIER 1 병렬]──[TIER 2]──[TIER 3]──[TIER 4]──[응답 반환]
                           │                                            │
                     AgentDataPublisher                           BackgroundTasks
                     (즉시 전달)                               (비동기 일괄 저장)
                           │                                            │
                           ▼                                            ▼
                     Backend 서버                                Backend 서버
                    (emotion_log,                          (podcast_episodes,
                     content_analysis)                      emotion_logs,
                                                            visualizations)
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

# 수신 API (Backend Server → AI Server)

> Backend 서버가 프론트엔드 요청을 받아 AI 서버에 전달하는 API입니다.

# 1. 팟캐스트 에피소드 생성

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /api/v1/podcasts/episodes |
| 카테고리 | Podcast |
| 타입 | `POST` |

**EndPoint** : `POST /api/v1/podcasts/episodes`

**설명** : 사용자의 주제(topic)와 설명(description)을 받아 팟캐스트모드 LangGraph 파이프라인(TIER 0→1→2→3→4)을 실행하고, AI가 생성한 에피소드 스크립트를 반환합니다. 에피소드 데이터는 BackgroundTasks로 비동기 저장됩니다.

**구현 파일** : `src/api/routes/podcasts.py`

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

> 없음

### Query Parameter

> 없음

### Request Body

> 소스: `PodcastRequest` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 ID |
| session_id | String (UUID) | true | 세션 고유 ID |
| topic | String | true | 에피소드 주제 (2~200자) |
| description | String | false | 주제에 대한 상세 설명 (최대 2000자) |
| preferences | Object | false | 에피소드 생성 선호 설정 |
| preferences.target_duration_minutes | Integer | false | 목표 에피소드 길이 (분, 3~5, 기본 5) |
| preferences.tone | String | false | 톤 선호 (`warm`, `professional`, `casual`, `motivational`) |
| preferences.include_visualization | Boolean | false | 커버 이미지 생성 여부 (기본 true) |
| tracing | Object | false | 추적 컨텍스트 (미전송 시 서버가 자동 생성) |
| tracing.request_id | String | false | API 요청 고유 ID |
| tracing.trace_id | String | false | 분산 추적 ID |
| tracing.correlation_id | String | false | 상관관계 ID |

```json
{
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "topic": "직장 스트레스 관리법에 대해 알고 싶어",
    "description": "특히 야근이 많은 상황에서...",
    "preferences": {
        "target_duration_minutes": 5,
        "tone": "warm",
        "include_visualization": true
    }
}
```

### Response Body

**Success**

> 소스: `PodcastEpisodeResponse` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `true` |
| episode | Object | true | 에피소드 데이터 |
| episode.episode_id | String | true | 에피소드 고유 ID |
| episode.session_id | String | true | 생성 세션 ID |
| episode.episode_title | String | true | 에피소드 제목 (한국어) |
| episode.total_duration | Integer | true | 총 에피소드 길이 (분) |
| episode.segments | Array | true | 세그먼트 목록 |
| episode.segments[].segment_id | String | true | 세그먼트 고유 ID |
| episode.segments[].segment_type | String | true | `opening`, `education`, `practical`, `exploration`, `transition`, `closing` |
| episode.segments[].duration_minutes | Integer | true | 세그먼트 예상 길이 (분) |
| episode.segments[].script_text | String | true | 스크립트 텍스트 (TTS 입력) |
| episode.segments[].word_count | Integer | true | 단어 수 |
| episode.segments[].emotional_tone | String | true | 감정 톤 |
| episode.segments[].tts_markers | Array | true | TTS 제어 마커 |
| episode.key_insights | Array[String] | true | 핵심 인사이트 (3~5개) |
| episode.themes | Array[String] | true | 에피소드 주제 태그 |
| episode.created_at | String | true | 에피소드 생성 시각 (ISO 8601) |
| emotion | Object | false | 감정 분석 요약 (null 가능) |
| emotion.primary_emotion | String | true | 주요 감정 (영문 키) |
| emotion.primary_emotion_kr | String | true | 주요 감정 (한국어, UI 표시용) |
| emotion.intensity | Float | true | 감정 강도 (0.0~1.0) |
| emotion.valence | Float | true | 감정 가치 (-1.0~1.0) |
| emotion.secondary_emotions | Array[String] | true | 부수 감정 목록 |
| emotion.tone_recommendation | String | true | 추천 톤 |
| safety_alert | Object | false | 안전 경고 (warning/crisis 시에만 포함) |
| safety_alert.status | String | true | `warning` 또는 `crisis` |
| safety_alert.alert_message | String | true | 안전 안내 메시지 (한국어) |
| safety_alert.helpline_info | Array | false | 도움 연결 정보 |
| safety_alert.show_emergency_button | Boolean | true | 긴급 도움 버튼 표시 여부 |
| cover_image | Object | false | 커버 이미지 (비동기 생성이므로 null 가능) |
| cover_image.image_url | String | false | 이미지 URL (S3 CDN) |
| cover_image.interpretation | String | true | 해설 텍스트 |
| cover_image.style_type | String | true | 시각적 스타일 유형 |
| cover_image.original_prompt | String | true | 이미지 생성 원본 프롬프트 |
| cover_image.resolution | String | true | 이미지 해상도 |
| cover_image.status | String | true | 생성 상태 |
| metadata | Object | true | 응답 메타데이터 |
| metadata.mode | String | true | 항상 `"podcast"` |
| metadata.pipeline_duration_ms | Integer | true | 파이프라인 소요 시간 (ms) |
| metadata.intent_type | String | true | 분류된 의도 타입 |
| metadata.complexity_score | Float | true | 입력 복잡도 점수 |
| metadata.reasoning_depth | String | true | 추론 깊이 (full/standard/minimal) |
| metadata.retry_count | Integer | true | TIER 2→3 재시도 횟수 |
| metadata.total_words | Integer | true | 전체 스크립트 단어 수 |
| tracing | Object | true | 추적 컨텍스트 |

```json
{
    "success": true,
    "episode": {
        "episode_id": "ep_a1b2c3d4e5f6",
        "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "episode_title": "야근 속 나를 지키는 법 - 직장 스트레스 관리 가이드",
        "total_duration": 5,
        "segments": [
            {
                "segment_id": "seg_001",
                "segment_type": "opening",
                "duration_minutes": 1,
                "script_text": "안녕하세요, 오늘은 직장에서의 스트레스, 특히 야근이 많은 환경에서 ...",
                "word_count": 150,
                "emotional_tone": "warm",
                "tts_markers": []
            },
            {
                "segment_id": "seg_002",
                "segment_type": "education",
                "duration_minutes": 2,
                "script_text": "스트레스 관리의 핵심은...",
                "word_count": 300,
                "emotional_tone": "informative",
                "tts_markers": [
                    {"position": 42, "instruction": "slow_down"},
                    {"position": 180, "instruction": "pause_1s"}
                ]
            },
            {
                "segment_id": "seg_003",
                "segment_type": "practical",
                "duration_minutes": 1,
                "script_text": "이제 잠시 멈추고, 자신에게 물어보세요...",
                "word_count": 150,
                "emotional_tone": "reflective",
                "tts_markers": []
            },
            {
                "segment_id": "seg_004",
                "segment_type": "closing",
                "duration_minutes": 1,
                "script_text": "오늘 이야기를 마무리하며...",
                "word_count": 120,
                "emotional_tone": "encouraging",
                "tts_markers": []
            }
        ],
        "key_insights": [
            "마이크로 휴식의 중요성",
            "경계 설정 기법",
            "자기 대화 리프레이밍"
        ],
        "themes": ["직장 스트레스", "야근", "자기 관리"],
        "created_at": "2026-03-11T12:00:00.000Z"
    },
    "emotion": {
        "primary_emotion": "anxiety",
        "primary_emotion_kr": "불안",
        "intensity": 0.55,
        "valence": -0.30,
        "secondary_emotions": ["stress", "fatigue"],
        "tone_recommendation": "supportive_neutral"
    },
    "safety_alert": null,
    "cover_image": {
        "image_url": "https://cdn.mindlog.app/vis/3fa85f64/podcast/ep_a1b2c3d4e5f6/cover.webp",
        "interpretation": "잔잔한 바다와 일출이 회복의 여정을 상징합니다.",
        "style_type": "Conceptual",
        "original_prompt": "A serene ocean sunrise representing recovery journey...",
        "resolution": "1024x1024",
        "status": "completed"
    },
    "metadata": {
        "mode": "podcast",
        "pipeline_duration_ms": 3200,
        "intent_type": "topic_exploration",
        "complexity_score": 0.5,
        "reasoning_depth": "standard",
        "retry_count": 0,
        "total_words": 720
    },
    "tracing": {
        "request_id": "req_8a9b0c1d2e3f",
        "trace_id": "trace_4a5b6c7d8e9f",
        "correlation_id": "corr_1a2b3c4d5e6f",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

**Error**

> 소스: `ErrorResponse` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `false` |
| error | Object | true | 에러 상세 |
| error.code | String | true | 에러 코드 |
| error.message | String | true | 에러 메시지 |
| error.field | String | false | 에러가 발생한 필드명 (검증 에러 시) |
| error.trace_id | String | false | 추적 ID (디버깅용) |
| tracing | Object | false | 추적 컨텍스트 (디버깅용) |

```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "topic은 2자 이상이어야 합니다.",
        "field": "topic",
        "trace_id": "trace_4a5b6c7d8e9f"
    },
    "tracing": {
        "request_id": "req_8a9b0c1d2e3f",
        "trace_id": "trace_4a5b6c7d8e9f",
        "correlation_id": "corr_1a2b3c4d5e6f",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 에피소드 생성 성공 |
| 422 Unprocessable Entity | VALIDATION_ERROR | 요청 검증 에러 (Pydantic) |
| 500 Internal Server Error | SERVER_ERROR | 서버 내부 오류 |

---

# 2. 감정 추이 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/users/{user_id}/emotions |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/v1/users/{user_id}/emotions`

**설명** : 사용자의 과거 감정 분석 기록을 시간순으로 조회합니다. 프론트엔드의 감정 추이 그래프, 감정 분포 차트, 감정 달력 등 시각화 컴포넌트에 데이터를 제공합니다. Backend 서버가 MySQL `emotion_logs` 테이블에서 직접 조회하여 반환합니다 (AI 서버 미관여).

**구현 파일** : 미구현 (Backend 서버 담당)
**소스 스키마** : `EmotionHistoryResponse`, `EmotionLogEntry`, `PaginationMeta` (src/api/external_schemas.py)

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Authorization | Bearer {token} | JWT 인증 토큰. 토큰의 user_id 클레임과 Path Parameter의 user_id 일치 여부 검증 |

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 식별자. Backend `users` 테이블의 PK |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| days | Integer | false | 30 | 조회 기간 (일 단위, 1~365). 현재로부터 과거 N일간 필터링 |
| page | Integer | false | 1 | 페이지 번호 (1부터 시작). Pydantic `ge=1` |
| page_size | Integer | false | 20 | 페이지당 항목 수 (1~100). Pydantic `ge=1, le=100` |

### Request Body

> GET 요청은 Request Body가 없습니다.

### Response Body

**Success**

> 소스: `EmotionHistoryResponse` (src/api/external_schemas.py)

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| success | Boolean | false | 항상 `true` |
| emotions | Array[EmotionLogEntry] | false | 감정 로그 항목 배열 (최신순 정렬, 결과 없으면 빈 배열) |
| emotions[].log_id | String | false | 감정 로그 고유 ID. 형식: `emo_{uuid_hex[:8]}` |
| emotions[].session_id | String | false | 소속 세션 ID. 형식: `sess_{uuid_hex[:12]}` |
| emotions[].mode | String | false | 모드 (`conversation` 또는 `podcast`) |
| emotions[].primary_emotion | String | false | 주감정 (영문 키, e.g. `anxiety`, `joy`) |
| emotions[].intensity | Float | false | 감정 강도 (0.0~1.0) |
| emotions[].valence | Float | false | 극성 (-1.0~1.0, 부정~긍정) |
| emotions[].arousal | Float | false | 각성도 (0.0~1.0) |
| emotions[].secondary_emotions | Array[String] | false | 부수 감정 (빈 배열 가능) |
| emotions[].created_at | String (ISO 8601) | false | 기록 시각 (UTC) |
| pagination | Object (PaginationMeta) | false | 페이지네이션 정보 |
| pagination.page | Integer | false | 현재 페이지 |
| pagination.page_size | Integer | false | 페이지당 항목 수 |
| pagination.total_items | Integer | false | 전체 항목 수 |
| pagination.total_pages | Integer | false | 전체 페이지 수 |
| pagination.has_next | Boolean | false | 다음 페이지 존재 여부 |
| pagination.has_prev | Boolean | false | 이전 페이지 존재 여부 |
| tracing | Object (RequestTracing) | false | 추적 컨텍스트 |

```json
{
    "success": true,
    "emotions": [
        {
            "log_id": "emo_a1b2c3d4",
            "session_id": "sess_x1y2z3w4a5b6",
            "mode": "podcast",
            "primary_emotion": "anxiety",
            "intensity": 0.65,
            "valence": -0.40,
            "arousal": 0.70,
            "secondary_emotions": ["stress", "fatigue"],
            "created_at": "2026-03-03T12:00:00.000Z"
        }
    ],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total_items": 45,
        "total_pages": 3,
        "has_next": true,
        "has_prev": false
    },
    "tracing": {
        "request_id": "req_a1b2c3d4e5f6",
        "trace_id": "trace_f6e5d4c3b2a1",
        "correlation_id": "corr_1a2b3c4d5e6f",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

**Error**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| success | Boolean | false | 항상 `false` |
| error | Object (ErrorDetail) | false | 에러 상세 |
| error.code | String | false | 에러 코드 (`VALIDATION_ERROR`, `AUTH_ERROR`, `NOT_FOUND`, `SERVER_ERROR`) |
| error.message | String | false | 에러 메시지 |
| error.trace_id | String | true | 추적 ID |
| tracing | Object | true | 추적 컨텍스트 |

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | SUCCESS | 조회 성공 (결과 0건이어도 200 OK, 빈 배열) |
| 400 Bad Request | VALIDATION_ERROR | Query Parameter 유효성 검증 실패 |
| 401 Unauthorized | AUTH_ERROR | JWT 인증 실패 또는 user_id 불일치 |
| 404 Not Found | NOT_FOUND | user_id에 해당하는 사용자 미존재 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 에러 |

### 변경 이력

- **v1.2**: 엔드포인트 변경 (`/api/v1/history/emotions` → `/api/v1/users/{user_id}/emotions`), `user_id`를 Query → Path Variable로 이동, 응답 래퍼 변경 (`{code, message, data}` → `{success, emotions[], pagination, tracing}`), `recorded_at` → `created_at`, `limit` → `page_size` (1~100), `log_id`/`session_id` 신규 필드 추가

---

# 3. 에피소드 목록 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/users/{user_id}/podcasts/episodes |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/v1/users/{user_id}/podcasts/episodes`

**설명** : 사용자가 생성한 팟캐스트 에피소드 목록을 페이지네이션 기반으로 조회합니다. Backend 서버가 MySQL `podcast_episodes` 테이블에서 직접 조회하여 반환합니다 (AI 서버 미관여).

**구현 파일** : 미구현 (Backend 서버 담당)
**소스 스키마** : `PodcastEpisodeListResponse`, `PodcastEpisodeSummary`, `PaginationMeta` (src/api/external_schemas.py)

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Authorization | Bearer {token} | JWT 인증 토큰 |

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 식별자 |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| page | Integer | false | 1 | 페이지 번호 (1부터 시작). Pydantic `ge=1` |
| page_size | Integer | false | 20 | 페이지당 항목 수 (1~100). Pydantic `ge=1, le=100` |

### Request Body

> GET 요청은 Request Body가 없습니다.

### Response Body

**Success**

> 소스: `PodcastEpisodeListResponse` (src/api/external_schemas.py)

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| success | Boolean | false | 항상 `true` |
| episodes | Array[PodcastEpisodeSummary] | false | 에피소드 요약 목록 (최신순 정렬, 빈 배열 가능) |
| episodes[].episode_id | String | false | 에피소드 고유 ID (UUID) |
| episodes[].title | String | false | 에피소드 제목 (한국어) |
| episodes[].total_duration_minutes | Integer | false | 총 재생 시간 (분) |
| episodes[].themes | Array[String] | false | 주제 태그 배열 |
| episodes[].primary_emotion | String | **true** | 주감정 (영문 키). 감정 분석 미수행 시 `null` |
| episodes[].cover_image_url | String | **true** | 커버 이미지 CDN URL. 미생성 시 `null` |
| episodes[].created_at | String (ISO 8601) | false | 생성 시각 (UTC) |
| pagination | Object (PaginationMeta) | false | 페이지네이션 정보 (6 필드) |
| tracing | Object (RequestTracing) | false | 추적 컨텍스트 |

```json
{
    "success": true,
    "episodes": [
        {
            "episode_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "title": "야근 속 나를 지키는 법",
            "total_duration_minutes": 5,
            "themes": ["직장 스트레스", "야근", "자기 관리"],
            "primary_emotion": "anxiety",
            "cover_image_url": "https://cdn.mindlog.app/vis/podcast/sess_a1b2/c3d4e5f6.webp",
            "created_at": "2026-03-03T12:00:00.000Z"
        },
        {
            "episode_id": "d4e5f6a7-b8c9-0123-def0-234567890123",
            "title": "마음 돌봄의 시작",
            "total_duration_minutes": 4,
            "themes": ["자기 돌봄", "명상"],
            "primary_emotion": null,
            "cover_image_url": null,
            "created_at": "2026-03-01T09:15:00.000Z"
        }
    ],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total_items": 8,
        "total_pages": 1,
        "has_next": false,
        "has_prev": false
    },
    "tracing": {
        "request_id": "req_b2c3d4e5f6a7",
        "trace_id": "trace_0a1b2c3d4e5f",
        "correlation_id": "corr_5f4e3d2c1b0a",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `false` |
| error | Object | true | 에러 상세 |
| error.code | String | true | 에러 코드 (`VALIDATION_ERROR`, `AUTH_ERROR`, `NOT_FOUND`) |
| error.message | String | true | 에러 메시지 |
| tracing | Object | false | 추적 컨텍스트 |

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 조회 성공 (에피소드 없어도 빈 배열로 200 반환) |
| 400 Bad Request | VALIDATION_ERROR | page_size 범위 초과 등 Query Parameter 검증 실패 |
| 401 Unauthorized | AUTH_ERROR | JWT 토큰 미전달, 만료, 유효하지 않은 토큰 |
| 404 Not Found | NOT_FOUND | user_id에 해당하는 사용자 미존재 |

### 변경 이력

- **v1.2**: 엔드포인트 변경 (`/api/v1/history/episodes` → `/api/v1/users/{user_id}/podcasts/episodes`), `user_id` Query → Path Variable, 응답 래퍼 변경, `theme`(단수) → `themes`(배열), `primary_emotion` Required → nullable, `limit` → `page_size`, 페이지네이션 6필드 확장

---

# 4. 에피소드 단건 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/users/{user_id}/podcasts/episodes/{episode_id} |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/v1/users/{user_id}/podcasts/episodes/{episode_id}`

**설명** : 특정 팟캐스트 에피소드의 전체 데이터를 상세 조회합니다. Backend 서버가 MySQL의 `podcast_episodes` + `podcast_segments` 테이블을 JOIN하여 직접 조회합니다. 응답 구조는 팟캐스트 에피소드 생성 API의 `PodcastEpisodeResponse`와 동일합니다.

**구현 파일** : 미구현 (Backend 서버 담당)
**소스 스키마** : `PodcastEpisodeData`, `PodcastSegment`, `EmotionSummary`, `SafetyAlertData`, `VisualizationData` (src/api/external_schemas.py)

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Authorization | Bearer {token} | JWT 인증 토큰. 토큰의 user_id 클레임과 Path Parameter의 user_id 일치 검증 |

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 식별자 |
| episode_id | String (UUID) | true | 조회 대상 에피소드 ID. `podcast_episodes` 테이블의 PK |

### Request Body

> GET 요청은 Request Body가 없습니다.

### Response Body

**Success**

> 소스: AI 파이프라인의 `PodcastEpisodeResponse` 구조와 동일. Backend 서버가 MySQL에서 재구성하여 반환.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| success | Boolean | false | 항상 `true` |
| episode | Object (PodcastEpisodeData) | false | 에피소드 전체 데이터 |
| episode.episode_id | String | false | 에피소드 고유 ID |
| episode.session_id | String | false | 생성 세션 ID |
| episode.title | String | false | 에피소드 제목 (한국어) |
| episode.total_duration_minutes | Integer | false | 총 재생 시간 (분) |
| episode.created_at | String (ISO 8601) | false | 생성 시각 (UTC) |
| episode.segments | Array[PodcastSegment] | false | 세그먼트 배열 (segment_order ASC 정렬, 3~5개) |
| episode.segments[].segment_id | String | false | 세그먼트 고유 ID |
| episode.segments[].segment_type | String | false | `opening`, `education`, `practical`, `exploration`, `transition`, `closing` |
| episode.segments[].script_text | String | false | 스크립트 전문 (한국어, TTS 입력) |
| episode.segments[].duration_minutes | Integer | false | 예상 재생 시간 (분) |
| episode.segments[].emotional_tone | String | false | 감정 톤 (`warm`, `informative`, `reflective`, `encouraging`, `neutral` 등) |
| episode.segments[].word_count | Integer | false | 단어(어절) 수 |
| episode.segments[].tts_markers | Array[TTSMarkerData] | false | TTS 제어 마커 배열 (빈 배열 가능) |
| episode.segments[].tts_markers[].position | Integer | false | 스크립트 내 문자 위치 |
| episode.segments[].tts_markers[].instruction | String | false | TTS 지시사항 (`slow_down`, `pause_1s`, `emphasize` 등) |
| episode.key_insights | Array[String] | false | 핵심 인사이트 (3~5개) |
| episode.themes | Array[String] | false | 주제 태그 |
| emotion | Object (EmotionSummary) | **true** | 감정 분석 요약 (Safety CRISIS 등으로 미수행 시 `null`) |
| emotion.primary_emotion | String | false | 주감정 (영문 키) |
| emotion.primary_emotion_kr | String | false | 주감정 (한국어) |
| emotion.intensity | Float | false | 강도 (0.0~1.0) |
| emotion.valence | Float | false | 극성 (-1.0~1.0) |
| emotion.secondary_emotions | Array[String] | false | 부수 감정 |
| emotion.tone_recommendation | String | false | 추천 톤 |
| safety_alert | Object (SafetyAlertData) | **true** | 안전 경고 (warning/crisis 시에만 존재) |
| cover_image | Object | **true** | 커버 이미지 데이터 |
| cover_image.image_url | String | **true** | S3 CDN URL (비동기 생성 중이면 `null`) |
| cover_image.interpretation_text | String | false | 해설 텍스트 (한국어) |
| cover_image.style_info | Object | false | 스타일 정보 (`type`, `palette`, `gradient`, `pattern`, `primary_emotion`) |
| metadata | Object (PodcastResponseMeta) | false | 응답 메타데이터 (mode, pipeline_duration_ms, intent_type 등) |
| tracing | Object (RequestTracing) | false | 추적 컨텍스트 |

```json
{
    "success": true,
    "episode": {
        "episode_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
        "session_id": "sess_a1b2c3d4e5f6",
        "title": "야근 속 나를 지키는 법 - 직장 스트레스 관리 가이드",
        "total_duration_minutes": 5,
        "created_at": "2026-03-03T12:00:00.000Z",
        "segments": [
            {
                "segment_id": "seg_001",
                "segment_type": "opening",
                "script_text": "안녕하세요, 오늘은 직장에서의 야근과 스트레스...",
                "duration_minutes": 1,
                "emotional_tone": "warm",
                "word_count": 150,
                "tts_markers": [
                    {"position": 0, "instruction": "slow_down"},
                    {"position": 45, "instruction": "pause_1s"}
                ]
            }
        ],
        "key_insights": ["마이크로 휴식의 중요성", "경계 설정 기법", "점진적 이완법"],
        "themes": ["직장 스트레스", "야근", "자기 관리"]
    },
    "emotion": {
        "primary_emotion": "anxiety",
        "primary_emotion_kr": "불안",
        "intensity": 0.55,
        "valence": -0.30,
        "secondary_emotions": ["stress", "fatigue"],
        "tone_recommendation": "supportive_neutral"
    },
    "safety_alert": null,
    "cover_image": {
        "image_url": "https://cdn.mindlog.app/vis/podcast/sess_a1b2c3d4e5f6/c3d4e5f6/cover.webp",
        "interpretation_text": "잔잔한 바다와 일출이 회복의 여정을 상징합니다.",
        "style_info": {
            "type": "Conceptual",
            "palette": "blue",
            "gradient": ["#1a2a6c", "#b21f1f", "#fdbb2d"],
            "pattern": "soft_rain",
            "primary_emotion": "anxiety"
        }
    },
    "metadata": {
        "mode": "podcast",
        "pipeline_duration_ms": 3200,
        "intent_type": "stress_management",
        "complexity_score": 0.65,
        "reasoning_depth": "standard",
        "retry_count": 0,
        "total_words": 720
    },
    "tracing": {
        "request_id": "req_a1b2c3d4e5f6",
        "trace_id": "trace_f6e5d4c3b2a1",
        "correlation_id": "corr_1a2b3c4d5e6f",
        "timestamp": "2026-03-03T12:00:00.000Z"
    }
}
```

**Error**

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| success | Boolean | false | 항상 `false` |
| error | Object (ErrorDetail) | false | 에러 상세 |
| error.code | String | false | `NOT_FOUND`, `AUTH_ERROR`, `SERVER_ERROR` |
| error.message | String | false | 에러 메시지 |
| tracing | Object | true | 추적 컨텍스트 |

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | SUCCESS | 조회 성공 |
| 401 Unauthorized | AUTH_ERROR | JWT 인증 실패 또는 user_id 불일치 |
| 404 Not Found | NOT_FOUND | 에피소드 미발견 또는 소유자 불일치 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 에러 |

### 변경 이력

- **v1.2**: 엔드포인트 변경 (`/api/v1/history/episodes/{episodeId}` → `/api/v1/users/{user_id}/podcasts/episodes/{episode_id}`), 응답 래퍼 변경, `episode_title` → `title`, `total_duration` → `total_duration_minutes`, `tts_markers` 추가, `cover_image.interpretation` → `interpretation_text`, `cover_image.style_info` 추가, `emotion.arousal` 제거 (EmotionSummary 미포함)

---

# 5. 세션 생성

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /api/v1/sessions |
| 카테고리 | Session |
| 타입 | `POST` |

**EndPoint** : `POST /api/v1/sessions`

**설명** : 대화나 팟캐스트 모드 진입 시 Backend 서버가 호출합니다. 신규 세션 ID(`sess_{uuid}`)를 생성하여 반환합니다.

**구현 파일** : `src/api/routes/sessions.py`

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |

### Request Body

> 소스: `SessionCreateRequest` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 ID |
| mode | String | false | 모드 (`"conversation"` 또는 `"podcast"`, 기본 `"conversation"`) |
| device_info | Object | false | 디바이스 정보 |
| tracing | Object | false | 추적 컨텍스트 (미전송 시 서버가 자동 생성) |

```json
{
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "mode": "podcast",
    "tracing": {
        "request_id": "req_1a2b3c4d5e6f",
        "trace_id": "trace_7a8b9c0d1e2f",
        "correlation_id": "corr_3a4b5c6d7e8f"
    }
}
```

### Response Body

**Success**

> 소스: `SessionCreateResponse` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `true` |
| session_id | String | true | 생성된 세션 ID (`sess_{uuid}`) |
| mode | String | true | 세션 모드 |
| created_at | String | true | 생성 시각 (ISO 8601) |
| tracing | Object | true | 추적 컨텍스트 |

```json
{
    "success": true,
    "session_id": "sess_a1b2c3d4e5f6",
    "mode": "podcast",
    "created_at": "2026-03-11T12:00:00.000Z",
    "tracing": {
        "request_id": "req_1a2b3c4d5e6f",
        "trace_id": "trace_7a8b9c0d1e2f",
        "correlation_id": "corr_3a4b5c6d7e8f",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 세션 생성 성공 |
| 422 Unprocessable Entity | VALIDATION_ERROR | 요청 검증 에러 |
| 500 Internal Server Error | SERVER_ERROR | 서버 내부 오류 |

---

# 6. 세션 종료

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 (Learning 트리거 비활성) |
| 엔드포인트 | /api/v1/sessions/{session_id}/close |
| 카테고리 | Session |
| 타입 | `POST` |

**EndPoint** : `POST /api/v1/sessions/{session_id}/close`

**설명** : 대화가 끝났을 때 Backend 서버가 호출합니다. 향후 Learning Agent를 비동기로 트리거하여 세션 피드백을 학습할 예정입니다.

**구현 파일** : `src/api/routes/sessions.py`

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| session_id | String | 종료할 세션 ID | sess_a1b2c3d4e5f6 |

### Request Body

> 소스: `SessionCloseRequest` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 ID |
| session_id | String | true | 종료할 세션 ID |
| feedback | Object | false | 사용자 피드백 |
| feedback.rating | Integer | false | 만족도 (1~5) |
| feedback.helpful | Boolean | false | 도움 여부 |
| feedback.comment | String | false | 코멘트 (최대 500자) |
| tracing | Object | false | 추적 컨텍스트 |

```json
{
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "session_id": "sess_a1b2c3d4e5f6",
    "feedback": {
        "rating": 4,
        "helpful": true,
        "comment": "도움이 되었어요"
    }
}
```

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `true` |
| message | String | true | 성공 메시지 |

```json
{
    "success": true,
    "message": "Session sess_a1b2c3d4e5f6 closed successfully"
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 세션 종료 성공 |
| 422 Unprocessable Entity | VALIDATION_ERROR | 요청 검증 에러 |
| 500 Internal Server Error | SERVER_ERROR | 서버 내부 오류 |

> **NOTE**: 현재 Learning Agent 트리거는 비활성 상태입니다. 대화모드 에이전트 구현 완료 후 활성화 예정.

---

# 7. 헬스체크

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /health, /health/ready |
| 카테고리 | Operational |
| 타입 | `GET` |

**구현 파일** : `src/api/routes/health.py`

---

### 7-1. ALB 헬스체크

**EndPoint** : `GET /health`

**설명** : AWS ALB Target Group 헬스체크용. 애플리케이션이 실행 중인지(200 OK) 확인합니다.

#### Response Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | String | true | 항상 `"ok"` |

```json
{
    "status": "ok"
}
```

### 7-2. Readiness 점검

**EndPoint** : `GET /health/ready`

**설명** : Docker 컨테이너 Readiness Probe용. LangGraph 컴파일 상태, BackendClient 초기화 상태를 검사합니다.

#### Response Body

> 소스: `ReadyResponse` (src/api/routes/health.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | String | true | `"ready"` 또는 `"not_ready"` |
| components | Object | true | 컴포넌트별 상태 |
| components.graph | String | true | LangGraph 컴파일 상태 (`"ok"` / `"not_ready"`) |
| components.backend_client | String | true | BackendClient 초기화 상태 (`"ok"` / `"not_ready"`) |
| storage_mode | String | true | 현재 저장소 모드 (e.g. `"local"`) |

```json
{
    "status": "ready",
    "components": {
        "graph": "ok",
        "backend_client": "ok"
    },
    "storage_mode": "local"
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 정상 응답 (컴포넌트 상태는 status 필드로 확인) |

---

# 8. Prometheus 메트릭

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /metrics |
| 카테고리 | Operational |
| 타입 | `GET` |

**EndPoint** : `GET /metrics`

**설명** : Prometheus 포맷으로 파이프라인 실행 성능 메트릭을 노출합니다. Grafana 대시보드 구성에 사용됩니다.

**구현 파일** : `src/monitoring/prometheus.py`

---

### Response

- **Content-Type**: `text/plain; version=0.0.4; charset=utf-8` (Prometheus text exposition format)

### 수집 메트릭

| 메트릭 이름 | 타입 | 설명 | 라벨 |
|------------|------|------|------|
| `mindlog_requests_total` | Counter | 파이프라인 요청 수 | `mode`, `status` |
| `mindlog_crisis_events_total` | Counter | 위기 감지 이벤트 수 | — |
| `mindlog_pipeline_duration_seconds` | Histogram | 전체 파이프라인 실행 시간 | `mode` |
| `mindlog_agent_duration_seconds` | Histogram | 에이전트별 실행 시간 | `agent`, `tier` |
| `mindlog_llm_tokens_total` | Gauge | LLM 토큰 사용량 | `direction` |

### 수집 흐름

```
파이프라인 실행 시:
    MindLogTelemetryCallback (LangGraph callback)
        │ 각 에이전트 실행 시 메트릭 수집
        ▼
    telemetry_cb.get_metrics()  → PipelineMetrics
        │
        ▼
    MetricsCollector.record_pipeline(metrics)
        │ Prometheus 레지스트리에 기록
        ▼
    GET /metrics  → Prometheus text exposition format
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 메트릭 반환 성공 |

> **NOTE**: 미들웨어(`RequestLoggingMiddleware`)에서 `/health`, `/health/ready`, `/metrics` 경로는 로깅 제외됩니다.

---

# 14. 사용자 프로필 수정

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/users/{user_id}/profile |
| 카테고리 | User |
| 타입 | `PATCH` |

**EndPoint** : `PATCH /api/v1/users/{user_id}/profile`

**설명** : 사용자의 개인화 프로필을 수정합니다. Personalization Agent와 Script Personalizer가 톤/스타일 조정 시 참조하는 설정입니다.

**소스 스키마** : `UserProfileUpdateRequest`, `UserProfileData` (src/api/external_schemas.py)

---

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 식별자 |

### Request Body

> 소스: `UserProfileUpdateRequest` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String | true | 사용자 고유 ID |
| display_name | String | false | 표시 이름 (최대 50자) |
| age_group | String | false | 연령대 (`10s`, `20s`, `30s`, `40s`, `50s`, `60s_plus`) |
| preferred_style | String | false | 선호 응답 스타일 (`warm`, `professional`, `casual`, `neutral`) |
| preferred_attitude | String | false | 선호 응답 태도 (`supportive`, `analytical`, `balanced`, `motivational`) |
| accessibility_needs | Array[String] | false | 접근성 요구사항 (e.g. `["large_text", "high_contrast"]`) |
| notification_enabled | Boolean | false | 알림 수신 동의 여부 |
| tracing | Object | false | 추적 컨텍스트 |

### Response Body

**Success**

> 소스: `UserProfileData` (src/api/external_schemas.py)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String | true | 사용자 고유 ID |
| display_name | String | true | 표시 이름 (기본값: 빈 문자열) |
| age_group | String | true | 연령대 (기본값: `30s`) |
| preferred_style | String | true | 선호 스타일 (기본값: `neutral`) |
| preferred_attitude | String | true | 선호 태도 (기본값: `balanced`) |
| accessibility_needs | Array[String] | true | 접근성 요구사항 (기본값: 빈 배열) |
| notification_enabled | Boolean | true | 알림 수신 동의 (기본값: `true`) |
| created_at | String (ISO 8601) | true | 계정 생성 시각 |
| updated_at | String (ISO 8601) | true | 마지막 수정 시각 |
| total_sessions | Integer | true | 총 세션 수 (기본값: 0) |
| total_episodes | Integer | true | 총 에피소드 수 (기본값: 0) |

---

# 발신 API (AI Server → Backend Server)

> AI 서버가 파이프라인 실행 중/후에 Backend 서버로 데이터를 저장하는 내부 API입니다.
> 모든 발신 API는 `BackendClient` (`src/api/client.py`)를 통해 호출됩니다.

### BackendClient 통신 개요

| 메서드 | HTTP | 용도 | 사용처 |
|--------|------|------|--------|
| `save(resource, data)` | POST /api/v1/{resource} | 데이터 저장 | _save_episode_bundle, AgentDataPublisher, LearningAgent |
| `load(resource, user_id, **params)` | GET /api/v1/{resource} | 데이터 조회 | 현재 미사용 (대화모드 구현 시 사용 예정) |

### 통신 설정

| 항목 | 값 | 환경변수 |
|------|---|---------|
| Base URL | `http://localhost:8080/api/v1` | `BACKEND_API_URL` |
| 타임아웃 | 5초 | `config/settings.yaml → api.timeout` |
| 최대 재시도 | 3회 (exponential backoff: 1초, 2초, 4초) | — |

**관련 파일**: `src/api/client.py`, `src/api/backend_resources.py`

### 공통 요청 형식 (SaveRequest)

> 소스: `SaveRequest` (src/api/contracts.py)

```json
{
    "user_id": "string (UUID)",
    "session_id": "string (UUID)",
    "type": "string (데이터 유형 식별자)",
    "data": { "..." },
    "timestamp": "2026-03-11T12:00:00Z (ISO 8601)"
}
```

### 공통 응답 형식 (SaveResponse)

> 소스: `SaveResponse` (src/api/contracts.py)

```json
{
    "success": true,
    "id": "string (생성된 리소스 ID, nullable)",
    "message": "string (응답 메시지, nullable)"
}
```

---

# 9. 에피소드 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/podcast_episodes |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/v1/podcast_episodes`

**설명** : 팟캐스트 에피소드 생성 후 에피소드 메타데이터와 세그먼트 데이터를 Backend에 비동기 저장합니다.

**구현 파일** : `src/api/routes/podcasts.py` → `_save_episode_bundle()`
**리소스 상수** : `RESOURCE_PODCAST_EPISODE` (`src/api/backend_resources.py`)
**호출 시점** : BackgroundTasks로 비동기 호출

---

### Request Body (data 필드)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"podcast_episode"` |
| data.episode_id | String | true | 에피소드 ID (`ep_{hash}`) |
| data.episode_title | String | true | 에피소드 제목 (한국어) |
| data.total_duration | Integer | true | 총 길이 (분) |
| data.total_words | Integer | true | 전체 단어 수 |
| data.segment_count | Integer | true | 세그먼트 수 |
| data.key_insights | Array[String] | true | 핵심 인사이트 |
| data.themes | Array[String] | true | 주제 태그 |
| data.reasoning_depth | String | true | 추론 깊이 (`full`/`standard`/`minimal`) |
| data.cover_image_url | String | false | S3 CDN URL (nullable) |
| data.trace_id | String | true | 분산 추적 ID |
| data.correlation_id | String | true | 상관관계 ID |
| data.segments | Array | true | 세그먼트 목록 |
| data.segments[].segment_id | String | true | 세그먼트 ID (`seg_{number}`) |
| data.segments[].segment_order | Integer | true | 순서 (0-based) |
| data.segments[].segment_type | String | true | 타입 (`opening`/`education`/`practical`/`exploration`/`transition`/`closing`) |
| data.segments[].duration_minutes | Integer | true | 세그먼트 길이 (분) |
| data.segments[].script_text | String | true | TTS 입력 텍스트 |
| data.segments[].word_count | Integer | true | 단어 수 |
| data.segments[].emotional_tone | String | true | 감정 톤 |
| data.segments[].tts_markers_json | String | true | JSON 배열 문자열 |

### Response Body

> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

# 10. 감정 로그 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/emotion_logs |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/v1/emotion_logs`

**설명** : 감정 분석 결과를 Backend에 저장합니다. 2가지 호출 경로가 있습니다.

**호출 경로**:
1. `_save_episode_bundle()` — BackgroundTasks에서 에피소드 저장 후 비동기 호출 (emotion_summary 존재 시)
2. `AgentDataPublisher.publish()` — EmotionAgent 실행 중 중간 결과 즉시 전송

**리소스 상수** : `RESOURCE_EMOTION_LOG` (`src/api/backend_resources.py`)

---

### Request Body (data 필드)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"emotion_log"` |
| data.log_id | String | true | 로그 ID (`elog_{hash12}`) |
| data.mode | String | true | 모드 (`podcast`/`conversation`) |
| data.episode_id | String | false | 에피소드 ID (팟캐스트 전용, `null` 가능) |
| data.primary_emotion | String | true | 주요 감정 (영문, e.g. `anxiety`) |
| data.intensity | Float | true | 감정 강도 (0.0~1.0) |
| data.valence | Float | true | 감정 극성 (-1.0~1.0) |
| data.arousal | Float | true | 각성도 (0.0~1.0) |
| data.secondary_emotions | Array[String] | true | 부수 감정 목록 |
| data.tone_recommendation | String | true | 추천 톤 (e.g. `supportive_neutral`) |
| data.trace_id | String | true | 분산 추적 ID |

### Response Body

> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

# 11. 시각화 메타 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/visualizations |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/v1/visualizations`

**설명** : 시각화(커버 이미지) 메타데이터를 Backend에 저장합니다. visual_data가 존재할 때만 호출됩니다.

**구현 파일** : `src/api/routes/podcasts.py` → `_save_episode_bundle()`
**리소스 상수** : `RESOURCE_VISUALIZATION` (`src/api/backend_resources.py`)

---

### Request Body (data 필드)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"visualization"` |
| data.visualization_id | String | true | 시각화 ID (`vis_{hash12}`) |
| data.mode | String | true | 모드 (`podcast`/`conversation`) |
| data.episode_id | String | false | 에피소드 ID (팟캐스트 전용, `null` 가능) |
| data.s3_key | String | true | S3 객체 키 |
| data.cdn_url | String | true | CDN URL |
| data.image_prompt | String | true | 이미지 생성 프롬프트 (영문) |
| data.interpretation_text | String | true | 해설 텍스트 (한국어) |
| data.primary_emotion | String | true | 기반 감정 |
| data.palette | String | true | 팔레트 이름 |
| data.style_tags | Array[String] | true | 스타일 태그 |
| data.trace_id | String | true | 분산 추적 ID |

### Response Body

> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

# 12. 학습 데이터 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/learning |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/v1/learning`

**설명** : LearningAgent가 생성한 사용자 패턴 분석 결과를 Backend에 비동기 저장합니다.

**구현 파일** : `src/agents/shared/learning.py` → `_save_learning_result()`
**리소스 상수** : `RESOURCE_LEARNING` (`src/api/backend_resources.py`)

---

### Request Body (data 필드)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"learning"` |
| data.mode | String | true | 모드 (`podcast`/`conversation`) |
| data.learning_data | Object | true | 학습 결과 (가변 JSON) |
| data.learning_data.preferred_topics | Array[String] | false | 선호 주제 |
| data.learning_data.emotional_patterns | Array[String] | false | 감정 패턴 |
| data.learning_data.interaction_style | String | false | 상호작용 스타일 |

> **NOTE**: `learning_data` 내부 구조는 LLM 출력에 의존하여 가변적입니다. Backend에서는 JSON blob으로 저장을 권장합니다.

### Response Body

> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

# 13. 콘텐츠 분석 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/content_analyses |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/v1/content_analyses`

**설명** : ContentAnalyzer 에이전트의 분석 결과를 AgentDataPublisher를 경유하여 Backend에 저장합니다. 저장 실패 시에도 파이프라인 흐름에 영향을 주지 않습니다 (예외 미전파).

**구현 파일** : `src/api/publisher.py` → `AgentDataPublisher.publish()`
**리소스 상수** : `RESOURCE_CONTENT_ANALYSIS` (`src/api/backend_resources.py`)

---

### Request Body (data 필드)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"content_analysis"` |
| data.main_theme | String | true | 주요 주제 |
| data.sub_themes | Array[String] | true | 하위 주제 목록 |
| data.target_duration | Integer | true | 목표 길이 (분) |
| data.narrative_structure | String | true | 서사 구조 |
| data.depth_level | String | true | 분석 깊이 |
| data.emotional_journey | Object | true | 감정 여정 맵 |
| data.confidence | Float | true | 분석 신뢰도 (0.0~1.0) |

### Response Body

> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

## Load API — 데이터 조회

> 출처: BACKEND_API_CONTRACT.md에서 통합 (v1.2)

### 공통 요청 형식

```
GET /api/v1/{resource}?user_id={uuid}&type={type}&limit={n}&page={p}
```

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `user_id` | string | Y | 사용자 UUID |
| `type` | string | N | 데이터 유형 필터 |
| `limit` | integer | N | 페이지당 결과 수 (기본 10) |
| `page` | integer | N | 페이지 번호 (기본 1) |

### 공통 응답 형식 (LoadResponse)

> 소스: `LoadResponse` (src/api/contracts.py)

```json
{
    "success": true,
    "data": [ { "..." } ],
    "total": 10,
    "page": 1
}
```

> **NOTE**: 현재 AI 서버 코드에서 `backend_client.load()`를 호출하는 곳이 **없습니다**. 대화모드 구현 시 Memory Agent, Context Agent 등에서 사용 예정입니다.

---

## 스트리밍 이벤트 스키마

> 소스: `StreamEvent` + `StreamEventType` (src/api/external_schemas.py)
> SSE/WS 스트리밍 엔드포인트. LangGraph `get_stream_writer()` 이벤트를 프론트엔드 소비 형태로 정규화.

### StreamEventType (StrEnum)

| 이벤트 값 | 상수명 | 설명 |
|----------|--------|------|
| `tier_start` | TIER_START | TIER 실행 시작 |
| `agent_complete` | AGENT_COMPLETE | 개별 에이전트 완료 |
| `tier_end` | TIER_END | TIER 실행 완료 |
| `crisis_detected` | CRISIS_DETECTED | Safety CRISIS 감지 — TIER 1 병렬 작업 즉시 취소 |
| `partial_response` | PARTIAL_RESPONSE | 부분 응답 (스트리밍) |
| `final_response` | FINAL_RESPONSE | 최종 응답 |
| `error` | ERROR | 에러 발생 |

### StreamEvent 필드

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_type | StreamEventType | true | 이벤트 유형 |
| session_id | String | true | 세션 ID |
| tier | Integer | false | 현재 TIER (0-4). `null` 가능 |
| agent | String | false | 에이전트 이름. `null` 가능 |
| data | Object | true | 이벤트 페이로드 (기본값: 빈 객체) |
| elapsed_ms | Integer | true | TIER 시작 이후 경과 시간 (ms, 기본값: 0) |
| timestamp | String (ISO 8601) | true | 이벤트 발생 시각 (UTC) |
| trace_id | String | true | 추적 ID |

---

# 공통 Error Code 명세

> 소스: `ErrorDetail`, `ErrorResponse` (src/api/external_schemas.py)
> 전역 예외 핸들러: `src/api/main.py` (3개 핸들러)

### 에러 응답 공통 형식

```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "상세 에러 메시지",
        "field": "에러 필드명 (검증 에러 시, nullable)",
        "trace_id": "trace_xxx (디버깅용, nullable)"
    },
    "tracing": {
        "request_id": "req_xxx",
        "trace_id": "trace_xxx",
        "correlation_id": "corr_xxx",
        "timestamp": "2026-03-11T12:00:00.000Z"
    }
}
```

### 에러 코드 목록

| HTTP Status | Code | Description | 클라이언트 대응 |
|-------------|------|-------------|---------------|
| 400 | `VALIDATION_ERROR` | 필수 필드 누락 또는 형식 오류. `error.field`에 문제 필드명 포함 | 요청 데이터 확인 후 수정 |
| 400 | `INPUT_TOO_LONG` | 입력 텍스트가 최대 길이 초과 (topic 200자) | 입력 텍스트 축소 |
| 401 | `AUTH_ERROR` | 인증 실패 (토큰 만료/무효/미포함) | 토큰 갱신 후 재시도 |
| 403 | `FORBIDDEN` | 접근 권한 없음 | 권한 확인 |
| 404 | `NOT_FOUND` | 요청한 리소스를 찾을 수 없음 | URL/ID 확인 |
| 404 | `SESSION_NOT_FOUND` | session_id에 해당하는 세션 미존재 | 세션 생성 후 재시도 |
| 422 | `VALIDATION_ERROR` | Pydantic 구조 검증 실패. `error.field` 포함 | 요청 본문 구조 수정 |
| 429 | `RATE_LIMITED` | 요청 제한 초과 | `Retry-After` 헤더 값만큼 대기 후 재시도 |
| 500 | `SERVER_ERROR` | 서버 내부 오류 | 최대 3회 재시도 (exponential backoff) |
| 500 | `PIPELINE_TIMEOUT` | AI 파이프라인 실행 타임아웃 (기본 30초) | trace_id와 함께 관리자 문의 |
| 500 | `CRISIS_ESCALATION` | Safety Agent CRISIS 감지 에스컬레이션 | 위기 응답 콘텐츠를 사용자에게 즉시 표시 |
| 503 | `SERVICE_UNAVAILABLE` | 서비스 일시 중단 | 10~30초 후 재시도 |

### 전역 예외 핸들러 매핑

| 핸들러 | HTTP Status | Code 매핑 | 트리거 |
|--------|------------|----------|--------|
| `http_exception_handler` | 원본 유지 | 404→`NOT_FOUND`, 429→`RATE_LIMITED`, 기타→`SERVER_ERROR` | `StarletteHTTPException` |
| `validation_exception_handler` | 422 | `VALIDATION_ERROR` | Pydantic `RequestValidationError` |
| `general_exception_handler` | 500 | `SERVER_ERROR` | 미처리 `Exception` (catch-all) |

### 재시도 정책

- **4xx 에러**: 재시도 불필요 (요청 수정 후 재전송)
- **429 에러**: `Retry-After` 헤더 값만큼 대기 후 재시도 (헤더 미포함 시 10초 권장)
- **5xx 에러**: 최대 3회 재시도 (exponential backoff: 1초, 2초, 4초). `PIPELINE_TIMEOUT`은 재시도 비권장

---

## Backend 협의 사항

> 출처: BACKEND_API_CONTRACT.md에서 통합 (v1.2)

### 즉시 협의 (1차)

- [ ] Backend 헬스체크 경로 확인 (`/health` 또는 `/actuator/health`)
- [ ] AI → Backend 네트워크 연결 확인 (app-2:8000 → app-3:8080)
- [ ] 인증/인가 방식 결정 (Service-to-service 토큰 / API Key / 내부 네트워크 신뢰)

### API 명세 확정 (2차)

- [ ] Save API 5개 리소스의 data 스키마 검토 및 확정
- [ ] Load API 쿼리 파라미터 및 응답 구조 확정
- [ ] 에러 코드 체계 확정
- [ ] 페이지네이션 방식 (offset vs cursor) 확정

### 향후 협의 (3차)

- [ ] 벡터 검색 엔드포인트 존재 여부 (`vector/search`)
- [ ] 그래프 쿼리 엔드포인트 존재 여부 (`graph/query`)
- [ ] 이미지 업로드 엔드포인트 (`storage/upload`)
- [ ] S3 객체 조회 엔드포인트 (`storage/object`)
- [ ] 대화모드 전용 리소스 경로 (`conversations`, `memories`, `sessions`)

---

## 리소스 경로 정리

| 리소스 경로 | 상태 | Save type | 용도 |
|------------|------|-----------|------|
| `podcast_episodes` | **활성** | `podcast_episode` | 에피소드 메타 + 세그먼트 |
| `emotion_logs` | **활성** | `emotion_log` | 감정 벡터 데이터 |
| `visualizations` | **활성** | `visualization` | 커버 이미지 메타 |
| `learning` | **활성** | `learning` | 학습 패턴 데이터 |
| `content_analyses` | **활성** | `content_analysis` | 콘텐츠 분석 결과 |
| `conversations` | 미확정 | — | 대화 기록 (대화모드) |
| `memories` | 미확정 | — | 개인 기억 데이터 |
| `sessions` | 미확정 | — | 세션 메타데이터 |

**상수 정의**: `src/api/backend_resources.py`

---

## 참조 파일 인덱스

| 파일 | 역할 |
|------|------|
| `src/api/main.py` | 서버 시작, 라우터 등록, 예외 핸들러 |
| `src/api/routes/podcasts.py` | 에피소드 생성, 응답 구성, 백그라운드 저장 |
| `src/api/routes/sessions.py` | 세션 생성/종료 |
| `src/api/routes/health.py` | 헬스체크 |
| `src/api/client.py` | BackendClient (save/load) |
| `src/api/publisher.py` | AgentDataPublisher (중간 데이터 전달) |
| `src/api/contracts.py` | SaveRequest, SaveResponse, LoadResponse |
| `src/api/backend_resources.py` | 리소스 경로/타입 상수 |
| `src/api/external_schemas.py` | 외부 API 스키마 (요청/응답) |
| `src/api/middleware.py` | HTTP 요청 로깅 미들웨어 |
| `src/monitoring/prometheus.py` | Prometheus 메트릭 수집/노출 |
| `src/monitoring/callbacks.py` | LangGraph 텔레메트리 콜백 |
| `src/graph/workflow.py` | LangGraph 워크플로우 정의 |

---

## 변경이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-03-03 | 최초 작성 (팟캐스트 에피소드 생성 API) |
| v1.1 | 2026-03-11 | History API 3건 + Session 2건 + Operational 2건 + Internal 5건 + Error Code 추가 |
| v1.2 | 2026-03-13 | History API 엔드포인트 변경 (Notion SSOT 동기화), API_FLOW.md/BACKEND_API_CONTRACT.md 통합, 사용자 프로필 API 추가, 스트리밍 이벤트 스키마 추가, segment_type 영문 통일, Error Code 갱신 |

---

*마지막 업데이트: 2026-03-13 v1.2*

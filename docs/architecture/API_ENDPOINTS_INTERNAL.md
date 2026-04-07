# 발신 API (AI Server → Backend Server)

> [API_SPEC.md](API_SPEC.md) 문서 모음의 일부 (v2.0)

> AI 서버가 파이프라인 실행 중/후에 Backend 서버로 데이터를 저장하는 내부 API입니다.
> 모든 발신 API는 `BackendClient` (`src/api/client.py`)를 통해 호출됩니다.

### BackendClient 통신 개요

| 메서드 | HTTP | 용도 | 사용처 |
|--------|------|------|--------|
| `save(resource, data)` | POST /api/v1/{resource} | 데이터 저장 | _save_episode_bundle, AgentDataPublisher, LearningAgent |
| `load(resource, user_id, **params)` | GET /api/v1/{resource} | 데이터 조회 | 미구현 (향후 확장용) |

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
| data.mode | String | true | 모드 (`podcast`) |
| data.episode_id | String | false | 에피소드 ID (`null` 가능) |
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
| data.mode | String | true | 모드 (`podcast`) |
| data.episode_id | String | false | 에피소드 ID (`null` 가능) |
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
| data.mode | String | true | 모드 (`podcast`) |
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

> **NOTE**: 현재 AI 서버 코드에서 `backend_client.load()`를 호출하는 곳이 **없습니다**. 향후 필요 시 활성화 예정입니다.

---

*[← 수신 API](API_ENDPOINTS_RECEIVING.md) · [API_SPEC.md (인덱스)](API_SPEC.md) · [공통 →](API_COMMON.md)*

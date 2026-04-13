# 수신 API (Backend Server → AI Server)

> [API_SPEC.md](API_SPEC.md) 문서 모음의 일부 (v2.0)

> Backend 서버가 프론트엔드 요청을 받아 AI 서버에 전달하는 API입니다.

# 1. 팟캐스트 에피소드 생성

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /api/podcasts/episodes |
| 카테고리 | Podcast |
| 타입 | `POST` |

**EndPoint** : `POST /api/podcasts/episodes`

**설명** : 사용자의 주제(topic)와 설명(description)을 받아 팟캐스트모드 LangGraph 파이프라인(TIER 0→1→2→3→4)을 실행하고, 핵심 데이터를 DB에 동기 저장한 뒤 완료 신호를 반환합니다. 모든 데이터는 DB에 저장되므로 Backend가 GET API로 조회 가능합니다.

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

> 소스: `SlimPodcastResponse` (src/api/external_schemas.py)
>
> 파이프라인 실행 + DB 저장 완료 후 반환하는 **최소 응답**. 모든 데이터는 DB에 저장되므로 Backend가 GET API로 조회 가능.
> safety_alert만 직접 포함 (CRISIS 시 에피소드 미생성 → DB 미저장).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | Boolean | true | 항상 `true` |
| episode_id | String | true | 생성된 에피소드 고유 ID |
| session_id | String | true | 세션 ID |
| safety_alert | Object | false | 안전 경고 (warning/crisis 시에만 포함, safe 시 `null`) |
| safety_alert.status | String | true | `warning` 또는 `crisis` |
| safety_alert.alert_message | String | true | 안전 안내 메시지 (한국어) |
| safety_alert.helpline_info | Array | false | 도움 연결 정보 |
| safety_alert.show_emergency_button | Boolean | true | 긴급 도움 버튼 표시 여부 |
| tracing | Object | true | 추적 컨텍스트 |
| tracing.request_id | String | true | API 요청 고유 ID |
| tracing.trace_id | String | true | 분산 추적 ID |
| tracing.correlation_id | String | true | 상관관계 ID |
| tracing.timestamp | String | true | 타임스탬프 (ISO 8601) |

```json
{
    "success": true,
    "episode_id": "ep_a1b2c3d4e5f6",
    "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "safety_alert": null,
    "tracing": {
        "request_id": "req_8a9b0c1d2e3f",
        "trace_id": "trace_4a5b6c7d8e9f",
        "correlation_id": "corr_1a2b3c4d5e6f",
        "timestamp": "2026-03-16T12:00:00.000Z"
    }
}
```

> **참고**: 이전 버전의 `PodcastEpisodeResponse`는 episode, emotion, cover_image, metadata를 모두 포함했으나,
> v25(2026-03-16)에서 `SlimPodcastResponse`로 교체됨. 상세 데이터는 Backend GET API로 조회.

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
| 엔드포인트 | /api/users/{user_id}/emotions |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/users/{user_id}/emotions`

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
| emotions[].mode | String | false | 모드 (`podcast`) |
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

- **v1.2**: 엔드포인트 변경 (`/api/history/emotions` → `/api/users/{user_id}/emotions`), `user_id`를 Query → Path Variable로 이동, 응답 래퍼 변경 (`{code, message, data}` → `{success, emotions[], pagination, tracing}`), `recorded_at` → `created_at`, `limit` → `page_size` (1~100), `log_id`/`session_id` 신규 필드 추가

---

# 3. 에피소드 목록 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/users/{user_id}/podcasts/episodes |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/users/{user_id}/podcasts/episodes`

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

- **v1.2**: 엔드포인트 변경 (`/api/history/episodes` → `/api/users/{user_id}/podcasts/episodes`), `user_id` Query → Path Variable, 응답 래퍼 변경, `theme`(단수) → `themes`(배열), `primary_emotion` Required → nullable, `limit` → `page_size`, 페이지네이션 6필드 확장

---

# 4. 에피소드 단건 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/users/{user_id}/podcasts/episodes/{episode_id} |
| 카테고리 | History |
| 타입 | `GET` |
| 방향 | Backend Server → Frontend (AI 서버 미관여) |

**EndPoint** : `GET /api/users/{user_id}/podcasts/episodes/{episode_id}`

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

- **v1.2**: 엔드포인트 변경 (`/api/history/episodes/{episodeId}` → `/api/users/{user_id}/podcasts/episodes/{episode_id}`), 응답 래퍼 변경, `episode_title` → `title`, `total_duration` → `total_duration_minutes`, `tts_markers` 추가, `cover_image.interpretation` → `interpretation_text`, `cover_image.style_info` 추가, `emotion.arousal` 제거 (EmotionSummary 미포함)

---

# 5. 세션 생성

| 속성 | 값 |
|------|---|
| 상태 | 구현 완료 |
| 엔드포인트 | /api/sessions |
| 카테고리 | Session |
| 타입 | `POST` |

**EndPoint** : `POST /api/sessions`

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
| mode | String | false | 모드 (`"podcast"`) |
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
| 엔드포인트 | /api/sessions/{session_id}/close |
| 카테고리 | Session |
| 타입 | `POST` |

**EndPoint** : `POST /api/sessions/{session_id}/close`

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
| 엔드포인트 | /api/users/{user_id}/profile |
| 카테고리 | User |
| 타입 | `PATCH` |

**EndPoint** : `PATCH /api/users/{user_id}/profile`

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

*[← API_SPEC.md (인덱스)](API_SPEC.md) · [발신 API →](API_ENDPOINTS_INTERNAL.md)*

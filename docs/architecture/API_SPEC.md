# Mind-Log API 기능 명세서

> **작성일**: 2026-03-03
> **버전**: v1.0
> **상태**: 초안 (3인 리뷰 필요)

---

Base Url : (배포 후 확정)

## Swagger 경로

1. mind-log : (배포 후 확정)

---

## 카테고리

| 카테고리 | 설명 |
|---------|------|
| **Conversation** | 대화 모드 관련 API |
| **Podcast** | 팟캐스트 모드 관련 API |
| **History** | 히스토리 조회 API |
| **Common** | 공통 에러 코드 등 |

---

## API 목록

### ▼ Conversation

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [대화 요청](#1-대화-요청) | `POST` | /api/v1/conversations | 명세 완료 | |
| [대화 스트리밍](#2-대화-스트리밍-sse) | `GET` | /api/v1/conversations/stream | 명세 완료 | |

### ▼ Podcast

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [팟캐스트 에피소드 생성](#3-팟캐스트-에피소드-생성) | `POST` | /api/v1/podcasts/episodes | 명세 완료 | |

### ▼ History

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [대화 히스토리 조회](#4-대화-히스토리-조회) | `GET` | /api/v1/history/conversations | 명세 완료 | |
| [감정 추이 조회](#5-감정-추이-조회) | `GET` | /api/v1/history/emotions | 명세 완료 | |
| [에피소드 목록 조회](#6-에피소드-목록-조회) | `GET` | /api/v1/history/episodes | 명세 완료 | |
| [에피소드 단건 조회](#7-에피소드-단건-조회) | `GET` | /api/v1/history/episodes/{episodeId} | 명세 완료 | |

### ▼ Common

| 이름 | 타입 | 엔드포인트 | 상태 | 변경사항 |
|------|------|----------|------|---------|
| [공통 Error Code 명세](#공통-error-code-명세) | | | 명세 완료 | |

---

---

# 1. 대화 요청

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/conversations |
| 카테고리 | Conversation |
| 타입 | `POST` |

**EndPoint** : `POST /api/v1/conversations`

**설명** : 사용자의 메시지를 받아 AI 멘탈케어 파이프라인(TIER 0~4)을 실행하고, 분석 결과와 응답을 반환하는 핵심 API입니다. 대화모드 전용.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |
| X-Trace-Id | trace_{uuid} | (선택) 외부 분산 추적 ID. 미전송 시 서버가 생성 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| | | | | |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String (UUID) | true | 외부 시스템의 사용자 ID |
| session_id | String (UUID) | true | 외부 시스템의 세션 ID |
| mode | String | true | 실행 모드. 이 API에서는 항상 `"conversation"` |
| user_input | String | true | 사용자 메시지 (최대 2000자) |
| user_profile | Object | false | 외부에서 관리하는 사용자 정보 |
| user_profile.nickname | String | false | 사용자 닉네임 |
| user_profile.locale | String | false | 로케일 (예: `ko-KR`) |
| user_profile.timezone | String | false | 타임존 (예: `Asia/Seoul`) |

```json
{
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "mode": "conversation",
    "user_input": "오늘 하루 너무 힘들었어...",
    "user_profile": {
        "nickname": "홍길동",
        "locale": "ko-KR",
        "timezone": "Asia/Seoul"
    }
}
```

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 |
| data.response_text | String | true | AI 응답 텍스트 (AgentState.final_output) |
| data.turn_sequence | Integer | true | 세션 내 대화 순서 (1부터) |
| data.emotion | Object | true | 감정 분석 결과 |
| data.emotion.primary_emotion | String | true | 주감정 (예: `anxiety`, `sadness`, `joy`) |
| data.emotion.intensity | Float | true | 감정 강도 (0.0~1.0) |
| data.emotion.valence | Float | true | 감정 극성 (-1.0~1.0) |
| data.emotion.arousal | Float | true | 각성도 (0.0~1.0) |
| data.safety_alert | Object | false | 안전 경고. warning/crisis 시에만 포함 |
| data.safety_alert.level | String | false | `"warning"` 또는 `"crisis"` |
| data.safety_alert.message | String | false | 경고 메시지 |
| data.safety_alert.helpline_info | Array | false | 위기 시 도움 연결 정보 |
| data.visualization | Object | false | 시각화 정보. 비동기 완료 후 포함 |
| data.visualization.image_url | String | false | CDN 서명 URL |
| data.visualization.interpretation | String | false | AI 해석 텍스트 |
| data.visualization.palette | String | false | 색상 팔레트명 |
| data.trace_id | String | true | 분산 추적 ID |
| data.processing_time_ms | Integer | true | 처리 소요 시간 (ms) |

```json
{
    "code": "SUCCESS",
    "message": "대화 처리 완료",
    "data": {
        "response_text": "많이 힘드셨군요. 오늘 어떤 일이 있었는지 좀 더 이야기해 주실래요?",
        "turn_sequence": 1,
        "emotion": {
            "primary_emotion": "sadness",
            "intensity": 0.72,
            "valence": -0.65,
            "arousal": 0.35
        },
        "safety_alert": null,
        "visualization": {
            "image_url": "https://cdn.mindlog.app/vis/3fa85f64/conv/a1b2c3d4/1709471200_sadness_abc123.webp",
            "interpretation": "깊은 파랑과 회색 톤이 오늘의 지친 감정을 표현합니다.",
            "palette": "deep_ocean"
        },
        "trace_id": "trace_7f8a9b0c1d2e3f4a",
        "processing_time_ms": 1250
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "VALIDATION_ERROR",
    "message": "user_input은 필수 항목입니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 대화 처리 성공 |
| 400 Bad Request | VALIDATION_ERROR | 필수 필드 누락 또는 형식 오류 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |
| 429 Too Many Requests | RATE_LIMIT | 요청 제한 초과 |
| 500 Internal Server Error | SERVER_ERROR | 서버 내부 오류 |

---

---

# 2. 대화 스트리밍 (SSE)

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/conversations/stream |
| 카테고리 | Conversation |
| 타입 | `GET` |

**EndPoint** : `GET /api/v1/conversations/stream`

**설명** : 대화 파이프라인 실행 중 실시간 진행 상황을 SSE(Server-Sent Events)로 전달합니다. TIER별 시작/완료, 위기 감지, 최종 응답 준비, 시각화 완료 등의 이벤트를 스트리밍합니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Accept | text/event-stream | SSE 스트림 요청 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| session_id | String (UUID) | true | 세션 ID | a1b2c3d4-e5f6-7890-abcd-ef1234567890 |
| trace_id | String | false | 추적할 trace_id | trace_7f8a9b0c |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| | | | |

### Response Body

**Success (SSE event stream)**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| event_type | String | true | 이벤트 유형 |
| data | Object | true | 이벤트 데이터 |
| trace_id | String | true | 분산 추적 ID |
| timestamp | String | true | ISO 8601 타임스탬프 |

```
event: tier_start
data: {"event_type":"tier_start","data":{"tier":1,"agents":["safety","emotion","context","reasoning"]},"trace_id":"trace_7f8a9b0c","timestamp":"2026-03-03T12:00:01.123Z"}

event: crisis_detected
data: {"event_type":"crisis_detected","data":{"level":"crisis","message":"위기 상황이 감지되었습니다."},"trace_id":"trace_7f8a9b0c","timestamp":"2026-03-03T12:00:01.500Z"}

event: final_ready
data: {"event_type":"final_ready","data":{"turn_sequence":1},"trace_id":"trace_7f8a9b0c","timestamp":"2026-03-03T12:00:02.350Z"}

event: visualization_ready
data: {"event_type":"visualization_ready","data":{"image_url":"https://cdn.mindlog.app/vis/..."},"trace_id":"trace_7f8a9b0c","timestamp":"2026-03-03T12:00:05.100Z"}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "SESSION_NOT_FOUND",
    "message": "해당 session_id를 찾을 수 없습니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | SSE 스트림 연결 성공 |
| 404 Not Found | SESSION_NOT_FOUND | 세션을 찾을 수 없음 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |

---

---

# 3. 팟캐스트 에피소드 생성

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/podcasts/episodes |
| 카테고리 | Podcast |
| 타입 | `POST` |

**EndPoint** : `POST /api/v1/podcasts/episodes`

**설명** : 사용자의 주제를 받아 팟캐스트모드 파이프라인을 실행하고, AI가 생성한 에피소드 스크립트(인트로/본문/성찰/마무리 세그먼트)를 반환합니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |
| X-Trace-Id | trace_{uuid} | (선택) 외부 분산 추적 ID |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| | | | | |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String (UUID) | true | 외부 시스템의 사용자 ID |
| session_id | String (UUID) | true | 외부 시스템의 세션 ID |
| mode | String | true | 항상 `"podcast"` |
| user_input | String | true | 에피소드 주제 (최대 500자) |
| description | String | false | 추가 맥락 설명 |
| preferences | Object | false | 생성 옵션 |
| preferences.target_duration_min | Integer | false | 목표 재생 시간 (분, 기본 5) |
| preferences.tone | String | false | 톤 (`calm`, `energetic`, `reflective`) |
| preferences.depth | String | false | 깊이 (`light`, `moderate`, `deep`) |

```json
{
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "session_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "mode": "podcast",
    "user_input": "직장 스트레스 관리법에 대해 알고 싶어",
    "description": "특히 야근이 많은 상황에서...",
    "preferences": {
        "target_duration_min": 5,
        "tone": "calm",
        "depth": "moderate"
    }
}
```

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 |
| data.episode_id | String (UUID) | true | 생성된 에피소드 ID |
| data.episode_title | String | true | AI 생성 에피소드 제목 |
| data.total_duration_min | Integer | true | 총 재생 시간 (분) |
| data.segments | Array | true | 세그먼트 배열 |
| data.segments[].segment_id | String | true | 세그먼트 ID |
| data.segments[].segment_type | String | true | `intro`, `body`, `reflection`, `closing` |
| data.segments[].script_text | String | true | 스크립트 텍스트 |
| data.segments[].duration_min | Integer | true | 세그먼트 재생 시간 (분) |
| data.segments[].emotional_tone | String | true | 감정 톤 |
| data.segments[].word_count | Integer | true | 단어 수 |
| data.key_insights | Array[String] | true | 핵심 인사이트 배열 |
| data.themes | Array[String] | true | 주제 태그 배열 |
| data.emotion | Object | true | 감정 분석 요약 |
| data.emotion.primary_emotion | String | true | 주감정 |
| data.emotion.intensity | Float | true | 감정 강도 |
| data.emotion.valence | Float | true | 감정 극성 |
| data.emotion.arousal | Float | true | 각성도 |
| data.safety_alert | Object | false | 안전 경고 (warning/crisis 시만) |
| data.cover_image | Object | false | 커버 이미지 (비동기 완료 후) |
| data.cover_image.image_url | String | false | CDN 서명 URL |
| data.cover_image.interpretation | String | false | AI 해석 |
| data.trace_id | String | true | 분산 추적 ID |
| data.processing_time_ms | Integer | true | 처리 소요 시간 (ms) |

```json
{
    "code": "SUCCESS",
    "message": "에피소드 생성 완료",
    "data": {
        "episode_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
        "episode_title": "야근 속 나를 지키는 법 - 직장 스트레스 관리 가이드",
        "total_duration_min": 5,
        "segments": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "script_text": "안녕하세요, 오늘은 직장에서의 스트레스, 특히 야근이 많은 환경에서 ...",
                "duration_min": 1,
                "emotional_tone": "warm",
                "word_count": 150
            },
            {
                "segment_id": "seg_002",
                "segment_type": "body",
                "script_text": "스트레스 관리의 핵심은...",
                "duration_min": 2,
                "emotional_tone": "informative",
                "word_count": 300
            },
            {
                "segment_id": "seg_003",
                "segment_type": "reflection",
                "script_text": "이제 잠시 멈추고, 자신에게 물어보세요...",
                "duration_min": 1,
                "emotional_tone": "reflective",
                "word_count": 150
            },
            {
                "segment_id": "seg_004",
                "segment_type": "closing",
                "script_text": "오늘 이야기를 마무리하며...",
                "duration_min": 1,
                "emotional_tone": "encouraging",
                "word_count": 120
            }
        ],
        "key_insights": [
            "마이크로 휴식의 중요성",
            "경계 설정 기법",
            "자기 대화 리프레이밍"
        ],
        "themes": ["직장 스트레스", "야근", "자기 관리"],
        "emotion": {
            "primary_emotion": "anxiety",
            "intensity": 0.55,
            "valence": -0.30,
            "arousal": 0.60
        },
        "safety_alert": null,
        "cover_image": {
            "image_url": "https://cdn.mindlog.app/vis/3fa85f64/podcast/c3d4e5f6/cover_def456.webp",
            "interpretation": "잔잔한 바다와 일출이 회복의 여정을 상징합니다."
        },
        "trace_id": "trace_8a9b0c1d2e3f4a5b",
        "processing_time_ms": 3200
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "VALIDATION_ERROR",
    "message": "mode는 'podcast'여야 합니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 201 Created | - | 에피소드 생성 성공 |
| 400 Bad Request | VALIDATION_ERROR | 필수 필드 누락 또는 형식 오류 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |
| 429 Too Many Requests | RATE_LIMIT | 요청 제한 초과 |
| 500 Internal Server Error | SERVER_ERROR | 서버 내부 오류 |

---

---

# 4. 대화 히스토리 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/history/conversations |
| 카테고리 | History |
| 타입 | `GET` |

**EndPoint** : `GET /api/v1/history/conversations`

**설명** : 특정 세션의 대화 히스토리를 턴 순서대로 조회합니다. 페이지네이션을 지원합니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| user_id | String (UUID) | true | 사용자 ID | 3fa85f64-5717-4562-b3fc-2c963f66afa6 |
| session_id | String (UUID) | false | 특정 세션만 조회 | a1b2c3d4-e5f6-7890-abcd-ef1234567890 |
| limit | Integer | false | 조회 건수 (기본 20, 최대 100) | 20 |
| page | Integer | false | 페이지 번호 (기본 1) | 1 |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| | | | |

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 |
| data.conversations | Array | true | 대화 턴 배열 |
| data.conversations[].id | String (UUID) | true | 대화 턴 ID |
| data.conversations[].turn_sequence | Integer | true | 턴 순서 |
| data.conversations[].user_input | String | true | 사용자 메시지 |
| data.conversations[].ai_response | String | true | AI 응답 |
| data.conversations[].emotion | Object | true | 감정 분석 |
| data.conversations[].emotion.primary_emotion | String | true | 주감정 |
| data.conversations[].emotion.intensity | Float | true | 감정 강도 |
| data.conversations[].emotion.valence | Float | true | 극성 |
| data.conversations[].risk_level | Integer | true | 위험 레벨 (0~4) |
| data.conversations[].visualization_url | String | false | 시각화 이미지 URL |
| data.conversations[].created_at | String | true | 생성 시각 (ISO 8601) |
| data.total | Integer | true | 전체 건수 |
| data.page | Integer | true | 현재 페이지 |

```json
{
    "code": "SUCCESS",
    "message": "조회 성공",
    "data": {
        "conversations": [
            {
                "id": "d4e5f6a7-b8c9-0123-def0-123456789abc",
                "turn_sequence": 1,
                "user_input": "오늘 하루 너무 힘들었어...",
                "ai_response": "많이 힘드셨군요...",
                "emotion": {
                    "primary_emotion": "sadness",
                    "intensity": 0.72,
                    "valence": -0.65
                },
                "risk_level": 0,
                "visualization_url": "https://cdn.mindlog.app/vis/.../sadness.webp",
                "created_at": "2026-03-03T12:00:00.000Z"
            }
        ],
        "total": 15,
        "page": 1
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "VALIDATION_ERROR",
    "message": "user_id는 필수 항목입니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 조회 성공 |
| 400 Bad Request | VALIDATION_ERROR | 필수 필드 누락 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |

---

---

# 5. 감정 추이 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/history/emotions |
| 카테고리 | History |
| 타입 | `GET` |

**EndPoint** : `GET /api/v1/history/emotions`

**설명** : 사용자의 감정 추이를 기간별로 조회합니다. 프론트엔드의 감정 추이 그래프, 감정 분포 차트에 사용됩니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| user_id | String (UUID) | true | 사용자 ID | 3fa85f64-5717-4562-b3fc-2c963f66afa6 |
| days | Integer | false | 조회 기간 (일, 기본 30) | 30 |
| limit | Integer | false | 조회 건수 (기본 100) | 100 |
| page | Integer | false | 페이지 번호 (기본 1) | 1 |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| | | | |

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 |
| data.entries | Array | true | 감정 기록 배열 |
| data.entries[].primary_emotion | String | true | 주감정 |
| data.entries[].intensity | Float | true | 감정 강도 (0.0~1.0) |
| data.entries[].valence | Float | true | 극성 (-1.0~1.0) |
| data.entries[].arousal | Float | true | 각성도 (0.0~1.0) |
| data.entries[].recorded_at | String | true | 기록 시각 (ISO 8601) |
| data.summary | Object | true | 기간 요약 |
| data.summary.dominant_emotion | String | true | 기간 내 지배 감정 |
| data.summary.avg_valence | Float | true | 평균 극성 |
| data.summary.emotion_distribution | Object | true | 감정 분포 (감정명: 비율) |
| data.total | Integer | true | 전체 건수 |
| data.page | Integer | true | 현재 페이지 |

```json
{
    "code": "SUCCESS",
    "message": "조회 성공",
    "data": {
        "entries": [
            {
                "primary_emotion": "anxiety",
                "intensity": 0.65,
                "valence": -0.40,
                "arousal": 0.70,
                "recorded_at": "2026-03-03T12:00:00.000Z"
            },
            {
                "primary_emotion": "joy",
                "intensity": 0.80,
                "valence": 0.75,
                "arousal": 0.60,
                "recorded_at": "2026-03-02T18:30:00.000Z"
            }
        ],
        "summary": {
            "dominant_emotion": "anxiety",
            "avg_valence": -0.15,
            "emotion_distribution": {
                "anxiety": 0.35,
                "sadness": 0.25,
                "joy": 0.20,
                "anger": 0.10,
                "neutral": 0.10
            }
        },
        "total": 45,
        "page": 1
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "VALIDATION_ERROR",
    "message": "user_id는 필수 항목입니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 조회 성공 |
| 400 Bad Request | VALIDATION_ERROR | 필수 필드 누락 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |

---

---

# 6. 에피소드 목록 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/history/episodes |
| 카테고리 | History |
| 타입 | `GET` |

**EndPoint** : `GET /api/v1/history/episodes`

**설명** : 사용자가 생성한 팟캐스트 에피소드 목록을 조회합니다. 에피소드 목록 페이지에 사용됩니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| | | | |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| user_id | String (UUID) | true | 사용자 ID | 3fa85f64-5717-4562-b3fc-2c963f66afa6 |
| limit | Integer | false | 조회 건수 (기본 10, 최대 50) | 10 |
| page | Integer | false | 페이지 번호 (기본 1) | 1 |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| | | | |

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 |
| data.episodes | Array | true | 에피소드 배열 |
| data.episodes[].episode_id | String (UUID) | true | 에피소드 ID |
| data.episodes[].title | String | true | 에피소드 제목 |
| data.episodes[].theme | String | false | 주제 |
| data.episodes[].duration_sec | Integer | true | 재생 시간 (초) |
| data.episodes[].cover_image_url | String | false | 커버 이미지 URL |
| data.episodes[].primary_emotion | String | true | 주감정 |
| data.episodes[].created_at | String | true | 생성 시각 (ISO 8601) |
| data.total | Integer | true | 전체 건수 |
| data.page | Integer | true | 현재 페이지 |

```json
{
    "code": "SUCCESS",
    "message": "조회 성공",
    "data": {
        "episodes": [
            {
                "episode_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
                "title": "야근 속 나를 지키는 법",
                "theme": "직장 스트레스",
                "duration_sec": 300,
                "cover_image_url": "https://cdn.mindlog.app/vis/.../cover.webp",
                "primary_emotion": "anxiety",
                "created_at": "2026-03-03T12:00:00.000Z"
            }
        ],
        "total": 8,
        "page": 1
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "VALIDATION_ERROR",
    "message": "user_id는 필수 항목입니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 조회 성공 |
| 400 Bad Request | VALIDATION_ERROR | 필수 필드 누락 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |

---

---

# 7. 에피소드 단건 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/v1/history/episodes/{episodeId} |
| 카테고리 | History |
| 타입 | `GET` |

**EndPoint** : `GET /api/v1/history/episodes/{episodeId}`

**설명** : 특정 팟캐스트 에피소드의 전체 스크립트, 세그먼트, 분석 결과를 상세 조회합니다.

---

### Request Headers

| Header | Value | Description |
|--------|-------|-------------|
| Content-Type | application/json | 요청 바디는 JSON 형식 |
| Authorization | Bearer ~~~ | jwt 토큰 |

### Path Variable

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| episodeId | UUID | 조회하고자 하는 에피소드 ID | c3d4e5f6-a7b8-9012-cdef-123456789012 |

### Query Parameter

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| | | | | |

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| | | | |

### Response Body

**Success**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 응답 코드 |
| message | String | true | 응답 메시지 |
| data | Object | true | 응답 데이터 (PodcastEpisodeResponse 전체) |
| data.episode_id | String (UUID) | true | 에피소드 ID |
| data.episode_title | String | true | 에피소드 제목 |
| data.total_duration_min | Integer | true | 총 재생 시간 (분) |
| data.segments | Array | true | 세그먼트 배열 (3번 API와 동일 구조) |
| data.key_insights | Array[String] | true | 핵심 인사이트 |
| data.themes | Array[String] | true | 주제 태그 |
| data.emotion | Object | true | 감정 분석 요약 |
| data.cover_image | Object | false | 커버 이미지 정보 |
| data.trace_id | String | true | 분산 추적 ID |
| data.created_at | String | true | 생성 시각 (ISO 8601) |

```json
{
    "code": "SUCCESS",
    "message": "조회 성공",
    "data": {
        "episode_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
        "episode_title": "야근 속 나를 지키는 법 - 직장 스트레스 관리 가이드",
        "total_duration_min": 5,
        "segments": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "script_text": "안녕하세요, 오늘은...",
                "duration_min": 1,
                "emotional_tone": "warm",
                "word_count": 150
            }
        ],
        "key_insights": ["마이크로 휴식의 중요성"],
        "themes": ["직장 스트레스", "야근"],
        "emotion": {
            "primary_emotion": "anxiety",
            "intensity": 0.55,
            "valence": -0.30,
            "arousal": 0.60
        },
        "cover_image": {
            "image_url": "https://cdn.mindlog.app/vis/.../cover.webp",
            "interpretation": "잔잔한 바다와 일출이 회복의 여정을 상징합니다."
        },
        "trace_id": "trace_8a9b0c1d2e3f4a5b",
        "created_at": "2026-03-03T12:00:00.000Z"
    }
}
```

**Error**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| code | String | true | 에러 코드 |
| message | String | true | 에러 메시지 |
| data | Object | false | null |

```json
{
    "code": "NOT_FOUND",
    "message": "해당 에피소드를 찾을 수 없습니다.",
    "data": null
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 조회 성공 |
| 404 Not Found | NOT_FOUND | 에피소드를 찾을 수 없음 |
| 401 Unauthorized | AUTH_ERROR | 인증 실패 |

---

---

# 공통 Error Code 명세

모든 API에서 공통으로 사용하는 에러 코드입니다.

### 에러 응답 공통 형식

```json
{
    "code": "ERROR_CODE",
    "message": "상세 에러 메시지",
    "data": null
}
```

### 에러 코드 목록

| HTTP Status | Code | Description | 대응 |
|-------------|------|-------------|------|
| 400 | VALIDATION_ERROR | 필수 필드 누락 또는 형식 오류 | 요청 데이터 확인 |
| 400 | INVALID_MODE | mode 값이 올바르지 않음 | `conversation` 또는 `podcast` 사용 |
| 400 | INPUT_TOO_LONG | user_input이 최대 길이 초과 | 대화 2000자, 팟캐스트 500자 |
| 401 | AUTH_ERROR | 인증 실패 (토큰 만료/무효) | 토큰 갱신 후 재시도 |
| 403 | FORBIDDEN | 접근 권한 없음 | 권한 확인 |
| 404 | NOT_FOUND | 요청한 리소스를 찾을 수 없음 | ID 확인 |
| 404 | SESSION_NOT_FOUND | 세션을 찾을 수 없음 | session_id 확인 |
| 429 | RATE_LIMIT | 요청 제한 초과 | 잠시 후 재시도 |
| 500 | SERVER_ERROR | 서버 내부 오류 | 재시도 또는 관리자 문의 |
| 500 | PIPELINE_ERROR | AI 파이프라인 실행 오류 | trace_id와 함께 관리자 문의 |
| 503 | SERVICE_UNAVAILABLE | 서비스 일시 중단 | 잠시 후 재시도 |

### 재시도 정책

- **4xx 에러**: 재시도 불필요 (요청 수정 후 재전송)
- **429 에러**: `Retry-After` 헤더 값만큼 대기 후 재시도
- **5xx 에러**: 최대 3회 재시도 (exponential backoff: 1초, 2초, 4초)

---

*마지막 업데이트: 2026-03-03 v1.0*

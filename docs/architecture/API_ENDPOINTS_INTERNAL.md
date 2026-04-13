# 발신 API (AI Server → Backend Server)

> [API_SPEC.md](API_SPEC.md) 문서 모음의 일부 (v2.0)

> AI 서버가 파이프라인 실행 중/후에 Backend 서버로 데이터를 저장하는 내부 API입니다.
> 모든 발신 API는 `BackendClient` (`src/api/client.py`)를 통해 호출됩니다.

### BackendClient 통신 개요

| 메서드 | HTTP | 용도 | 사용처 |
|--------|------|------|--------|
| `save(resource, data)` | POST /api/{resource} | 데이터 저장 | _save_episode_bundle, AgentDataPublisher, LearningAgent |
| `load(resource, user_id, **params)` | GET /api/{resource} | 데이터 조회 | 미구현 (향후 확장용) |
| `load_graph_cumulative(user_id)` | GET /api/graph_nodes | 누적 그래프 조회 | publish_graph_to_rdb() |
| `put_graph_cumulative(data)` | PUT /api/graph_nodes | 누적 그래프 저장 | publish_graph_to_rdb() |

### 통신 설정

| 항목 | 값 | 환경변수 |
|------|---|---------|
| Base URL | `http://localhost:8080/api` | `BACKEND_API_URL` |
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
| 엔드포인트 | /api/podcast_episodes |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |
 
**EndPoint** : `POST /api/podcast_episodes`
 
**설명** : 팟캐스트 에피소드 생성 후 에피소드 메타데이터와 통합된 스크립트 데이터를 Backend에 비동기 저장합니다.
 
**구현 파일** : `src/api/routes/podcasts.py` → `_save_episode_bundle()`
**리소스 상수** : `RESOURCE_PODCAST_EPISODE` (`src/api/backend_resources.py`)
**호출 시점** : BackgroundTasks로 비동기 호출 (v3.0: 세그먼트 배열에서 단일 text로 구조 변경)
 
---
 
### Request Body (data 필드)
 
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| type | String | true | `"podcast_episode"` |
| data.episode_id | String | true | 에피소드 ID (`ep_{hash}`) |
| data.episode_title | String | true | 에피소드 제목 (한국어) |
| data.total_duration | Integer | true | 총 길이 (분) |
| data.total_words | Integer | true | 전체 단어 수 |
| data.script_text | String | true | **통합 스크립트 전문 (v3.0 추가)** |
| data.key_insights | Array[String] | true | 핵심 인사이트 |
| data.themes | Array[String] | true | 주제 태그 |
| data.reasoning_depth | String | true | 추론 깊이 (`full`/`standard`/`minimal`) |
| data.cover_image_url | String | false | S3 CDN URL (nullable) |
| data.trace_id | String | true | 분산 추적 ID |
| data.correlation_id | String | true | 상관관계 ID |
 
### Response Body
 
> 공통 응답 형식: `SaveResponse` (src/api/contracts.py)
 
### Status Code
 
| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 저장 성공 |
| 400 Bad Request | VALIDATION_ERROR | 요청 검증 실패 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |
 
---
 
# 15. 사용자 프로필 조회 (Internal)
 
| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/internal/users/{user_id}/profile |
| 카테고리 | Internal |
| 타입 | `GET` |
| 방향 | AI Server → Backend Server |
 
**EndPoint** : `GET /api/internal/users/{user_id}/profile`
 
**설명** : AI 서버가 개인화(ScriptPersonalizer)를 위해 Backend 서버에 저장된 사용자의 프로필 및 상호작용 통계를 조회합니다.
 
**호출 시점** : `ScriptPersonalizerAgent._query_user_profile()`
**리소스 상수** : `RESOURCE_USER_PROFILE` (`src/api/backend_resources.py`)
 
---
 
### Path Parameters
 
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| user_id | String (UUID) | true | 사용자 고유 ID |
 
### Response Body (data 필드)
 
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| user_id | String | true | 사용자 고유 ID |
| nickname | String | false | 사용자 닉네임 |
| interaction_count | Integer | true | 총 상호작용 횟수 (개인화 조건 판단용) |
| preferred_topics | Array[String] | true | 선호 주제 목록 |
| emotional_patterns | Array[String] | true | 감정 패턴 목록 |
| interaction_style | String | true | 상호작용 스타일 |
 
### Status Code
 
| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 성공 |
| 404 Not Found | NOT_FOUND | 사용자 미존재 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |
 
---

---

# 10. 감정 로그 저장

| 속성 | 값 |
|------|---|
| 상태 | 명세 완료 |
| 엔드포인트 | /api/emotion_logs |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/emotion_logs`

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
| 엔드포인트 | /api/visualizations |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/visualizations`

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
| 엔드포인트 | /api/learning |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/learning`

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
| 엔드포인트 | /api/content_analyses |
| 카테고리 | Internal |
| 타입 | `POST` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `POST /api/content_analyses`

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

# 14. 누적 그래프 조회

| 속성 | 값 |
|------|---|
| 상태 | **테스트 완료 (2026-04-09)** |
| 엔드포인트 | /api/v1/graph_nodes |
| 카테고리 | Internal |
| 타입 | `GET` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `GET /api/v1/graph_nodes?user_id={uuid}`

**설명** : EMA 계산 전 기존 누적 그래프 데이터를 조회합니다. 신규 유저는 200 + 빈 nodes/links를 반환합니다 (404 아님).

**구현 파일** : `src/api/client.py` → `load_graph_cumulative()`
**리소스 상수** : `RESOURCE_GRAPH_NODES` (`src/api/backend_resources.py`)
**호출 시점** : `publish_graph_to_rdb()` 내부 — EMA 병합 전 기존 데이터 조회

---

### Request

```
GET /api/v1/graph_nodes?user_id={uuid}
```

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `user_id` | string | Y | 사용자 UUID |

### Response Body

> 주의: 범용 `LoadResponse`가 아닌 **전용 응답 형식** 사용.

**신규 유저** (데이터 없음):
```json
{
  "code": "ok",
  "data": {
    "user_id": "...",
    "type": "graph_cumulative",
    "data": { "nodes": [], "links": [] }
  }
}
```

**기존 유저**:
```json
{
  "code": "ok",
  "data": {
    "user_id": "...",
    "type": "graph_cumulative",
    "data": {
      "nodes": [
        {
          "label": "업무과부하",
          "grp": "work_structure",
          "weight": 0.81,
          "mention_count": 3,
          "trend": "increasing",
          "first_seen": "2026-04-08T10:00:00",
          "last_seen": "2026-04-08T10:30:00"
        }
      ],
      "links": [
        {
          "source_label": "업무과부하",
          "source_grp": "work_structure",
          "target_label": "번아웃",
          "target_grp": "emotional_exhaustion",
          "weight": 3,
          "relationship": "causes",
          "first_seen": "2026-04-08T10:00:00",
          "last_seen": "2026-04-08T10:30:00"
        }
      ]
    }
  }
}
```

**AI 코드 파싱**: `body["data"]["data"]` (이중 중첩) → `GraphCumulativeData.model_validate()`

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 정상 조회 (신규 유저도 200) |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

# 15. 누적 그래프 저장 (UPSERT)

| 속성 | 값 |
|------|---|
| 상태 | **테스트 완료 (2026-04-09)** |
| 엔드포인트 | /api/v1/graph_nodes |
| 카테고리 | Internal |
| 타입 | `PUT` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `PUT /api/v1/graph_nodes`

**설명** : AI 서버가 EMA 계산 완료 후 누적 그래프를 Backend에 저장(UPSERT)합니다. UPSERT 키: `user_id + label + grp` (노드), `user_id + source_label + source_grp + target_label + target_grp` (링크).

**구현 파일** : `src/api/client.py` → `put_graph_cumulative()`
**리소스 상수** : `RESOURCE_GRAPH_NODES` (`src/api/backend_resources.py`)
**타입 상수** : `TYPE_GRAPH_CUMULATIVE` = `"graph_cumulative"`
**호출 시점** : `publish_graph_to_rdb()` 내부 — EMA 병합 후 결과 저장

---

### Request Body

> 주의: 범용 `SaveRequest`를 사용하지 않는 전용 형식. `session_id`/`timestamp`를 포함하지 않음.

```json
{
  "user_id": "string (UUID)",
  "type": "graph_cumulative",
  "data": {
    "nodes": [
      {
        "label": "업무과부하",
        "grp": "work_structure",
        "weight": 0.81,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-09T10:30:00"
      }
    ],
    "links": [
      {
        "source_label": "업무과부하",
        "source_grp": "work_structure",
        "target_label": "번아웃",
        "target_grp": "emotional_exhaustion",
        "weight": 3,
        "relationship": "causes",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-09T10:30:00"
      }
    ]
  }
}
```

**BE 거부 필드** (포함 시 400 `GRAPH_REQUEST_SCHEMA_MISMATCH`):
- `session_id` — 누적 데이터는 유저 단위, 세션 무관
- `timestamp` — 노드/링크별 `first_seen`/`last_seen`으로 충분

**BE 필수 필드**:
- `nodes[].first_seen`, `nodes[].last_seen` — 없으면 400
- `links[].source_grp`, `links[].target_grp` — 없으면 400
- `links[].first_seen`, `links[].last_seen` — 없으면 400

### Response Body

```json
{ "code": "ok", "message": "성공" }
```

> 주의: 범용 `SaveResponse`가 아닌 전용 응답. `success` 대신 `code` 필드 사용.

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | ok | 저장/갱신 성공 |
| 400 Bad Request | GRAPH_REQUEST_SCHEMA_MISMATCH | 허용하지 않는 필드 포함 |
| 400 Bad Request | GRAPH_NODE_LABEL_REQUIRED | nodes[].label 누락 |
| 400 Bad Request | GRAPH_INVALID_GROUP | 유효하지 않은 grp 값 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

---

## Load API — 데이터 조회

> 출처: BACKEND_API_CONTRACT.md에서 통합 (v1.2)

### 공통 요청 형식

```
GET /api/{resource}?user_id={uuid}&type={type}&limit={n}&page={p}
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

# 16. 지식 문서 원문 조회

| 속성 | 값 |
|------|---|
| 상태 | 명세 작성 중 (Backend 확정 필요) |
| 엔드포인트 | /api/internal/knowledge |
| 카테고리 | Internal |
| 타입 | `GET` |
| 방향 | AI Server → Backend Server |

**EndPoint** : `GET /api/internal/knowledge?ids={chunk_id1},{chunk_id2},...`

**설명** : KnowledgeAgent가 Pinecone 벡터 검색으로 선정한 top_k 청크 ID를 기반으로 Backend RDB의 `knowledge_base` 테이블에서 청크 텍스트 및 메타데이터를 조회한다. 청크 ID는 Pinecone의 `_id`와 동일한 값을 사용한다.

**구현 파일** : `src/agents/podcast/knowledge.py` → `_fetch_documents_from_backend()`
**리소스 상수** : `RESOURCE_KNOWLEDGE` (`src/api/backend_resources.py`)
**호출 시점** : `KnowledgeAgent.search()` — Pinecone 검색 직후, TextGen 호출 이전

---

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ids` | String (comma-separated) | true | 조회할 청크 ID 목록 (최대 10개, Pinecone `_id` 값과 동일) |

**요청 예시**:
```
GET /api/internal/knowledge?ids=cbt_chunk_042,stress_chunk_015
```

### Response Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | Boolean | true | 성공 여부 |
| `data` | Array[Object] | true | 청크 목록 |
| `data[].id` | String | true | 청크 ID (Pinecone ID와 동일) |
| `data[].title` | String | true | 문서 제목 |
| `data[].content` | String | true | 청크 텍스트 (PDF에서 추출된 실제 내용) |
| `data[].page` | Integer | false | 출처 페이지 번호 |
| `data[].source` | String | true | 원본 PDF 파일명 (예: `cbt_guide.pdf`) |
| `data[].domain` | String | true | 도메인 (예: `mental_health`) |

**응답 예시**:
```json
{
  "success": true,
  "data": [
    {
      "id": "cbt_chunk_042",
      "title": "CBT 기법 가이드",
      "content": "인지행동치료에서 인지 왜곡이란 현실을 왜곡하여 지각하는 사고 패턴을 말한다...",
      "page": 42,
      "source": "cbt_guide.pdf",
      "domain": "mental_health"
    },
    {
      "id": "stress_chunk_015",
      "title": "스트레스 관리 매뉴얼",
      "content": "직장 내 스트레스의 주요 원인으로는 업무 과부하, 역할 모호성...",
      "page": 15,
      "source": "stress_management.pdf",
      "domain": "mental_health"
    }
  ]
}
```

### Status Code

| Status | Code | Description |
|--------|------|-------------|
| 200 OK | - | 정상 조회 (일부 ID가 없어도 200, 해당 ID 제외하고 반환) |
| 400 Bad Request | VALIDATION_ERROR | `ids` 파라미터 누락 또는 10개 초과 |
| 500 Internal Server Error | SERVER_ERROR | Backend 서버 내부 오류 |

> **NOTE**: 요청한 ID 중 일부가 RDB에 없어도 404가 아닌 200으로 응답하고, 존재하는 청크만 `data` 배열에 포함합니다.

---

*[← 수신 API](API_ENDPOINTS_RECEIVING.md) · [API_SPEC.md (인덱스)](API_SPEC.md) · [공통 →](API_COMMON.md)*


# 현재 코드에 구현된 API 전수 목록

기준 코드: `/Users/jun/Downloads/실무통합/lang_develop`
작성일: 2026-04-09

---

## 1. 수신 API (외부 → AI Server)

FastAPI 라우터로 구현된 수신 엔드포인트.

### 1-1. Health Check (ALB/Docker용)

| # | 방향 | 메서드 + 경로 | Request | Response | 소스 |
|---|------|-------------|---------|---------|------|
| 1 | ALB→AI | `GET /health` | 없음 | `{"status": "ok"}` | `routes/health.py:30` |
| 2 | Docker→AI | `GET /health/ready` | 없음 | `{"status": "ready", "components": {"graph": "ok", "backend_client": "ok"}, "storage_mode": "..."}` | `routes/health.py:40` |

### 1-2. 세션 관리 (`/api/sessions`)

| # | 방향 | 메서드 + 경로 | Request | Response | 소스 |
|---|------|-------------|---------|---------|------|
| 3 | Backend→AI | `POST /api/sessions` | `SessionCreateRequest` (user_id, mode="podcast", tracing?) | `SessionCreateResponse` (success, session_id, mode, created_at, tracing) | `routes/sessions.py:42` |
| 4 | Backend→AI | `POST /api/sessions/{session_id}/close` | `SessionCloseRequest` (user_id, session_id, feedback?, tracing?) | `{"success": true, "message": "..."}` | `routes/sessions.py:69` |
| 5 | Backend→AI | `POST /api/sessions/{session_id}/personalization-context` ⚠️ 경로 TBD | `PersonalizationContextRequest` (session_id, keywords, title, description) | `{"success": true}` | `routes/sessions.py:91` |

### 1-3. 팟캐스트 에피소드 (`/api/podcasts`)

| # | 방향 | 메서드 + 경로 | Request | Response | 소스 |
|---|------|-------------|---------|---------|------|
| 6 | Backend→AI | `POST /api/podcasts/episodes` | `PodcastRequest` (user_id, session_id, situation, thought, action, colleague_reaction?, learning_pattern?, tracing?) | `SlimPodcastResponse` (success, episode_id, session_id, safety_alert?, tracing) | `routes/podcasts.py:236` |
| 7 | Backend→AI | `POST /api/podcasts/episodes/stream` | `PodcastRequest` (동일) | SSE 스트림 (`connected`→`tier_start`→`agent_complete`→`tier_end`→`result`→`done`) | `routes/podcasts.py:368` |

### 1-4. 내부 그래프 조회 (`/internal/graph`)

| # | 방향 | 메서드 + 경로 | Request | Response | 소스 |
|---|------|-------------|---------|---------|------|
| 8 | Backend→AI | `GET /internal/graph/users/{user_id}/data?limit=100` | query: limit (default 100, max 500) | `{"success": true, "data": {"nodes": [...], "links": [...], "frequent_keywords": [...], "category_distribution": {...}}}` | `routes/graph.py:58` |

⚠️ **주의**: [이관 예정] Neo4j 백엔드 이관 시 이 라우터 전체 삭제 예정.

### 1-5. 모니터링

| # | 방향 | 메서드 + 경로 | Request | Response | 소스 |
|---|------|-------------|---------|---------|------|
| 9 | Prometheus→AI | `GET /metrics` | 없음 | Prometheus 메트릭 텍스트 | `main.py:207` |

---

## 2. 발신 API (AI Server → Backend Server)

`BackendClient` 클래스 (`src/api/client.py`)의 public 메서드.

공통 설정:
- **base_url** 기본값: `http://localhost:8080/greenroom/ingest/ai`
- **profile_base_url**: `http://localhost:8080` (호스트만)
- **timeout**: 5초 (settings.api_timeout)
- **HTTP 클라이언트**: `httpx.AsyncClient`

### 2-1. SaveRequest 경유 (재시도 3회 자동)

| # | 방향 | 메서드 + 경로 | Request (SaveRequest) | Response (SaveResponse) | 사용처 |
|---|------|-------------|---------------------|----------------------|------|
| 1 | AI→Backend | `POST {base_url}/{resource}` | `{user_id, session_id, type, data, timestamp}` | `{success, id, message}` | `save()` |
| 2 | AI→Backend | `GET {base_url}/{resource}?user_id={uuid}&...` | query params | `{success, data[], total, page}` | `load()` |
| 3 | AI→Backend | `PUT {base_url}/{resource}` | SaveRequest (동일) | SaveResponse (동일) | `update()` — UPSERT |

### 2-2. 사용자 프로필 조회 (호스트만)

| # | 방향 | 메서드 + 경로 | Request | Response | 사용처 |
|---|------|-------------|---------|---------|------|
| 4 | AI→Backend | `GET {profile_base_url}/internal/users/{user_id}/profile` | 없음 | `dict[str, Any]` (사용자 프로필) | `get_user_profile()` — Script Personalizer |

### 2-3. 수집 API (SaveRequest 미사용, 직접 전송)

| # | 방향 | 메서드 + 경로 | Request | Response | 사용처 |
|---|------|-------------|---------|---------|------|
| 5 | AI→Backend | `POST {base_url}/tickets/mind-frequencies` | `{session_id, keywords, description}` | 없음 (fire-and-forget) | `ingest_mind_frequencies()` — Content Analyzer |
| 6 | AI→Backend | `POST {base_url}/podcast_episodes` | `{session_id, image_url, texts, title, summary, keywords}` | 없음 (부분 실패 허용) | `ingest_podcast_episodes()` — `_save_core_data()` |

---

## 3. 실제 호출되는 리소스 경로 (save/load 대상)

현재 파이프라인이 실제로 호출하는 리소스만 표시.

| # | 방향 | 전체 URL | type | 호출 위치 |
|---|------|---------|------|---------|
| 1 | AI→Backend | `POST /greenroom/ingest/ai/podcast_metadata` | `podcast_metadata` | `routes/podcasts.py` `_save_core_data()` |
| 2 | AI→Backend | `POST /greenroom/ingest/ai/visualizations` | `visualization` | `routes/podcasts.py` `_save_core_data()` |
| 3 | AI→Backend | `POST /greenroom/ingest/ai/content_analyses` | `content_analysis` | `agents/content_analyzer.py` (Publisher 경유) |
| 4 | AI→Backend | `POST /greenroom/ingest/ai/emotion_logs` | `emotion_log` | `agents/emotion.py` (Publisher 경유) |
| 5 | AI→Backend | `POST /greenroom/ingest/ai/learning` | `learning` | `agents/learning.py` |
| 6 | AI→Backend | `POST /greenroom/ingest/ai/graph_analyses` | `graph_analysis` | `agents/podcast_reasoning.py` (Publisher 경유) |
| 7 | AI→Backend | `POST /greenroom/ingest/ai/tickets/mind-frequencies` | (없음) | `agents/content_analyzer.py` |
| 8 | AI→Backend | `POST /greenroom/ingest/ai/podcast_episodes` | (없음) | `routes/podcasts.py` `_save_core_data()` |

---

## 4. 리소스 상수 전수 (`backend_resources.py`)

### 활성 (현재 파이프라인 사용)
```python
RESOURCE_LEARNING            = "learning"
RESOURCE_PODCAST_METADATA    = "podcast_metadata"
RESOURCE_PODCAST_EPISODES    = "podcast_episodes"     # 수집 API (SaveRequest 미사용)
RESOURCE_CONTENT_ANALYSIS    = "content_analyses"
RESOURCE_EMOTION_LOG         = "emotion_logs"
RESOURCE_VISUALIZATION       = "visualizations"
RESOURCE_GRAPH_ANALYSIS      = "graph_analyses"       # GoT 그래프 분석
RESOURCE_MIND_FREQUENCIES    = "tickets/mind-frequencies"  # 수집 API
RESOURCE_GRAPH_EPISODES      = "graph_nodes/episodes" # 누적 그래프 노드
```

### 협의 필요 (정의만 있음)
```python
RESOURCE_SESSION             = "sessions"             # TODO: 백엔드 팀 협의
```

### 프록시 모드 전용 (STORAGE_MODE=proxy/hybrid)
```python
RESOURCE_VECTOR_SEARCH       = "vector/search"        # TODO: 엔드포인트 확인
RESOURCE_GRAPH_QUERY         = "graph/query"          # TODO: 엔드포인트 확인
RESOURCE_STORAGE_UPLOAD      = "storage/upload"       # TODO: 이미지 업로드 엔드포인트
RESOURCE_STORAGE_OBJECT      = "storage/object"       # TODO: S3 객체 조회
```

### Save 타입 (SaveRequest.type)
```python
TYPE_PODCAST_METADATA  = "podcast_metadata"
TYPE_EMOTION_LOG       = "emotion_log"
TYPE_VISUALIZATION     = "visualization"
TYPE_LEARNING          = "learning"
TYPE_CONTENT_ANALYSIS  = "content_analysis"
TYPE_GRAPH_ANALYSIS    = "graph_analysis"
TYPE_GRAPH_EPISODE     = "graph_episode"
```

---

## 5. 명세서 v3 커버리지 점검

**현재 v3에 명세 있음 (11건)**:
- ✅ 세션 생성 (#3)
- ✅ 세션 종료 (#4)
- ✅ 개인화 맥락 수신 (#5)
- ✅ 팟캐스트 에피소드 생성 (#6)
- ✅ 에피소드 단건 조회 (별도 조회 API)
- ✅ 에피소드 저장 (내부) — `podcast_metadata` (발신 #1)
- ✅ 콘텐츠 분석 저장 (내부) (발신 #3)
- ✅ 감정 로그 저장 (내부) (발신 #4)
- ✅ 시각화 메타 저장 (내부) (발신 #2)
- ✅ 학습 데이터 저장 (내부) (발신 #5)
- ✅ mind-frequencies 수집 (내부) (발신 #7)
- ✅ podcast_episodes 수집 (내부) (발신 #8)

**v3에 명세 없음 (⚠️ 누락 후보)**:
- ❌ **`GET /health`** — ALB 헬스체크 (v2 "헬스 체크" 파일은 있음, v3 복사 확인 필요)
- ❌ **`GET /health/ready`** — Docker Readiness Probe (v2 "헬스 체크"와 통합 가능)
- ❌ **`POST /api/podcasts/episodes/stream`** — SSE 스트리밍 (v2에 있었는지 확인 필요)
- ❌ **`GET /internal/graph/users/{user_id}/data`** — Neo4j 그래프 조회 (v2 "내부 데이터 조회 API (Internal).md"에 포함되어 있을 가능성)
- ❌ **`GET /metrics`** — Prometheus 메트릭 (v2 "Prometheus 메트릭" 파일 있음)
- ❌ **`POST {resource}/graph_analyses`** — GoT 분석 저장 (Podcast Reasoning Agent가 호출하는데 별도 명세 없음)
- ❌ **`GET {profile_base_url}/internal/users/{user_id}/profile`** — 사용자 프로필 조회 (Backend 담당 API, AI는 호출자)
- ❌ **`PUT {base_url}/{resource}`** — update/UPSERT (현재 호출되지 않지만 BackendClient에 메서드 존재)
- ❌ **`GET {base_url}/{resource}`** — load (현재 호출되지 않지만 BackendClient에 메서드 존재)

---

## 6. 주의점

### 6-1. 호출되지만 명세서가 없는 API
- **graph_analyses 저장**: Podcast Reasoning Agent가 AgentDataPublisher를 통해 호출 (`RESOURCE_GRAPH_ANALYSIS = "graph_analyses"`). v3 명세서에 관련 파일이 없음 — 추가 필요할 수 있음.

### 6-2. 정의만 있고 호출되지 않는 리소스
- `RESOURCE_GRAPH_EPISODES = "graph_nodes/episodes"` — 누적 그래프 노드 리소스. 현재 호출 경로 없음.
- 프록시 모드 4개(`vector/search`, `graph/query`, `storage/upload`, `storage/object`) — STORAGE_MODE=proxy일 때만 활성화, TODO 상태.

### 6-3. 경로 TBD
- **개인화 맥락 수신** (`POST /api/sessions/{session_id}/personalization-context`): 엔드포인트 경로 TBD (임시). Backend 팀과 협의 후 확정 필요.

### 6-4. 백엔드가 제공하는 API (AI는 호출자)
- `GET /internal/users/{user_id}/profile` — 사용자 프로필 조회. Backend 책임 API이므로 AI 쪽 명세서는 "호출 규약" 수준으로만 기록하면 됨.

---

## 요약

| 구분 | 개수 |
|------|------|
| 수신 엔드포인트 | 9개 |
| 발신 메서드 (BackendClient) | 6개 |
| 실제 호출 리소스 | 8개 |
| v3 명세서 커버리지 | 11건 명세 있음 |
| **누락 후보** | **4~9건** (주로 Health, Metrics, Internal Graph, Stream, graph_analyses) |

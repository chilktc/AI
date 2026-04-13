# Backend API 전수 테스트 결과

**Goal:** AI→Backend 발신 API 10개를 프로덕션 환경에서 전수 테스트하여 실제 동작을 검증하고, 코드 버그를 수집·분류한다.

**Architecture:** Chrome MCP → AWS SSM Session Manager(EC2 app-2) → `docker exec mindlog-ai-service python3` 로 각 엔드포인트를 직접 호출. httpx 동기 클라이언트 사용.

**Tech Stack:** Chrome MCP (`mcp__Claude_in_Chrome__*`), AWS SSM Session Manager, Python 3.11.15, httpx 0.28.1

**실행 일시:** 2026-04-13

---

## 실제 엔드포인트 목록 (검증 완료)

| # | 메서드 | 실제 엔드포인트 | BackendClient 메서드 | 결과 |
|---|--------|----------------|---------------------|------|
| 1 | GET | `/internal/users/{user_id}/profile` | `get_user_profile()` | ✅ 200 |
| 2 | GET | `/api/v1/graph_nodes?user_id=X` | `load_graph_cumulative()` | ✅ 200 |
| 3 | PUT | `/api/v1/graph_nodes` | `put_graph_cumulative()` | ✅ 200 |
| 4 | POST | `/greenroom/ingest/ai/podcast_metadata` | `save(RESOURCE_PODCAST_METADATA)` | ✅ 200 |
| 5 | POST | `/greenroom/ingest/ai/emotion_logs` | `save(RESOURCE_EMOTION_LOG)` | ✅ 200 |
| 6 | POST | `/greenroom/ingest/ai/visualizations` | `save(RESOURCE_VISUALIZATION)` | ✅ 200 |
| 7 | POST | `/greenroom/ingest/ai/learning` | `save(RESOURCE_LEARNING)` | ✅ 200 |
| 8 | POST | `/greenroom/ingest/ai/content_analyses` | `save(RESOURCE_CONTENT_ANALYSIS)` | ✅ 200 |
| 9 | POST | `/greenroom/ingest/ai/mind-frequencies` | `ingest_mind_frequencies()` | ✅ 201 |
| 10 | POST | `/greenroom/ingest/ai/podcast_episodes` | `ingest_podcast_episodes()` | ⚠️ 스키마 통과 / FK 실패 |

> API 10은 `text` 단일 문자열로 전송 시 스키마 통과 확인. 테스트 세션 ID가 존재하지 않아 `DOES_NOT_EXIST_TICKET` 반환 (실 데이터로는 정상 동작 예상).

---

## 테스트 결과 상세

### 통과 (9/10)
- API 1~9 모두 실제 엔드포인트 호출 성공
- API 9(`mind-frequencies`) — 올바른 경로·페이로드 확인 후 201 반환

### 스키마 검증 통과 (1/10)
- API 10(`podcast_episodes`) — `text` 단수 string 으로 변경 시 VALIDATION_ERROR 해소, FK 오류만 잔존

---

## 확인된 코드 버그 (4건)

### B-1: `src/api/backend_resources.py`

```python
# Before
RESOURCE_MIND_FREQUENCIES = "tickets/mind-frequencies"

# After
RESOURCE_MIND_FREQUENCIES = "mind-frequencies"
```

### B-2: `src/api/client.py` — `ingest_mind_frequencies()`

```python
# Before
json={
    "session_id": session_id,   # snake_case → 백엔드 VALIDATION_ERROR
    "keywords": keywords,
    "description": description,
},

# After
json={
    "sessionId": session_id,    # camelCase — 백엔드 요구 스펙
    "keywords": keywords,
    "description": description,
},
```

### B-3: `src/api/client.py` — `ingest_podcast_episodes()`

```python
# Before
json={
    "session_id": session_id,
    "image_url": image_url,
    "texts": texts,             # 배열 → 백엔드 VALIDATION_ERROR
    "title": title,
    "summary": summary,
    "keywords": keywords,
},

# After
json={
    "session_id": session_id,
    "image_url": image_url,
    "text": "\n".join(texts),   # 단일 문자열 — 백엔드 요구 스펙
    "title": title,
    "summary": summary,
    "keywords": keywords,
},
```

> 구분자(`"\n"` vs `" "`)는 백엔드 팀과 최종 확인 필요.

### B-4: `src/api/client.py` — graph_nodes 경로 분리

`__init__`에 `_graph_base_url` 추가:

```python
# Before
self._base_url = base_url or settings.api_base_url
parsed = urlparse(self._base_url)
self._profile_base_url = f"{parsed.scheme}://{parsed.netloc}"

# After
self._base_url = base_url or settings.api_base_url
parsed = urlparse(self._base_url)
self._profile_base_url = f"{parsed.scheme}://{parsed.netloc}"
self._graph_base_url = f"{parsed.scheme}://{parsed.netloc}/api/v1"
```

`load_graph_cumulative()` / `put_graph_cumulative()` URL 수정:

```python
# Before
f"{self._base_url}/graph_nodes"       # /greenroom/ingest/ai/graph_nodes → 404

# After
f"{self._graph_base_url}/graph_nodes" # /api/v1/graph_nodes → 200
```

---

## 코드 수정 완료 현황 (2026-04-13, commit 884c18c)

| 버그 | 파일 | 수정 내용 | 상태 |
|------|------|----------|------|
| B-1 | `backend_resources.py` | `RESOURCE_MIND_FREQUENCIES` 경로 수정 | ✅ 완료 (이전 세션) |
| B-2 | `client.py` | `"session_id"` → `"sessionId"` (camelCase) | ✅ 완료 |
| B-3 | `client.py`, `routes/podcasts.py` | `title` 파라미터 추가 | ✅ 완료 |
| B-4 | `client.py` | `_graph_base_url = host/api/v1` 분리, graph_nodes URL 교정 | ✅ 완료 |
| 추가 | `content_analyzer.py`, `client.py` | `user_summaries` 호출 제거 (mind-frequencies 통합) | ✅ 완료 |
| 추가 | `api_proxy.py` | `GraphProxyClient.execute_query()` 미구현 엔드포인트 호출 제거 | ✅ 완료 |

---

## graph_nodes 아키텍처 확정 (2026-04-13)

**확인 사항:**
- Neo4j는 AI 서버 내부 인프라 — 백엔드 경유 불필요
- `graph/query` 엔드포인트는 백엔드에 없음 (원래부터 미구현) → 제거 완료
- 백엔드와 통신하는 그래프 관련 API는 **GET/PUT graph_nodes 2개뿐**

**현재 코드 상태 (확정):**

```
GoT 추론 결과 저장 흐름:
  podcast_reasoning.py → publish_graph_to_rdb()
    → BackendClient.load_graph_cumulative()  : GET  http://host/api/v1/graph_nodes
    → EMA 병합 (src/api/graph_cumulative.py)
    → BackendClient.put_graph_cumulative()   : PUT  http://host/api/v1/graph_nodes
```

**GraphProxyClient.execute_query() 동작:**
- proxy 모드에서 Cypher 쿼리가 호출되면 빈 결과(`[]`) 반환 (HTTP 전송 없음)
- GoT 에피소드 노드의 Neo4j 직접 저장은 `storage.mode: local/hybrid` 시 활성화

---

## 운영환경 설정 버그

| 항목 | 이전 값 (잘못됨) | 올바른 값 | 조치 |
|------|----------------|---------|------|
| `BACKEND_API_URL` (GitHub Secret) | `http://10.7.10.20:8080/api/v1` | `http://10.7.10.20:8080/greenroom/ingest/ai` | ✅ 수정 완료 (2026-04-13) |

> **주의:** `BACKEND_API_URL` 변경 후 `/greenroom/ingest/ai/graph_nodes`로 호출하면 **500 INTERNAL_SERVER_ERROR** 발생 확인.
> B-4 코드 수정 전 배포 시 graph_nodes GET/PUT 전부 실패. **B-4는 긴급 수정 대상.**

---

## 관련 파일

- `src/api/client.py` — BackendClient (B-2, B-3, B-4 수정 대상)
- `src/api/backend_resources.py` — RESOURCE_* 상수 (B-1 수정 대상)
- `src/api/contracts.py` — SaveRequest, SaveResponse, GraphCumulativeData
- `config/settings.yaml` — `api.timeout: 10`, `api_base_url` 기본값

---

## CLI 재검증 절차 (코드 배포 후)

```bash
# graph_nodes — /api/v1 경로 확인
sudo docker exec mindlog-ai-service python3 -c "
import httpx
r = httpx.get('http://10.7.10.20:8080/api/v1/graph_nodes', params={'user_id':'<real_user_id>'}, timeout=10)
print(r.status_code, r.text[:200])
"

# mind-frequencies — camelCase sessionId 확인
sudo docker exec mindlog-ai-service python3 -c "
import httpx
r = httpx.post('http://10.7.10.20:8080/greenroom/ingest/ai/mind-frequencies', json={'sessionId':'<real_session_id>','keywords':['stress'],'description':'test'}, timeout=10)
print(r.status_code, r.text[:200])
"
```

# 변경이력 v21

> 날짜: 2026-03-09

---

## v21: 저장소 추상화 + 관측성 인프라 — Zone C + Zone D(Backend) 구현

### 배경

v20에서 테스트 스위트 구조 개선(361→270)을 완료한 후, AWS EC2 배포를 위한
외부 인프라 전환 작업을 시작하였다. INFRA_DEPLOYMENT_GUIDE.md와
AI_Team_Work_Zone_Assignment.md를 기반으로 다음 범위를 구현한다:

1. **C-1: 구조화 JSON 로깅** — `APP_ENV=production`에서 JSON 포맷 자동 전환 (OpenSearch 수집용)
2. **C-2: Prometheus 메트릭 엔드포인트** — `GET /metrics` + 5개 메트릭 (요청 수, CRISIS 이벤트, 파이프라인/에이전트 실행 시간, LLM 토큰)
3. **C-3: S3 클라이언트** — boto3 기반 읽기+쓰기 (직접 업로드 + Backend 프록시 이중 지원)
4. **4-2: Backend API 리소스 매핑** — `TODO(backend):` 주석으로 협의 포인트 26개 표시
5. **4-3: 저장소 전략 패턴** — `STORAGE_MODE=local|proxy|hybrid` 환경별 팩토리
6. **4-4: S3 이미지 업로드** — 직접 업로드(S3Client) + Backend 경유(StorageProxyClient) 이중 경로

**원칙**: Protected 파일(agent_state.py, message.py, contracts.py, workflow.py) 수정 없음.
Shared Infrastructure(base_agent.py, llm_client.py, prompt_loader.py, loader.py) 기존 시그니처 변경 없음.

---

### 신규 파일 (10개)

| 파일 | Zone | 내용 |
|------|------|------|
| `src/db/__init__.py` | 4-3 | DB 패키지 — 4개 ABC + 4개 팩토리 함수 export |
| `src/db/base.py` | 4-3 | 추상 인터페이스 4종 — `BaseVectorClient`, `BaseGraphClient`, `BaseRDBClient`, `BaseStorageClient` + `_AsyncCloseable` ABC |
| `src/db/pinecone_client.py` | 4-3 | `PineconeClient(BaseVectorClient)` — pinecone-client SDK + `asyncio.to_thread()` |
| `src/db/neo4j_client.py` | 4-3 | `Neo4jClient(BaseGraphClient)` — neo4j `AsyncGraphDatabase` 네이티브 async |
| `src/db/mysql_client.py` | 4-3 | `MySQLClient(BaseRDBClient)` — PyMySQL + `asyncio.to_thread()` |
| `src/db/s3_client.py` | C-3, 4-4 | `S3Client(BaseStorageClient)` — boto3 + `asyncio.to_thread()`, 읽기+쓰기 |
| `src/db/api_proxy.py` | 4-2, 4-3 | Backend API 프록시 4종 — `VectorProxyClient`, `GraphProxyClient`, `RDBProxyClient`, `StorageProxyClient` |
| `src/db/factory.py` | 4-3 | 환경별 팩토리 — `create_vector_client()`, `create_graph_client()`, `create_rdb_client()`, `create_storage_client()` |
| `src/monitoring/prometheus.py` | C-2 | `MetricsCollector` (lazy-init) + `get_metrics_router()` → `GET /metrics` |
| `src/api/backend_resources.py` | 4-2 | Backend API 리소스 경로 상수 + `TODO(backend)` 주석 |

### 수정 파일 (5개)

| 파일 | Zone | 변경 내용 |
|------|------|----------|
| `src/utils/logger.py` | C-1 | `_is_production()`, `_create_json_formatter()` 추가. `_create_formatter()`에서 `APP_ENV=production` 분기. `get_agent_logger()` 시그니처 불변 |
| `requirements.txt` | C-1, C-2 | `python-json-logger>=2.0.0`, `prometheus-client>=0.20.0` 추가 |
| `.env.example` | 4-3 | `STORAGE_MODE=local`, `S3_MODE` 섹션 추가 |
| `config/settings.yaml` | 4-3 | `storage:` 섹션 추가 (mode, s3 bucket/prefix, pinecone index 이름) |
| `config/loader.py` | 4-3 | `storage_mode`, `s3_bucket`, `s3_upload_prefix` 프로퍼티 추가 (기존 시그니처 불변) |

---

### 주요 아키텍처

#### 저장소 전략 패턴 (Strategy + Factory)

```
STORAGE_MODE 환경변수
    ↓
factory.py
    ├── "local"  → 직접 클라이언트 (Pinecone, Neo4j, MySQL, S3)
    ├── "proxy"  → Backend API 프록시 (VectorProxy, GraphProxy, RDBProxy, StorageProxy)
    └── "hybrid" → Pinecone+Neo4j 직접, MySQL 프록시
                   S3_MODE로 S3만 별도 제어 가능

추상 인터페이스 (base.py):

  _AsyncCloseable (ABC)         ← close() + __aenter__/__aexit__
      ├── BaseVectorClient      ← query(), upsert()
      ├── BaseGraphClient       ← execute_query()
      ├── BaseRDBClient         ← fetch(), execute()
      └── BaseStorageClient     ← get_object(), put_object(), list_objects(), generate_presigned_url()

에이전트 코드에서 사용:
  from src.db import create_vector_client
  client = create_vector_client()    # STORAGE_MODE에 따라 자동 선택
  results = await client.query(...)
```

#### Prometheus 메트릭 구조

```
MetricsCollector (lazy-init: _ensure_metrics() classmethod)
    │
    ├── mindlog_requests_total          Counter  (mode, status)
    ├── mindlog_crisis_events_total     Counter  (mode, risk_level)
    ├── mindlog_pipeline_duration_seconds  Histogram  (mode)
    ├── mindlog_agent_duration_seconds     Histogram  (agent, tier)
    └── mindlog_llm_tokens_total        Gauge    (agent, direction)
         │
    record_pipeline(PipelineMetrics) ← 텔레메트리 콜백에서 호출
    record_agent(AgentMetric)       ← 텔레메트리 콜백에서 호출
         │
    get_metrics_router() → FastAPI APIRouter → GET /metrics
         │
    Zone A 인수: main.py에서 app.include_router(get_metrics_router())
```

#### JSON 로깅 분기 (C-1)

```
_create_formatter()
    │
    ├── APP_ENV == "production"
    │       └── _create_json_formatter()
    │               → JsonFormatter(timestamp, level, logger, message)
    │               → OpenSearch / FluentBit 수집
    │
    └── 그 외 (development)
            → 평문 텍스트: [2026-03-09 14:30:00] INFO     [agent.safety] ...
```

---

### TODO(backend) 목록

Backend팀과의 협의 포인트 요약. `grep -rn "TODO(backend)" src/`로 전체 검색 가능.

| 항목 | 파일 | 내용 |
|------|------|------|
| 4-2 | `backend_resources.py` | 리소스 경로명(conversations, emotion_logs 등) 확정 |
| 4-2 | `backend_resources.py` | 이미지 바이트 전송 방식 확정 |
| 4-3 | `api_proxy.py` | 벡터 검색/upsert 엔드포인트 확인 |
| 4-3 | `api_proxy.py` | 그래프 쿼리 엔드포인트 + Cypher 프록시 가능 여부 |
| 4-3 | `api_proxy.py` | SQL 쿼리 프록시 vs REST resource 방식 결정 |
| 4-4 | `api_proxy.py` | S3 업로드/조회/목록/Presigned URL 엔드포인트 |
| 4-4 | `api_proxy.py` | 바이너리 전송 방식 (base64 vs multipart) |
| 4-4 | `s3_client.py` | 업로드 prefix 구조 확정 |

---

### 검증 결과

```
$ python3 -m pytest tests/ -v
269 passed in 155.97s

$ python3 -m ruff check .
All checks passed!

$ grep -rn "TODO(backend)" src/
26개 매칭 (api_proxy.py 14개, backend_resources.py 11개, s3_client.py 1개)
```

---

*Production 코드 변경: logger.py 1개 수정 (포맷터 분기 추가) | Protected 파일 수정: 없음*

---

## 팀 기여 (Team Contributions)

> 같은 기간 다른 개발자가 머지한 PR. 해당 버전 시점에 코드베이스에 반영된 변경사항.

### PR #9 — YAML 프롬프트 분리 및 리팩토링 (개발자1, Jun)

- **머지**: 2026-03-04 | **브랜치**: `jun_prompt`
- **규모**: +156 / -74 (10개 파일)

| 파일 | 변경 |
|------|------|
| `prompts/conversation/intent_classifier.yaml` | 신규: Intent Classifier 프롬프트 외부화 (42줄) |
| `prompts/conversation/knowledge.yaml` | 신규: Knowledge Agent 프롬프트 외부화 (24줄) |
| `prompts/podcast/script_generator.yaml` | 신규: Script Generator 프롬프트 외부화 (60줄) |
| `prompts/podcast/script_personalizer.yaml` | 신규: Script Personalizer 프롬프트 외부화 (4줄) |
| `src/agents/conversation/intent_classifier.py` | 수정: 인라인 프롬프트 → YAML 로딩으로 변경 (-41줄) |
| `src/agents/conversation/knowledge.py` | 수정: 인라인 프롬프트 → YAML 로딩으로 변경 (-15줄) |
| `src/agents/podcast/script_generator.py` | 수정: 프롬프트 로딩 방식 변경 |
| `src/agents/podcast/script_personalizer.py` | 수정: 프롬프트 로딩 방식 변경 |
| `tests/agents/conversation/test_intent_classifier.py` | 수정: 테스트 적용 |
| `.gitignore` | 수정 |

---

### PR #10 — Safety/Visualization 리팩토링 + safety_constants 모듈화 (개발자2, 한가은)

- **머지**: 2026-03-04 | **브랜치**: `feature/agents-gaeun`
- **규모**: +130 / -436 (3개 파일, 순감 -306줄)

| 파일 | 변경 |
|------|------|
| `src/agents/podcast/safety.py` | 리팩토링: Safety Agent 간소화 (170줄, -130줄 감소) |
| `src/agents/podcast/visualization.py` | 리팩토링: Visualization Agent 간소화 (375줄, -300줄 감소) |
| `src/agents/shared/safety_constants.py` | 신규: Safety 상수 모듈 분리 (21줄) — 위험 키워드, 임계값 등 |

---

### PR #12 — 세그먼트 통합 개인화 리팩토링 (개발자1, Jun)

- **머지**: 2026-03-06 | **브랜치**: `jun_segment`
- **규모**: +63 / -185 (7개 파일, 순감 -122줄)

| 파일 | 변경 |
|------|------|
| `src/agents/podcast/script_personalizer.py` | 리팩토링: 세그먼트 기반 개인화 로직 재구성 |
| `tests/agents/podcast/test_script_personalizer.py` | 수정: 테스트 적용 |
| `prompts/conversation/intent_classifier.yaml` | 삭제 (PR #9에서 추가, 여기서 제거) |
| `prompts/conversation/knowledge.yaml` | 삭제 |
| `prompts/podcast/script_generator.yaml` | 삭제 |
| `prompts/podcast/script_personalizer.yaml` | 삭제 |
| `.gitignore` | 수정 |

> **참고**: PR #9에서 추가한 프롬프트 YAML 파일 4개가 이 PR에서 제거됨 — 프롬프트 관리 방식 재조정으로 인한 것.

---

### PR #14 — 세그먼트 통합 개인화 처리 (개발자1, Jun)

- **머지**: 2026-03-09 | **브랜치**: `jun_segments`
- **규모**: +1 / -2 (2개 파일)

| 파일 | 변경 |
|------|------|
| `src/agents/podcast/script_personalizer.py` | 수정: 미사용 `segment_type` 파라미터 제거 (-1줄) |
| `tests/agents/podcast/test_script_personalizer.py` | 수정: 테스트 적용 |

---

*마지막 업데이트: 2026-03-16*

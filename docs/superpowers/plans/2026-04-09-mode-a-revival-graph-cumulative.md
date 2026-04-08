# Mode A 부활 — 누적 그래프 EMA AI 서버 전환 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `graph_cumulative.py`의 Mode B(POST /graph_nodes/episodes) 코드를 Mode A(GET → EMA 계산 → PUT /graph_nodes)로 전환하여, 백엔드가 구현한 실제 API와 정합성을 맞춘다.

**Architecture:**
Mode A에서는 AI 서버가 직접 EMA(지수이동평균)를 계산한다. 파이프라인 실행 시 (1) 백엔드에서 기존 누적 그래프를 GET, (2) 새 GoT 결과와 EMA 병합, (3) 병합된 최종 결과를 PUT으로 전송한다. 백엔드는 받은 데이터를 그대로 UPSERT하면 된다.

**Tech Stack:** Python 3.11, httpx, Pydantic v2, pytest-asyncio

---

## 전제 조건 — 백엔드 의존성 (AI 코드 외부)

> 아래 항목은 **백엔드팀 수정 사항**이다. AI 코드는 변경하지 않는다.
> 계획서 실행 전 백엔드팀 확인 필요.

| # | 엔드포인트 | 현재 문제 | 필요 조치 |
|---|-----------|---------|---------|
| 1 | `POST /api/v1/graph_analyses` | SaveRequest 포맷(`type`, `data`) 전송 시 400 반환 | SaveRequest 포맷 수용하도록 수정 필요 |

> `PUT /graph_nodes` 응답의 `success` 필드 누락은 Task 2의 `put_graph_cumulative()` 메서드에서 HTTP status_code 기준으로 처리한다.

> **AI팀 스키마(SaveRequest)는 변경하지 않는다.** 백엔드가 우리 포맷을 맞춰야 한다.

---

## 파이프라인 내 위치 — 전체 TIER 워크플로우

```
사용자 입력 ("요즘 직장에서 너무 힘들어요")
    │
    ▼
┌─────────────────────────────────┐
│ TIER 0: Intent Classifier       │
│   mode = "podcast"              │
│   complexity_score 계산         │
└──────────────┬──────────────────┘
               │
   ┌───────────┴────────────────────────────┐
   │       TIER 1 (4개 병렬 Fan-out)         │
   │                                         │
   │  ┌──────────┐  ┌──────────┐            │
   │  │ Safety   │  │ Emotion  │            │
   │  │ Agent    │  │ Agent    │            │
   │  └──────────┘  └──────────┘            │
   │                                         │
   │  ┌──────────┐  ┌──────────────────────┐│
   │  │ Content  │  │ Podcast Reasoning    ││
   │  │ Analyzer │  │                      ││
   │  └──────────┘  │  1. GoT 그래프 구축   ││
   │                │  2. ToT 대안 탐색     ││
   │                │  3. CoT 최종 상세화   ││
   │                └──────────┬───────────┘│
   └───────────────────────────│────────────┘
                               │
                    GoT 추론 완료 후 3곳에 저장:
                               │
             ┌─────────────────┼──────────────────┐
             ▼                 ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
    │ ① Neo4j      │  │ ② graph_     │  │ ③ publish_graph_     │
    │ 직접 저장    │  │ _to_backend  │  │ _to_rdb()            │
    │ (GoTNode     │  │ POST /graph_ │  │ ★ Mode A (이번 구현)  │
    │  MERGE)      │  │ _analyses    │  │ GET → EMA → PUT       │
    └──────────────┘  └──────────────┘  └──────────────────────┘
                               │
                               ▼
               ┌───────────────────────────┐
               │ TIER 2 (병렬)             │
               │  Script Generator         │
               │  Visualization            │
               └──────────────┬────────────┘
                               │
               ┌───────────────▼────────────┐
               │ TIER 3: Batch Validator    │
               └──────────────┬────────────┘
                               │
               ┌───────────────▼────────────┐
               │ TIER 4: Script Personalizer│
               └──────────────┬────────────┘
                               │
                     비동기: Learning Agent
                               │
                               ▼
                      팟캐스트 에피소드 출력
```

**호출 경로 (코드 레벨):**
```
podcast_reasoning.py → _save_graph_data()
    ├── _save_got_to_neo4j()            # Neo4j MERGE (①)
    ├── _publish_graph_to_backend()     # POST /graph_analyses (②)
    └── publish_graph_to_rdb()          # Mode A GET→EMA→PUT (③) ← 이번 변경
```

---

## Mode A 상세 워크플로우 (publish_graph_to_rdb 내부)

```
publish_graph_to_rdb(got_result, state, episode_id)
    │
    │  [사전 조건 검사]
    ├── backend_client is None? → False 반환 (파이프라인 계속)
    └── got_nodes 비어있음? → True 반환 (skip, 정상)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Step 1: 기존 누적 데이터 조회                         │
│                                                      │
│  BackendClient.load_graph_cumulative(user_id)        │
│  GET /api/v1/graph_nodes?user_id={user_id}           │
│                                                      │
│  응답 파싱:                                           │
│  {"code":"ok","data":{"data":{"nodes":[...],"links":[...]}}}
│       ↓                                              │
│  GraphCumulativeData(nodes=[...], links=[...])       │
│  (신규 사용자 or 404 → nodes=[], links=[])           │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Step 2: EMA 병합 계산                                │
│                                                      │
│  got_node_map 구성: {node_id: {label, grp}}          │
│  (엣지의 from/to ID → label+grp 변환용)              │
│                                                      │
│  ┌─── _merge_nodes() ──────────────────────────┐    │
│  │  기존 노드 (label+grp 키로 매핑)              │    │
│  │                                              │    │
│  │  ① 기존 노드와 매칭 (label+grp 동일):        │    │
│  │    new_weight = α×intensity + (1-α)×old_w   │    │
│  │    mention_count += 1                        │    │
│  │    trend = increasing/stable/decreasing      │    │
│  │    last_seen = now                           │    │
│  │                                              │    │
│  │  ② 매칭 없음 (신규 노드):                    │    │
│  │    weight = intensity                        │    │
│  │    mention_count = 1                         │    │
│  │    trend = "stable"                          │    │
│  │    first_seen = last_seen = now              │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ┌─── _merge_links() ──────────────────────────┐    │
│  │  기존 엣지 (source+target 4-tuple 키로 매핑) │    │
│  │                                              │    │
│  │  ① 기존 엣지와 매칭:                         │    │
│  │    weight += 1 (등장 횟수 누적)              │    │
│  │    last_seen = now                           │    │
│  │                                              │    │
│  │  ② 매칭 없음 (신규 엣지):                    │    │
│  │    weight = 1                                │    │
│  │    first_seen = last_seen = now              │    │
│  │                                              │    │
│  │  [예외] self-loop 차단:                      │    │
│  │    source == target → 무시                   │    │
│  │  [예외] 미등록 node_id → 무시                │    │
│  └──────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Step 3: 병합 결과 저장                                │
│                                                      │
│  SaveRequest(                                        │
│    user_id = state["user_id"],                       │
│    session_id = state["session_id"],                 │
│    type = "graph_cumulative",                        │
│    data = {"nodes": merged_nodes, "links": merged_links},
│    timestamp = now,                                  │
│  )                                                   │
│       ↓                                              │
│  BackendClient.put_graph_cumulative(request)         │
│  PUT /api/v1/graph_nodes                             │
│       ↓                                             │
│  HTTP 200 → True / 그 외 → False                    │
└─────────────────────────────────────────────────────┘
```

---

## EMA 계산 공식

```
새 weight = α × 새 intensity + (1 - α) × 기존 weight
α = config/settings.yaml → graph.ema_alpha  (기본값 0.3)

trend 판정 기준 (threshold = 0.05):
  delta = new_weight - old_weight
  delta ≥ +0.05  →  "increasing"
  delta ≤ -0.05  →  "decreasing"
  그 외           →  "stable"

예시:
  기존 weight = 0.6,  이번 intensity = 0.9
  new_weight  = 0.3 × 0.9 + 0.7 × 0.6 = 0.27 + 0.42 = 0.69
  delta = 0.69 - 0.60 = +0.09 → "increasing"
```

---

## 백엔드 API 스키마 참조 (BE_API_TEST_RESULT_2026-04-08 기준)

### GET /api/v1/graph_nodes?user_id={user_id} 응답

```json
{
  "code": "ok",
  "message": "성공",
  "data": {
    "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
    "type": "graph_cumulative",
    "data": {
      "nodes": [
        {
          "label": "번아웃",
          "grp": "EMOTIONAL_EXHAUSTION",
          "weight": 0.86,
          "mention_count": 5,
          "trend": "increasing",
          "first_seen": "2026-04-01T00:10:00",
          "last_seen": "2026-04-08T00:35:00"
        }
      ],
      "links": [
        {
          "source_label": "업무 과부하",
          "source_grp": "WORK_STRUCTURE",
          "target_label": "번아웃",
          "target_grp": "EMOTIONAL_EXHAUSTION",
          "weight": 6,
          "relationship": "causes",
          "first_seen": "2026-04-01T00:30:00",
          "last_seen": "2026-04-08T00:45:00"
        }
      ]
    }
  }
}
```

> 주의: `grp`는 BE 더미 데이터에서 UPPER_CASE로 반환될 수 있다.
> `_merge_nodes()` / `_merge_links()` 내부에서 `.lower()`로 정규화하여 처리한다.

신규 사용자 (데이터 없음): HTTP 404 반환 (에러가 아닌 정상 케이스).
에러 케이스 (5xx, 네트워크 오류 등): 예외 발생 → `None` 반환으로 에러와 완전 분리.

### PUT /api/v1/graph_nodes 응답 (Backend → AI 서버)

```json
{
  "code": "ok",
  "message": "성공"
}
```

> `success` 필드 없음. HTTP status + `code == "ok"` 두 조건 모두 검증해야 한다.

### PUT /api/v1/graph_nodes 요청 (AI 서버 → Backend) — SaveRequest 포맷

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "session_id": "sess_001",
  "type": "graph_cumulative",
  "data": {
    "nodes": [
      {
        "label": "업무과부하",
        "grp": "work_structure",
        "weight": 0.81,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-04-08T10:00:00+00:00",
        "last_seen": "2026-04-08T10:30:00+00:00"
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
        "first_seen": "2026-04-08T10:00:00+00:00",
        "last_seen": "2026-04-08T10:30:00+00:00"
      }
    ]
  },
  "timestamp": "2026-04-08T10:00:00+00:00"
}
```

---

## 변경 파일 목록

| 파일 | 작업 | 비고 |
|------|------|------|
| `src/api/contracts.py` | 수정 (**Protected** — 3인 합의) | `GraphCumulativeData` 신규 추가 (기존 코드 변경 없음) |
| `config/settings.yaml` | 수정 | `graph.ema_alpha: 0.3` 추가 |
| `config/loader.py` | 수정 (Shared Infra — 신규 추가만 허용) | `graph_ema_alpha` property 추가 |
| `src/api/backend_resources.py` | 수정 | Mode A 상수 추가, Mode B 상수 제거 |
| `src/api/client.py` | 수정 | `load_graph_cumulative()` + `put_graph_cumulative()` 추가 |
| `src/api/graph_cumulative.py` | **전체 재작성** | Mode B → Mode A (EMA 계산 포함) |
| `tests/api/test_graph_cumulative.py` | **전체 재작성** | Mode B 테스트 삭제, Mode A 테스트 신규 작성 |

> **`contracts.py` 수정 근거:**
> `GraphCumulativeData` 추가는 기존 `SaveRequest` / `SaveResponse` / `LoadResponse`를 전혀 건드리지 않는 **순수 추가**다.
> 이 스키마 없이 `load_graph_cumulative()`를 `dict[str, Any]` 반환으로 구현하면
> `.get()` 호출이 산재하고 타입 오류가 런타임에 숨겨진다.
> 계획서 원칙("수정하는 게 더 좋다면 진행")에 따라 추가한다.
> `GraphSaveResponse`는 추가하지 않는다 — PUT 응답 `code=="ok"` 확인은 `put_graph_cumulative()` 내부에 인라인 처리한다.

> **변경하지 않는 파일:**
> - `src/agents/podcast/podcast_reasoning.py` (`_publish_graph_to_backend` 유지 — 스키마 불변 원칙)
> - `src/api/graph_transformer.py` (`validate_group` 재사용)
> - `src/models/agent_state.py`, `src/models/message.py`, `src/graph/workflow.py` (Protected)

---

## Task 1: `contracts.py` — `GraphCumulativeData` 추가

**배경:** GET /graph_nodes의 응답 내부 `data.data` 필드를 타입 안전하게 파싱하기 위한 Pydantic 모델이 필요하다. `contracts.py`는 Protected 파일이지만, 기존 클래스를 변경하지 않고 신규 클래스만 추가하므로 영향 범위가 최소화된다. PUT 응답(`{"code":"ok","message":"성공"}`) 확인은 별도 모델 없이 `client.py`에 인라인 처리한다.

**Files:**
- Modify: `src/api/contracts.py`

- [ ] **Step 1: 실패 확인**

```bash
python3 -c "from src.api.contracts import GraphCumulativeData"
# 예상: ImportError (아직 없음)
```

- [ ] **Step 2: `contracts.py` 끝에 클래스 1개 추가**

`ErrorResponse` 클래스 정의 끝 다음에 아래를 추가한다:

```python
class GraphCumulativeData(BaseModel):
    """GET /api/v1/graph_nodes 응답의 누적 그래프 데이터.

    Backend 응답 구조:
        {"code": "ok", "data": {"data": <이 모델>}}

    신규 사용자(404): 이 모델이 아닌 None을 반환하는 것이 아니라,
    BackendClient.load_graph_cumulative()가 GraphCumulativeData()를 반환한다.
    에러(5xx 등): BackendClient가 None을 반환하여 완전히 구분한다.

    nodes: 누적 감정/주제 노드 목록 (label, grp, weight, mention_count, trend, first_seen, last_seen)
    links: 누적 연결 엣지 목록 (source_label, source_grp, target_label, target_grp, weight, relationship, ...)
    """

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, Any]] = Field(default_factory=list)
```

- [ ] **Step 3: import 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.contracts import GraphCumulativeData

d = GraphCumulativeData()
print('nodes:', d.nodes)   # []
print('links:', d.links)   # []
d2 = GraphCumulativeData(nodes=[{'label': 'test'}], links=[])
print('nodes:', d2.nodes)  # [{'label': 'test'}]
"
# 예상: 정상 출력
```

- [ ] **Step 4: 기존 contracts 클래스 영향 없음 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.contracts import SaveRequest, SaveResponse, LoadResponse, ErrorDetail, ErrorResponse
print('기존 클래스 모두 import OK')
"
# 예상: 기존 클래스 모두 import OK
```

- [ ] **Step 5: lint/type 검사**

```bash
PYTHONPATH=. python3 -m ruff check src/api/contracts.py
PYTHONPATH=. python3 -m mypy src/api/contracts.py --ignore-missing-imports
# 예상: 에러 없음
```

- [ ] **Step 6: 커밋**

```bash
git add src/api/contracts.py
git commit -m "feat: contracts.py에 GraphCumulativeData 스키마 추가 (GET /graph_nodes 응답 파싱용)"
```

---

## Task 2: `settings.yaml` + `loader.py` — EMA alpha 설정 추가

**배경:** `graph_cumulative.py`에서 EMA alpha 값을 settings에서 읽어야 한다.
현재 `settings.yaml`에 `graph:` 섹션이 없어 코드에서 참조 불가.

**Files:**
- Modify: `config/settings.yaml`
- Modify: `config/loader.py`

- [ ] **Step 1: 실패 확인**

```bash
PYTHONPATH=. python3 -c "
from config.loader import get_settings
s = get_settings()
print(s.graph_ema_alpha)
"
# 예상: AttributeError (아직 없음)
```

- [ ] **Step 2: `settings.yaml`에 graph 섹션 추가**

`security:` 섹션 바로 위에 다음을 추가한다:

```yaml
# 누적 그래프 설정
graph:
  ema_alpha: 0.3    # EMA 지수이동평균 계수 (0.0~1.0, 클수록 최신 에피소드 반영 비율 높음)
```

- [ ] **Step 3: `loader.py`에 property 추가**

`pii_sanitization_enabled` property 끝 다음에 추가한다:

```python
    @property
    def graph_ema_alpha(self) -> float:
        """누적 그래프 EMA 계수를 반환한다.

        0.0~1.0 범위. 클수록 최신 에피소드의 반영 비율이 높아진다.
        기본값 0.3 (config/settings.yaml graph.ema_alpha 미설정 시 폴백).
        """
        return float(self._config.get("graph", {}).get("ema_alpha", 0.3))
```

- [ ] **Step 4: 통과 확인**

```bash
PYTHONPATH=. python3 -c "
from config.loader import get_settings
s = get_settings()
print('graph_ema_alpha:', s.graph_ema_alpha)  # 0.3
"
# 예상: graph_ema_alpha: 0.3
```

- [ ] **Step 5: 전체 설정 테스트 확인**

```bash
PYTHONPATH=. pytest tests/ -k "settings or config or loader" -v --tb=short
# 예상: 기존 설정 관련 테스트 전부 통과
```

- [ ] **Step 6: 커밋**

```bash
git add config/settings.yaml config/loader.py
git commit -m "feat: graph.ema_alpha 설정 추가 (settings.yaml + loader.py)"
```

---

## Task 3: `backend_resources.py` — Mode A 상수 교체

**Files:**
- Modify: `src/api/backend_resources.py`

- [ ] **Step 1: 실패 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.backend_resources import RESOURCE_GRAPH_NODES, TYPE_GRAPH_CUMULATIVE
"
# 예상: ImportError (아직 없음)
```

- [ ] **Step 2: 파일 끝 3줄 교체**

현재:
```python
# --- 누적 그래프 리소스 ---
RESOURCE_GRAPH_EPISODES = "graph_nodes/episodes"
TYPE_GRAPH_EPISODE = "graph_episode"
```

교체 후:
```python
# --- 누적 그래프 리소스 (Mode A) ---
RESOURCE_GRAPH_NODES = "graph_nodes"          # GET(조회)/PUT(갱신) 공통 엔드포인트
TYPE_GRAPH_CUMULATIVE = "graph_cumulative"    # PUT 전송 시 SaveRequest.type 필드
```

- [ ] **Step 3: 통과 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.backend_resources import RESOURCE_GRAPH_NODES, TYPE_GRAPH_CUMULATIVE
assert RESOURCE_GRAPH_NODES == 'graph_nodes'
assert TYPE_GRAPH_CUMULATIVE == 'graph_cumulative'
print('OK')
"
# 예상: OK
```

- [ ] **Step 4: Mode B 상수 미참조 확인**

```bash
grep -rn "RESOURCE_GRAPH_EPISODES\|TYPE_GRAPH_EPISODE" src/
# 예상: 출력 없음 (graph_cumulative.py가 Task 5에서 제거됨)
```

- [ ] **Step 5: 커밋**

```bash
git add src/api/backend_resources.py
git commit -m "refactor: graph_nodes 리소스 상수 Mode A 전환 (episodes → graph_nodes)"
```

---

## Task 4: `client.py` — 그래프 전용 GET/PUT 메서드 추가

**배경:**
- `BackendClient.load()` → `LoadResponse({success, data:[], total, page})` 기대. GET /graph_nodes 응답은 `{"code":"ok","data":{"data":{...}}}` 구조 → 포맷 불일치.
- `BackendClient.update()` → `SaveResponse({success})` 기대. PUT /graph_nodes 응답은 `{"code":"ok","message":"성공"}` → `success` 필드 없어 ValidationError 발생.
- → 기존 메서드를 수정하지 않고 그래프 전용 메서드 2개를 추가한다.

**Files:**
- Modify: `src/api/client.py`

- [ ] **Step 1: 파일 상단 import에 `GraphCumulativeData` 추가**

현재:
```python
from src.api.contracts import LoadResponse, SaveRequest, SaveResponse
```

교체:
```python
from src.api.contracts import (
    GraphCumulativeData,
    LoadResponse,
    SaveRequest,
    SaveResponse,
)
```

- [ ] **Step 2: `update()` 메서드 끝 다음에 메서드 2개 추가**

```python
    async def load_graph_cumulative(self, user_id: str) -> GraphCumulativeData | None:
        """사용자의 누적 그래프 데이터를 조회한다.

        반환값 의미:
          - GraphCumulativeData(nodes=[], links=[]) : 신규 사용자 (HTTP 404 — 정상 케이스)
          - GraphCumulativeData(nodes=[...], ...)  : 기존 사용자 (HTTP 200 — 정상 케이스)
          - None                                   : GET 자체 실패 (5xx, 네트워크 에러 등)

        신규 사용자와 에러를 완전히 분리한다.
        호출자는 None 수신 시 에러 처리, GraphCumulativeData 수신 시 정상 처리해야 한다.

        Backend 응답 포맷 (200):
            {"code":"ok","data":{"data":{"nodes":[...],"links":[...]}}}
        Backend 응답 포맷 (404):
            404 Not Found (신규 사용자, 저장된 데이터 없음)

        Args:
            user_id: 사용자 고유 ID

        Returns:
            GraphCumulativeData (신규 또는 기존 사용자) | None (에러)
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/graph_nodes",
                params={"user_id": user_id},
            )
            # 404 = 신규 사용자 (정상) — 에러로 처리하지 않는다
            if response.status_code == 404:
                return GraphCumulativeData()
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            inner = body.get("data", {}).get("data") or {}
            return GraphCumulativeData.model_validate(inner)
        except Exception:
            # 에러 케이스 — None 반환으로 404(신규 사용자)와 완전 분리
            return None

    async def put_graph_cumulative(self, data: SaveRequest) -> bool:
        """누적 그래프 데이터를 백엔드에 저장(UPSERT)한다.

        HTTP status_code AND 응답 body의 code 필드를 모두 검증한다.
        Backend 실제 응답: {"code":"ok","message":"성공"}

        Args:
            data: SaveRequest 스키마 (type="graph_cumulative")

        Returns:
            HTTP 2xx + code=="ok" 시 True, 그 외 False
        """
        try:
            response = await self._client.put(
                f"{self._base_url}/graph_nodes",
                json=data.model_dump(mode="json"),
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            return isinstance(body, dict) and body.get("code") == "ok"
        except Exception:
            return False
```

- [ ] **Step 3: import 및 메서드 동작 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.client import BackendClient
from src.api.contracts import GraphCumulativeData
client = BackendClient.__new__(BackendClient)
print(hasattr(client, 'load_graph_cumulative'))  # True
print(hasattr(client, 'put_graph_cumulative'))   # True
"
# 예상: True / True
```

- [ ] **Step 4: lint/type 검사**

```bash
PYTHONPATH=. python3 -m ruff check src/api/client.py
PYTHONPATH=. python3 -m mypy src/api/client.py --ignore-missing-imports
# 예상: 에러 없음
```

- [ ] **Step 5: 커밋**

```bash
git add src/api/client.py
git commit -m "feat: BackendClient에 누적 그래프 전용 GET/PUT 메서드 추가"
```

---

## Task 5: `graph_cumulative.py` — Mode A 전체 재작성

**Files:**
- Modify: `src/api/graph_cumulative.py`

- [ ] **Step 1: 현재 파일 내용 확인 (삭제 전 파악)**

```bash
cat src/api/graph_cumulative.py
```

- [ ] **Step 2: 파일 전체를 아래 내용으로 교체**

```python
"""
GoT 그래프 데이터를 누적하여 Backend에 저장하는 모듈 (Mode A).

흐름:
  1. GET /api/v1/graph_nodes    — 기존 누적 데이터 조회
  2. EMA 계산                   — 기존 가중치와 새 GoT 결과를 지수이동평균으로 병합
  3. PUT /api/v1/graph_nodes    — 병합된 최종 데이터 저장

EMA 공식:
  new_weight = α × new_intensity + (1 - α) × existing_weight
  α = config/settings.yaml → graph.ema_alpha  (기본값 0.3)

사용 방법:
    await publish_graph_to_rdb(got_result, state, episode_id)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.graph_transformer import validate_group

logger = logging.getLogger(__name__)

_TREND_THRESHOLD: float = 0.05


def _apply_ema(existing_weight: float, new_intensity: float, alpha: float) -> float:
    """EMA: α × new + (1 - α) × existing. 소수점 4자리 반올림."""
    return round(alpha * new_intensity + (1.0 - alpha) * existing_weight, 4)


def _calc_trend(old_weight: float, new_weight: float) -> str:
    """가중치 변화량으로 trend를 판정한다.

    Returns:
        "increasing" | "stable" | "decreasing"
    """
    delta = new_weight - old_weight
    if delta >= _TREND_THRESHOLD:
        return "increasing"
    if delta <= -_TREND_THRESHOLD:
        return "decreasing"
    return "stable"


def _merge_nodes(
    existing_nodes: list[dict[str, Any]],
    got_nodes: list[dict[str, Any]],
    now: datetime,
    alpha: float,
) -> list[dict[str, Any]]:
    """기존 누적 노드와 새 GoT 노드를 EMA로 병합한다.

    Args:
        existing_nodes: GET /graph_nodes에서 받은 GraphCumulativeData.nodes
        got_nodes: 이번 에피소드 GoT 노드 (label, group, intensity 포함)
        now: 현재 시각 (last_seen 갱신용)
        alpha: EMA 계수

    Returns:
        병합된 누적 노드 목록 (grp는 소문자)
    """
    now_iso = now.isoformat()
    # (label, grp소문자) → 노드 dict 매핑 (기존 데이터 grp 대소문자 정규화)
    result: dict[tuple[str, str], dict[str, Any]] = {
        (n["label"], n["grp"].lower()): dict(n) for n in existing_nodes
    }

    for got_node in got_nodes:
        label = got_node.get("label", "").strip()
        if not label:
            continue
        grp = validate_group(got_node).lower()
        intensity = float(got_node.get("intensity", 0.5))
        key = (label, grp)

        if key in result:
            existing = result[key]
            old_w = float(existing.get("weight", 0.5))
            new_w = _apply_ema(old_w, intensity, alpha)
            result[key] = {
                **existing,
                "weight": new_w,
                "mention_count": int(existing.get("mention_count", 1)) + 1,
                "trend": _calc_trend(old_w, new_w),
                "last_seen": now_iso,
            }
        else:
            result[key] = {
                "label": label,
                "grp": grp,
                "weight": round(intensity, 4),
                "mention_count": 1,
                "trend": "stable",
                "first_seen": now_iso,
                "last_seen": now_iso,
            }

    return list(result.values())


def _merge_links(
    existing_links: list[dict[str, Any]],
    got_edges: list[dict[str, Any]],
    got_node_map: dict[str, dict[str, str]],
    now: datetime,
) -> list[dict[str, Any]]:
    """기존 누적 엣지와 새 GoT 엣지를 병합한다. 등장 횟수(weight)를 누적한다.

    Args:
        existing_links: GET /graph_nodes에서 받은 GraphCumulativeData.links
        got_edges: 이번 에피소드 GoT 엣지 (from/to 키 사용, relationship)
        got_node_map: GoT node id → {"label": ..., "grp": ...} 매핑
        now: 현재 시각

    Returns:
        병합된 누적 엣지 목록 (self-loop 제외)
    """
    now_iso = now.isoformat()
    # (src_label, src_grp소문자, tgt_label, tgt_grp소문자) → 엣지 dict
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {
        (
            e["source_label"],
            e["source_grp"].lower(),
            e["target_label"],
            e["target_grp"].lower(),
        ): dict(e)
        for e in existing_links
    }

    for edge in got_edges:
        src_id = str(edge.get("from", ""))
        tgt_id = str(edge.get("to", ""))
        src_info = got_node_map.get(src_id, {})
        tgt_info = got_node_map.get(tgt_id, {})

        src_label = src_info.get("label", "")
        src_grp = src_info.get("grp", "").lower()
        tgt_label = tgt_info.get("label", "")
        tgt_grp = tgt_info.get("grp", "").lower()

        if not src_label or not tgt_label:
            continue
        # self-loop 방지
        if src_label == tgt_label and src_grp == tgt_grp:
            continue

        key = (src_label, src_grp, tgt_label, tgt_grp)
        relationship = str(edge.get("relationship", "related"))

        if key in result:
            existing_edge = result[key]
            result[key] = {
                **existing_edge,
                "weight": int(existing_edge.get("weight", 1)) + 1,
                "last_seen": now_iso,
            }
        else:
            result[key] = {
                "source_label": src_label,
                "source_grp": src_grp,
                "target_label": tgt_label,
                "target_grp": tgt_grp,
                "weight": 1,
                "relationship": relationship,
                "first_seen": now_iso,
                "last_seen": now_iso,
            }

    return list(result.values())


async def publish_graph_to_rdb(
    got_result: dict[str, Any],
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """GoT 결과를 EMA로 누적하여 Backend에 저장한다 (Mode A).

    흐름:
      1. GET /api/v1/graph_nodes  — 기존 누적 데이터 조회
      2. EMA 병합                 — 새 GoT 노드/엣지를 기존 데이터와 통합
      3. PUT /api/v1/graph_nodes  — 병합 결과 저장

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)
        episode_id: 로그 컨텍스트용 (Mode A에서는 PUT payload에 미포함)

    Returns:
        성공 시 True, 실패 시 False (파이프라인 비중단)
    """
    try:
        from src.api.backend_resources import RESOURCE_GRAPH_NODES, TYPE_GRAPH_CUMULATIVE
        from src.api.contracts import GraphCumulativeData, SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            logger.warning("BackendClient가 초기화되지 않았습니다")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 누적 갱신을 건너뜁니다")
            return True

        from config.loader import get_settings

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        now = datetime.now(timezone.utc)
        alpha = get_settings().graph_ema_alpha

        # 1. 기존 누적 데이터 조회
        #    - GraphCumulativeData : 정상 (신규 사용자=빈 데이터 / 기존 사용자=누적 데이터)
        #    - None                : GET 자체 실패 (5xx, 네트워크 에러) → graceful degradation
        existing = await backend_client.load_graph_cumulative(user_id)
        if existing is None:
            logger.warning(
                "기존 누적 데이터 조회 실패 — 신규 사용자로 처리 후 진행 (user=%s)", user_id
            )
            existing = GraphCumulativeData()

        # GoT node id → {label, grp} 매핑 (엣지 해석용)
        got_node_map: dict[str, dict[str, str]] = {
            str(n.get("id", str(i))): {
                "label": n.get("label", ""),
                "grp": validate_group(n),
            }
            for i, n in enumerate(got_nodes)
        }

        # 2. EMA 병합
        merged_nodes = _merge_nodes(existing.nodes, got_nodes, now, alpha)
        merged_links = _merge_links(
            existing.links,
            got_result.get("edges", []),
            got_node_map,
            now,
        )

        # 3. PUT 저장
        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_GRAPH_CUMULATIVE,
            data={"nodes": merged_nodes, "links": merged_links},
            timestamp=now,
        )
        success = await backend_client.put_graph_cumulative(request)
        if success:
            logger.info(
                "누적 그래프 갱신 완료 (user=%s, nodes=%d, links=%d, ep=%s)",
                user_id,
                len(merged_nodes),
                len(merged_links),
                episode_id or "unknown",
            )
        else:
            logger.warning("누적 그래프 PUT 실패 (user=%s)", user_id)
        return success

    except Exception as e:
        logger.warning(
            "누적 그래프 갱신 실패 — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False
```

- [ ] **Step 3: import 동작 확인**

```bash
PYTHONPATH=. python3 -c "
from src.api.graph_cumulative import (
    _apply_ema,
    _calc_trend,
    _merge_links,
    _merge_nodes,
    publish_graph_to_rdb,
)
print('import OK')
"
# 예상: import OK
```

- [ ] **Step 4: lint/type/format 검사**

```bash
PYTHONPATH=. python3 -m ruff check src/api/graph_cumulative.py
PYTHONPATH=. python3 -m mypy src/api/graph_cumulative.py --ignore-missing-imports
PYTHONPATH=. python3 -m black --check src/api/graph_cumulative.py
# 에러 시: python3 -m black src/api/graph_cumulative.py
```

- [ ] **Step 5: 커밋**

```bash
git add src/api/graph_cumulative.py
git commit -m "feat: graph_cumulative Mode A 전환 — AI 서버 EMA 계산 + GET/PUT 구조"
```

---

## Task 6: `test_graph_cumulative.py` — Mode A 테스트 전체 재작성

**Files:**
- Modify: `tests/api/test_graph_cumulative.py`

테스트 커버리지 목표:
- `_apply_ema`: 공식 정확성, 경계값
- `_calc_trend`: 3가지 분기 + 임계값 경계
- `_merge_nodes`: 신규/기존 EMA/group 폴백/빈 label
- `_merge_links`: 신규/기존 누적/self-loop/미등록 node_id/source-target 키 별칭
- `publish_graph_to_rdb`: 신규 사용자/기존 사용자 EMA/빈 GoT/client None/GET 폴백/PUT 실패/예외

- [ ] **Step 1: 파일 전체를 아래 내용으로 교체**

```python
"""tests/api/test_graph_cumulative.py — Mode A 누적 그래프 테스트."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from src.api.contracts import GraphCumulativeData
from src.api.graph_cumulative import (
    _apply_ema,
    _calc_trend,
    _merge_links,
    _merge_nodes,
    publish_graph_to_rdb,
)

_NOW = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)
_NOW_ISO = _NOW.isoformat()


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_backend_client():
    """backend_client mock을 src.api.main에 주입한다.

    기본값:
      - load_graph_cumulative: GraphCumulativeData() 반환 (신규 사용자, 정상 케이스)
      - put_graph_cumulative:  True 반환 (성공)
    """
    mock_client = AsyncMock()
    mock_client.load_graph_cumulative = AsyncMock(
        return_value=GraphCumulativeData(nodes=[], links=[])
    )
    mock_client.put_graph_cumulative = AsyncMock(return_value=True)
    mock_main = ModuleType("src.api.main")
    mock_main.backend_client = mock_client  # type: ignore[attr-defined]
    old = sys.modules.get("src.api.main")
    sys.modules["src.api.main"] = mock_main
    yield mock_client
    if old is not None:
        sys.modules["src.api.main"] = old
    else:
        sys.modules.pop("src.api.main", None)


# ═══════════════════════════════════════════════════════════════════════
# _apply_ema
# ═══════════════════════════════════════════════════════════════════════


class TestApplyEma:
    def test_basic_formula(self) -> None:
        # 0.3 × 0.9 + 0.7 × 0.6 = 0.27 + 0.42 = 0.69
        assert _apply_ema(existing_weight=0.6, new_intensity=0.9, alpha=0.3) == 0.69

    def test_alpha_one_ignores_existing(self) -> None:
        assert _apply_ema(existing_weight=0.5, new_intensity=0.8, alpha=1.0) == 0.8

    def test_alpha_zero_keeps_existing(self) -> None:
        assert _apply_ema(existing_weight=0.5, new_intensity=0.9, alpha=0.0) == 0.5

    def test_result_rounded_to_4_decimals(self) -> None:
        result = _apply_ema(existing_weight=0.333, new_intensity=0.777, alpha=0.3)
        assert len(str(result).split(".")[-1]) <= 4


# ═══════════════════════════════════════════════════════════════════════
# _calc_trend
# ═══════════════════════════════════════════════════════════════════════


class TestCalcTrend:
    def test_increasing(self) -> None:
        assert _calc_trend(0.5, 0.6) == "increasing"

    def test_decreasing(self) -> None:
        assert _calc_trend(0.6, 0.5) == "decreasing"

    def test_stable_within_threshold(self) -> None:
        assert _calc_trend(0.5, 0.52) == "stable"

    def test_boundary_increasing(self) -> None:
        # 0.5 + 0.05 = 0.55 → increasing (경계 포함)
        assert _calc_trend(0.5, 0.55) == "increasing"

    def test_boundary_decreasing(self) -> None:
        # 0.5 - 0.05 = 0.45 → decreasing (경계 포함)
        assert _calc_trend(0.5, 0.45) == "decreasing"


# ═══════════════════════════════════════════════════════════════════════
# _merge_nodes
# ═══════════════════════════════════════════════════════════════════════


class TestMergeNodes:
    def test_new_node_inserted(self) -> None:
        got = [{"label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}]
        result = _merge_nodes([], got, _NOW, alpha=0.3)
        assert len(result) == 1
        node = result[0]
        assert node["label"] == "번아웃"
        assert node["grp"] == "emotional_exhaustion"
        assert node["weight"] == 0.8
        assert node["mention_count"] == 1
        assert node["trend"] == "stable"
        assert node["first_seen"] == _NOW_ISO
        assert node["last_seen"] == _NOW_ISO

    def test_existing_node_ema_applied(self) -> None:
        existing = [
            {
                "label": "번아웃",
                "grp": "emotional_exhaustion",
                "weight": 0.6,
                "mention_count": 2,
                "trend": "stable",
                "first_seen": "2026-04-01T00:00:00+00:00",
                "last_seen": "2026-04-07T00:00:00+00:00",
            }
        ]
        got = [{"label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.9}]
        result = _merge_nodes(existing, got, _NOW, alpha=0.3)
        assert len(result) == 1
        node = result[0]
        assert node["weight"] == 0.69          # 0.3×0.9 + 0.7×0.6
        assert node["mention_count"] == 3
        assert node["trend"] == "increasing"   # delta = +0.09 ≥ 0.05
        assert node["last_seen"] == _NOW_ISO
        assert node["first_seen"] == "2026-04-01T00:00:00+00:00"  # 변경 없음

    def test_existing_grp_uppercase_normalized(self) -> None:
        """BE 더미 데이터의 UPPER_CASE grp도 소문자로 정규화되어 매칭된다."""
        existing = [
            {
                "label": "번아웃",
                "grp": "EMOTIONAL_EXHAUSTION",  # BE 응답의 대문자
                "weight": 0.6,
                "mention_count": 1,
                "trend": "stable",
                "first_seen": "2026-04-01T00:00:00+00:00",
                "last_seen": "2026-04-07T00:00:00+00:00",
            }
        ]
        got = [{"label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.9}]
        result = _merge_nodes(existing, got, _NOW, alpha=0.3)
        # 대소문자 달라도 같은 노드로 인식 → EMA 적용
        assert len(result) == 1
        assert result[0]["mention_count"] == 2

    def test_invalid_group_falls_back(self) -> None:
        got = [{"label": "테스트", "group": "INVALID_GROUP", "intensity": 0.5}]
        result = _merge_nodes([], got, _NOW, alpha=0.3)
        assert result[0]["grp"] == "emotional_exhaustion"

    def test_existing_and_new_coexist(self) -> None:
        existing = [
            {
                "label": "기존노드",
                "grp": "leadership",
                "weight": 0.5,
                "mention_count": 1,
                "trend": "stable",
                "first_seen": "2026-04-01T00:00:00+00:00",
                "last_seen": "2026-04-07T00:00:00+00:00",
            }
        ]
        got = [
            {"label": "기존노드", "group": "leadership", "intensity": 0.8},
            {"label": "신규노드", "group": "work_structure", "intensity": 0.7},
        ]
        result = _merge_nodes(existing, got, _NOW, alpha=0.3)
        assert len(result) == 2
        assert {n["label"] for n in result} == {"기존노드", "신규노드"}

    def test_empty_label_skipped(self) -> None:
        got = [{"label": "", "group": "leadership", "intensity": 0.8}]
        result = _merge_nodes([], got, _NOW, alpha=0.3)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# _merge_links
# ═══════════════════════════════════════════════════════════════════════


class TestMergeLinks:
    @staticmethod
    def _node_map() -> dict:
        return {
            "1": {"label": "업무과부하", "grp": "work_structure"},
            "2": {"label": "번아웃", "grp": "emotional_exhaustion"},
        }

    def test_new_edge_inserted(self) -> None:
        edges = [{"from": "1", "to": "2", "relationship": "causes"}]
        result = _merge_links([], edges, self._node_map(), _NOW)
        assert len(result) == 1
        link = result[0]
        assert link["source_label"] == "업무과부하"
        assert link["target_label"] == "번아웃"
        assert link["weight"] == 1
        assert link["relationship"] == "causes"
        assert link["first_seen"] == _NOW_ISO

    def test_existing_edge_weight_incremented(self) -> None:
        existing = [
            {
                "source_label": "업무과부하",
                "source_grp": "work_structure",
                "target_label": "번아웃",
                "target_grp": "emotional_exhaustion",
                "weight": 3,
                "relationship": "causes",
                "first_seen": "2026-04-01T00:00:00+00:00",
                "last_seen": "2026-04-07T00:00:00+00:00",
            }
        ]
        edges = [{"from": "1", "to": "2", "relationship": "causes"}]
        result = _merge_links(existing, edges, self._node_map(), _NOW)
        assert len(result) == 1
        assert result[0]["weight"] == 4
        assert result[0]["last_seen"] == _NOW_ISO
        assert result[0]["first_seen"] == "2026-04-01T00:00:00+00:00"  # 변경 없음

    def test_self_loop_prevented(self) -> None:
        node_map = {
            "1": {"label": "번아웃", "grp": "emotional_exhaustion"},
            "2": {"label": "번아웃", "grp": "emotional_exhaustion"},
        }
        edges = [{"from": "1", "to": "2", "relationship": "causes"}]
        result = _merge_links([], edges, node_map, _NOW)
        assert result == []

    def test_unknown_source_id_skipped(self) -> None:
        edges = [{"from": "99", "to": "2", "relationship": "causes"}]
        result = _merge_links([], edges, self._node_map(), _NOW)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# publish_graph_to_rdb — 통합 흐름
# ═══════════════════════════════════════════════════════════════════════


class TestPublishGraphToRdb:
    @pytest.mark.asyncio
    async def test_success_new_user(self, mock_backend_client) -> None:
        """신규 사용자: GET → 빈 데이터, EMA 없이 신규 노드로 PUT."""
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"}, "ep_001")
        assert result is True
        mock_backend_client.load_graph_cumulative.assert_awaited_once_with("u1")
        mock_backend_client.put_graph_cumulative.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_existing_user_ema_applied(self, mock_backend_client) -> None:
        """기존 사용자: GET 기존 노드 반환 → EMA 계산 후 PUT."""
        mock_backend_client.load_graph_cumulative.return_value = GraphCumulativeData(
            nodes=[
                {
                    "label": "번아웃",
                    "grp": "emotional_exhaustion",
                    "weight": 0.6,
                    "mention_count": 2,
                    "trend": "stable",
                    "first_seen": "2026-04-01T00:00:00+00:00",
                    "last_seen": "2026-04-07T00:00:00+00:00",
                }
            ],
            links=[],
        )
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.9}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is True
        call_args = mock_backend_client.put_graph_cumulative.call_args
        saved = call_args[0][0]
        put_nodes = saved.data["nodes"]
        assert put_nodes[0]["weight"] == 0.69       # 0.3×0.9 + 0.7×0.6
        assert put_nodes[0]["mention_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_got_skips_all_backend_calls(self, mock_backend_client) -> None:
        got = {"nodes": [], "edges": []}
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is True
        mock_backend_client.load_graph_cumulative.assert_not_awaited()
        mock_backend_client.put_graph_cumulative.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_backend_client_returns_false(self) -> None:
        mock_main = ModuleType("src.api.main")
        mock_main.backend_client = None  # type: ignore[attr-defined]
        old = sys.modules.get("src.api.main")
        sys.modules["src.api.main"] = mock_main
        try:
            got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}]}
            result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
            assert result is False
        finally:
            if old is not None:
                sys.modules["src.api.main"] = old
            else:
                sys.modules.pop("src.api.main", None)

    @pytest.mark.asyncio
    async def test_new_user_404_returns_empty_data_not_error(self, mock_backend_client) -> None:
        """신규 사용자(404): GraphCumulativeData() 반환 → PUT 정상 진행.
        이 케이스는 에러가 아닌 정상 케이스다."""
        # fixture 기본값이 이미 GraphCumulativeData() (신규 사용자)
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "new_user", "session_id": "s1"})
        assert result is True
        # 신규 사용자도 PUT은 실행됨
        mock_backend_client.put_graph_cumulative.assert_awaited_once()
        call_args = mock_backend_client.put_graph_cumulative.call_args
        saved = call_args[0][0]
        # mention_count=1, trend="stable" (기존 데이터 없이 신규 삽입)
        assert saved.data["nodes"][0]["mention_count"] == 1
        assert saved.data["nodes"][0]["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_get_error_none_falls_back_and_puts(self, mock_backend_client) -> None:
        """GET 에러(None 반환): 신규 사용자 처리로 대체 후 PUT 진행 (graceful degradation).
        에러이지만 파이프라인은 중단하지 않는다."""
        mock_backend_client.load_graph_cumulative.return_value = None  # 에러 케이스
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is True
        # None이어도 PUT은 실행됨 (빈 데이터로 대체)
        mock_backend_client.put_graph_cumulative.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_put_failure_returns_false(self, mock_backend_client) -> None:
        """PUT 실패 시 False 반환 (파이프라인 비중단)."""
        mock_backend_client.put_graph_cumulative.return_value = False
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, mock_backend_client) -> None:
        """예외 발생 시 False 반환 (파이프라인 비중단)."""
        mock_backend_client.load_graph_cumulative.side_effect = RuntimeError("network error")
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is False
```

- [ ] **Step 2: 테스트 실행 — 전부 통과해야 함**

```bash
PYTHONPATH=. pytest tests/api/test_graph_cumulative.py -v
# 예상:
# PASSED TestApplyEma::test_basic_formula
# PASSED TestApplyEma::test_alpha_one_ignores_existing
# ... (전체 ~22개 통과)
```

- [ ] **Step 3: 전체 회귀 테스트 확인**

```bash
PYTHONPATH=. pytest tests/ -v --tb=short 2>&1 | tail -20
# 예상: 기존 532개 + 신규 테스트 전부 passed
```

- [ ] **Step 4: 커밋**

```bash
git add tests/api/test_graph_cumulative.py
git commit -m "test: graph_cumulative Mode A 테스트 전환 (EMA 계산, GET/PUT 흐름 검증)"
```

---

## 자기 검토 (Self-Review)

### 1. Spec 커버리지

| 요구사항 | Task |
|---------|------|
| `contracts.py` GraphCumulativeData + GraphSaveResponse 추가 | Task 1 |
| settings.yaml graph.ema_alpha 추가 | Task 2 |
| loader.py graph_ema_alpha property 추가 | Task 2 |
| Mode B constants 제거, Mode A constants 추가 | Task 3 |
| GET /graph_nodes 비표준 응답 파싱 | Task 4 (`load_graph_cumulative`) |
| PUT /graph_nodes 비표준 응답 처리 | Task 4 (`put_graph_cumulative`) |
| EMA 공식 구현 (α from settings) | Task 5 (`_apply_ema`) |
| trend 판정 | Task 5 (`_calc_trend`) |
| 노드 EMA 병합 + UPPERCASE grp 정규화 | Task 5 (`_merge_nodes`) |
| 엣지 누적 + self-loop 방지 | Task 5 (`_merge_links`) |
| publish_graph_to_rdb Mode A 전체 흐름 | Task 5 |
| 전체 테스트 | Task 6 |
| `_publish_graph_to_backend()` 유지 (코드 변경 없음) | — |

### 2. 타입 일관성

| 함수/속성 | Task 5 정의 | Task 6 테스트 |
|----------|-----------|-------------|
| `_apply_ema(float, float, float) → float` | ✅ | ✅ |
| `_calc_trend(float, float) → str` | ✅ | ✅ |
| `_merge_nodes(list, list, datetime, float) → list` | ✅ | ✅ |
| `_merge_links(list, list, dict, datetime) → list` | ✅ | ✅ |
| `publish_graph_to_rdb(dict, dict, str="") → bool` | ✅ | ✅ |
| `GraphCumulativeData.nodes / .links` (Task 1) | ✅ | ✅ |
| `load_graph_cumulative() → GraphCumulativeData \| None` | ✅ | ✅ — None/비None 케이스 분리 테스트 |
| `put_graph_cumulative()` PUT code 검증 (인라인) | ✅ — `body.get("code") == "ok"` | ✅ — `test_put_failure_returns_false` |

### 3. 백엔드 미해결 항목 (AI 코드 변경 없음)

| 항목 | AI측 처리 | 백엔드 필요 조치 |
|------|----------|----------------|
| `PUT /graph_nodes` 응답 `success` 필드 없음 | `put_graph_cumulative()`에서 HTTP status_code로 우회 | 응답에 `success: true` 추가 권장 |
| `POST /graph_analyses` SaveRequest 400 | `_publish_graph_to_backend()` 변경 없음 | SaveRequest 포맷 수용 필수 |

---

## PR 양식 (계획 완료 후 사용)

```
## Summary
- graph_cumulative.py Mode B(POST /graph_nodes/episodes) → Mode A(GET→EMA→PUT /graph_nodes) 전환
- AI 서버가 EMA(α=0.3, settings 설정 가능)를 직접 계산하여 누적 그래프 갱신
- BackendClient에 비표준 응답 파싱 전용 메서드 2개 추가 (PUT 응답 검증은 인라인 처리)
- contracts.py에 GraphCumulativeData 스키마 추가 (GET 응답 타입 안전성)

## 변경 파일
- src/api/contracts.py — GraphCumulativeData 추가 (Protected, 기존 코드 변경 없음, GraphSaveResponse 추가 없음)
- config/settings.yaml — graph.ema_alpha 설정 추가
- config/loader.py — graph_ema_alpha property 추가
- src/api/backend_resources.py — Mode A 상수 교체
- src/api/client.py — load_graph_cumulative / put_graph_cumulative 추가
- src/api/graph_cumulative.py — Mode A 전체 재작성 (EMA 포함)
- tests/api/test_graph_cumulative.py — 테스트 전체 재작성

## 미해결 백엔드 의존성
- [ ] POST /graph_analyses SaveRequest 포맷 수용 (백엔드팀 수정 필요)

## Test plan
- [ ] pytest tests/api/test_graph_cumulative.py -v (전체 통과 확인)
- [ ] pytest tests/ --tb=short (전체 회귀 테스트 통과 확인)
```

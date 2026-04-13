# Graph Mode B 단일화 리팩터 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mode A 삭제, Mode B를 단일 경로로 확정, "mode" 용어를 코드/문서에서 제거

**Architecture:** AI 서버는 GoT 결과를 group 검증 후 Backend에 POST만 한다. EMA 계산과 UPSERT는 Backend 책임이며, AI 서버에는 EMA 관련 코드가 없다.

**Tech Stack:** Python 3.11, pytest-asyncio, docs Markdown

---

## 파일 변경 목록

| 파일 | 작업 | 내용 |
|------|------|------|
| `src/api/graph_cumulative.py` | 재작성 | Mode A 함수 5개 삭제, `publish_graph_raw_mode_b` → `publish_graph_to_rdb` rename |
| `tests/api/test_graph_cumulative.py` | 재작성 | Mode A 테스트 4개 클래스 삭제, Mode B 테스트 rename, 디스패처 테스트 교체 |
| `config/loader.py` | 수정 | `graph_upsert_mode`, `graph_ema_alpha` 프로퍼티 삭제 |
| `config/settings.yaml` | 수정 | `graph:` 블록(upsert_mode + ema_alpha) 삭제 |
| `src/api/backend_resources.py` | 수정 | `RESOURCE_GRAPH_NODES` 삭제 (Mode A 전용) |
| `docs/architecture/NEO4J_INTEGRATION.md` | 수정 | Mode A 내용 제거, 단일 흐름 기술, API 목록 정리 |

---

## Phase 3-A 현황 확인

`docs/superpowers/plans/2026-04-07-neo4j-integration-plan.md` v2 기준:
- GoTNode group 필드 수정: **완료**
- seed_data.json Emotion/Topic: **완료**
- E2E 검증은 인프라(Neo4j) 준비 후 진행 — 코드 작업 없음

---

## Task 1: graph_cumulative.py 재작성

**Files:**
- Modify: `src/api/graph_cumulative.py`

삭제 대상 함수:
- `calc_ema()` — Mode A 전용 (EMA는 Backend가 처리)
- `calc_trend()` — Mode A 전용
- `merge_nodes_from_got()` — Mode A 전용
- `merge_edges_from_got()` — Mode A 전용
- `publish_graph_cumulative_mode_a()` — Mode A
- 구 `publish_graph_to_rdb()` — dispatcher (Mode 분기)

유지/rename:
- `publish_graph_raw_mode_b()` → `publish_graph_to_rdb()` (docstring에서 "Mode B" 용어 제거)

- [ ] **Step 1: graph_cumulative.py 전체 재작성**

```python
"""
GoT 그래프 에피소드 데이터를 Backend에 전송하는 모듈.

에피소드별 GoT 결과를 Backend에 POST한다.
Backend가 EMA 계산 + UPSERT를 수행한다.
AI 서버는 group 검증만 수행한다.

사용 방법:
    await publish_graph_to_rdb(got_result, state, episode_id)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.graph_transformer import validate_group

logger = logging.getLogger(__name__)


async def publish_graph_to_rdb(
    got_result: dict,
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """GoT 결과를 Backend에 POST한다.

    Backend가 수신 후 EMA 계산 + UPSERT를 수행한다.
    AI 서버는 group 검증만 수행하고 계산하지 않는다.

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)
        episode_id: 에피소드 ID (빈 문자열이면 session_id로 생성)

    Returns:
        성공 시 True, 실패 시 False (파이프라인 비중단)
    """
    try:
        from src.api.backend_resources import RESOURCE_GRAPH_EPISODES, TYPE_GRAPH_EPISODE
        from src.api.contracts import SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            logger.warning("BackendClient가 초기화되지 않았습니다")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 전송을 건너뜁니다")
            return True

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        ep_id = episode_id or f"ep_{session_id}"

        # group 검증만 수행 (계산 없음)
        validated_nodes = []
        for node in got_nodes:
            validated = dict(node)
            validated["group"] = validate_group(node)
            validated_nodes.append(validated)

        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_GRAPH_EPISODE,
            data={
                "episode_id": ep_id,
                "got_result": {
                    "nodes": validated_nodes,
                    "edges": got_result.get("edges", []),
                },
            },
            timestamp=datetime.now(timezone.utc),
        )
        await backend_client.save(RESOURCE_GRAPH_EPISODES, request)
        logger.info(
            "에피소드 GoT 데이터 전송 완료 (episode=%s, nodes=%d)",
            ep_id,
            len(validated_nodes),
        )
        return True

    except Exception as e:
        logger.warning(
            "에피소드 GoT 데이터 전송 실패 — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False
```

---

## Task 2: test_graph_cumulative.py 재작성

**Files:**
- Modify: `tests/api/test_graph_cumulative.py`

삭제: `TestCalcEma`, `TestCalcTrend`, `TestMergeNodesFromGot`, `TestMergeEdgesFromGot`, `TestPublishGraphModeA`, `TestPublishGraphModeB`, `TestPublishGraphToRdb` (구 dispatcher 테스트)
신규: `TestPublishGraphToRdb` (rename된 함수 테스트)

- [ ] **Step 1: 테스트 파일 전체 재작성**

```python
"""tests/api/test_graph_cumulative.py — GoT → Backend 전송 모듈 테스트."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.graph_cumulative import publish_graph_to_rdb


@pytest.fixture
def mock_backend_client():
    """backend_client mock을 src.api.main에 주입한다."""
    mock_client = AsyncMock()
    mock_main = ModuleType("src.api.main")
    mock_main.backend_client = mock_client  # type: ignore[attr-defined]
    old = sys.modules.get("src.api.main")
    sys.modules["src.api.main"] = mock_main
    yield mock_client
    if old is not None:
        sys.modules["src.api.main"] = old
    else:
        sys.modules.pop("src.api.main", None)


class TestPublishGraphToRdb:
    @pytest.mark.asyncio
    async def test_success(self, mock_backend_client) -> None:
        mock_backend_client.save.return_value = MagicMock(success=True)

        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_to_rdb(got, state, "ep_123")
        assert result is True
        mock_backend_client.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_group_validated(self, mock_backend_client) -> None:
        mock_backend_client.save.return_value = MagicMock(success=True)

        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "INVALID", "intensity": 0.8}],
            "edges": [],
        }
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_to_rdb(got, state, "ep_123")
        assert result is True
        call_args = mock_backend_client.save.call_args
        saved_data = call_args[0][1]  # SaveRequest
        nodes = saved_data.data["got_result"]["nodes"]
        assert nodes[0]["group"] == "emotional_exhaustion"

    @pytest.mark.asyncio
    async def test_save_failure_returns_false(self, mock_backend_client) -> None:
        mock_backend_client.save.side_effect = Exception("server error")

        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_to_rdb(got, state, "ep_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_got_returns_true(self, mock_backend_client) -> None:
        got = {"nodes": [], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_to_rdb(got, state)
        assert result is True
        mock_backend_client.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_backend_client_returns_false(self) -> None:
        mock_main = ModuleType("src.api.main")
        mock_main.backend_client = None  # type: ignore[attr-defined]
        old = sys.modules.get("src.api.main")
        sys.modules["src.api.main"] = mock_main
        try:
            got = {
                "nodes": [
                    {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
                ]
            }
            result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
            assert result is False
        finally:
            if old is not None:
                sys.modules["src.api.main"] = old
            else:
                sys.modules.pop("src.api.main", None)

    @pytest.mark.asyncio
    async def test_episode_id_auto_generated(self, mock_backend_client) -> None:
        mock_backend_client.save.return_value = MagicMock(success=True)

        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        state = {"user_id": "u1", "session_id": "sess_abc"}

        await publish_graph_to_rdb(got, state)  # episode_id 미전달
        call_args = mock_backend_client.save.call_args
        saved_data = call_args[0][1]
        assert saved_data.data["episode_id"] == "ep_sess_abc"
```

- [ ] **Step 2: 테스트 실행 (Task 1~2 완료 후)**

```bash
pytest tests/api/test_graph_cumulative.py -v
```

예상 결과: 6개 PASS

---

## Task 3: 설정 파일 정리

**Files:**
- Modify: `config/loader.py` (라인 401-409)
- Modify: `config/settings.yaml` (라인 225-228)
- Modify: `src/api/backend_resources.py` (라인 48)

- [ ] **Step 1: config/loader.py — graph_upsert_mode, graph_ema_alpha 프로퍼티 삭제**

삭제 대상 (라인 401-409):
```python
    @property
    def graph_upsert_mode(self) -> str:
        """그래프 누적 저장 모드를 반환한다 ('ai_server' 또는 'backend')."""
        return str(self._config.get("graph", {}).get("upsert_mode", "ai_server"))

    @property
    def graph_ema_alpha(self) -> float:
        """그래프 EMA 가중치 알파값을 반환한다 (0.0~1.0)."""
        return float(self._config.get("graph", {}).get("ema_alpha", 0.3))
```

- [ ] **Step 2: config/settings.yaml — graph 블록 삭제**

삭제 대상 (라인 225-228):
```yaml
# 그래프 누적 저장 설정
graph:
  upsert_mode: "ai_server"   # "ai_server" | "backend"
  ema_alpha: 0.3              # EMA 최근 반영 비율 (0.0~1.0)
```

- [ ] **Step 3: backend_resources.py — RESOURCE_GRAPH_NODES 삭제**

삭제 대상 (라인 48):
```python
RESOURCE_GRAPH_NODES = "graph_nodes"
```

---

## Task 4: 전체 테스트 검증

- [ ] **Step 1: 관련 테스트 실행**

```bash
pytest tests/api/test_graph_cumulative.py tests/api/test_graph_routes.py -v
```

예상 결과: 전체 PASS (test_graph_cumulative: 6개, test_graph_routes: 5개)

- [ ] **Step 2: 전체 테스트 실행**

```bash
pytest tests/ -v --tb=short -q
```

예상 결과: 기존 통과 수 유지 (이전 29개 Mode A 테스트 → 6개로 감소, 나머지 영향 없음)

---

## Task 5: NEO4J_INTEGRATION.md 업데이트

**Files:**
- Modify: `docs/architecture/NEO4J_INTEGRATION.md`

주요 변경 섹션:
1. **섹션 6-3** (Mode A vs Mode B): 단일 흐름으로 대체
2. **섹션 6-4** Mode A 가이드 삭제, Mode B 가이드에서 "Mode B" 제거
3. **섹션 6-5** API 목록: ①②(Mode A 전용) 삭제, ③④ 유지 (번호 재정렬)
4. **섹션 7** Backend팀 요청사항 업데이트
5. **섹션 10** settings 예시에서 upsert_mode, ema_alpha 삭제

- [ ] **Step 1: 섹션 6-3 교체 — 단일 흐름으로**

기존 "Mode A vs Mode B 비교" 블록을 아래로 교체:

```markdown
### 6-3. RDB 누적 저장 흐름

AI 서버는 GoT 결과를 group 검증 후 Backend에 POST한다.
EMA 계산과 UPSERT는 Backend가 수행한다.

```
AI 서버 (app-2)                            Backend (app-3)
┌──────────────────────────────────┐       ┌──────────────────────┐
│ 1. group 검증                    │       │ 1. 기존 누적 데이터 조회│
│    (VALID_GROUPS 6개 체크)        │──POST─▶│ 2. EMA 계산           │
│ 2. GoT 결과를 그대로 전송         │       │    α=0.3 (설정 가능)  │
│    (계산 없음)                    │       │ 3. MySQL UPSERT       │
└──────────────────────────────────┘       └──────────────────────┘

장점: AI서버 부담 최소, EMA 로직 Backend 집중 관리
```

AI서버 참조 코드: `src/api/graph_cumulative.py` — `publish_graph_to_rdb()`
```

- [ ] **Step 2: 섹션 6-4 — Mode A 가이드 삭제, "Backend 구현 가이드" 단일화**

`#### Mode A — Backend 구현 가이드` 블록 전체 삭제 (라인 526~592).
`#### Mode B — Backend 구현 가이드` 제목을 `#### Backend 구현 가이드`로 변경.
본문의 "Mode B에서는", "Mode A와 Mode B의 데이터 차이:" 주석 제거.
"> 현재 기본값은 Mode A이며, ..." 주석 삭제 (라인 785).

- [ ] **Step 3: 섹션 6-5 API 목록 정리**

기존 (4종):
| 우선 | 엔드포인트 | 용도 |
| ① | GET graph_nodes | EMA 계산용 조회 (Mode A 전용) |
| ② | PUT graph_nodes | EMA 완료 데이터 저장 (Mode A 전용) |
| ③ | POST graph_nodes/episodes | GoT 원본 전송 |
| ④ | GET graph/users/{id}/data | 프론트엔드용 |

변경 후 (2종):
```markdown
| 순서 | 엔드포인트 | 메서드 | 용도 |
|------|-----------|--------|------|
| **①** | `/api/graph_nodes/episodes` | POST | AI서버 → GoT 에피소드 원본 전송 (EMA는 Backend가 수행) |
| **②** | `/api/graph/users/{id}/data` | GET | **프론트엔드용** — MySQL 누적 데이터 직접 서빙 |
```

- [ ] **Step 4: 섹션 7 Backend팀 요청사항 업데이트**

기존 4종 → 3종:
```markdown
| 순서 | 엔드포인트 | 용도 |
|------|----------|------|
| 1 | `POST /api/graph_nodes/episodes` | GoT 에피소드 수신 + EMA 계산 + UPSERT |
| 2 | `GET /api/graph/users/{id}/data` | 프론트엔드용 — RDB에서 직접 조회 |
```

삭제: `GET /api/graph_nodes?user_id=X`, `PUT /api/graph_nodes` (Mode A 전용)

- [ ] **Step 5: 섹션 10 settings 예시에서 graph 블록 삭제**

기존 (라인 1155-1163):
```yaml
# 데이터베이스 접속 정보
databases:
  neo4j:
    uri: "bolt://localhost:7687"

# 그래프 누적 저장 설정
graph:
  upsert_mode: "ai_server"   # "ai_server" (Mode A) | "backend" (Mode B)
  ema_alpha: 0.3
```

변경 후:
```yaml
# 데이터베이스 접속 정보
databases:
  neo4j:
    uri: "bolt://localhost:7687"
```

---

## Task 6: 커밋

- [ ] **Step 1: 관련 테스트 최종 확인**

```bash
pytest tests/api/test_graph_cumulative.py tests/api/test_graph_routes.py -v
```

- [ ] **Step 2: 커밋**

```bash
git add src/api/graph_cumulative.py \
        tests/api/test_graph_cumulative.py \
        config/loader.py \
        config/settings.yaml \
        src/api/backend_resources.py \
        docs/architecture/NEO4J_INTEGRATION.md

git commit -m "refactor: Mode A 삭제, GoT→Backend 단일 전송 흐름으로 통합"
```

---

## 변경 전후 비교

| 항목 | 변경 전 | 변경 후 |
|------|--------|--------|
| graph_cumulative.py 함수 수 | 7개 | 1개 (`publish_graph_to_rdb`) |
| settings.yaml graph 블록 | upsert_mode + ema_alpha | 제거 |
| Backend 필요 API | 4종 | 2종 |
| 테스트 수 | 29개 | 6개 |
| EMA 계산 위치 | AI서버 (Mode A) / Backend (Mode B) | **Backend만** |

---

*작성일: 2026-04-07 | 브랜치: feature/reasoning-code-quality-cleanup*

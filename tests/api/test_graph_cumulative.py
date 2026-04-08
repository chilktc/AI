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
      - load_graph_cumulative: GraphCumulativeData() 반환 (신규 사용자)
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
        # 0.5 - 0.06 = 0.44 → decreasing (부동소수점 경계값 회피)
        assert _calc_trend(0.5, 0.44) == "decreasing"


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
        assert node["weight"] == 0.69  # 0.3×0.9 + 0.7×0.6
        assert node["mention_count"] == 3
        assert node["trend"] == "increasing"  # delta = +0.09 ≥ 0.05
        assert node["last_seen"] == _NOW_ISO
        assert node["first_seen"] == "2026-04-01T00:00:00+00:00"  # 변경 없음

    def test_existing_grp_uppercase_normalized(self) -> None:
        """BE 더미 데이터의 UPPER_CASE grp도 소문자로 정규화되어 매칭된다."""
        existing = [
            {
                "label": "번아웃",
                "grp": "EMOTIONAL_EXHAUSTION",
                "weight": 0.6,
                "mention_count": 1,
                "trend": "stable",
                "first_seen": "2026-04-01T00:00:00+00:00",
                "last_seen": "2026-04-07T00:00:00+00:00",
            }
        ]
        got = [{"label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.9}]
        result = _merge_nodes(existing, got, _NOW, alpha=0.3)
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
        """신규 사용자: GET → 빈 데이터, 신규 노드로 PUT."""
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
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
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.9}
            ],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is True
        call_args = mock_backend_client.put_graph_cumulative.call_args
        saved = call_args[0][0]
        put_nodes = saved.data["nodes"]
        assert put_nodes[0]["weight"] == 0.69  # 0.3×0.9 + 0.7×0.6
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
            got = {
                "nodes": [
                    {
                        "id": "1",
                        "label": "번아웃",
                        "group": "emotional_exhaustion",
                        "intensity": 0.8,
                    }
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
    async def test_new_user_404_returns_empty_data_not_error(self, mock_backend_client) -> None:
        """신규 사용자(404): 빈 데이터로 PUT 정상 진행 (에러 아님)."""
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "new_user", "session_id": "s1"})
        assert result is True
        mock_backend_client.put_graph_cumulative.assert_awaited_once()
        call_args = mock_backend_client.put_graph_cumulative.call_args
        saved = call_args[0][0]
        assert saved.data["nodes"][0]["mention_count"] == 1
        assert saved.data["nodes"][0]["trend"] == "stable"

    @pytest.mark.asyncio
    async def test_get_error_none_falls_back_and_puts(self, mock_backend_client) -> None:
        """GET 에러(None): 빈 데이터로 대체 후 PUT 진행 (graceful degradation)."""
        mock_backend_client.load_graph_cumulative.return_value = None
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is True
        mock_backend_client.put_graph_cumulative.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_put_failure_returns_false(self, mock_backend_client) -> None:
        """PUT 실패 시 False 반환 (파이프라인 비중단)."""
        mock_backend_client.put_graph_cumulative.return_value = False
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, mock_backend_client) -> None:
        """예외 발생 시 False 반환 (파이프라인 비중단)."""
        mock_backend_client.load_graph_cumulative.side_effect = RuntimeError("network error")
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}
            ],
            "edges": [],
        }
        result = await publish_graph_to_rdb(got, {"user_id": "u1", "session_id": "s1"})
        assert result is False

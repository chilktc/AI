"""tests/api/test_graph_cumulative.py — 누적 그래프 UPSERT 모듈 테스트."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.graph_cumulative import (
    calc_ema,
    calc_trend,
    merge_edges_from_got,
    merge_nodes_from_got,
    publish_graph_cumulative_mode_a,
    publish_graph_raw_mode_b,
    publish_graph_to_rdb,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixture: src.api.main mock 모듈 주입 (Python 3.9 호환)
# ═══════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════
# calc_ema
# ═══════════════════════════════════════════════════════════════════════


class TestCalcEma:
    def test_basic_calculation(self) -> None:
        result = calc_ema(0.80, 0.7, alpha=0.3)
        assert round(result, 2) == 0.77

    def test_custom_alpha(self) -> None:
        result = calc_ema(0.80, 0.7, alpha=0.5)
        assert round(result, 2) == 0.75

    def test_clamp_upper(self) -> None:
        result = calc_ema(1.0, 1.0, alpha=0.3)
        assert result <= 1.0

    def test_clamp_lower(self) -> None:
        result = calc_ema(0.0, 0.0, alpha=0.3)
        assert result >= 0.0


# ═══════════════════════════════════════════════════════════════════════
# calc_trend
# ═══════════════════════════════════════════════════════════════════════


class TestCalcTrend:
    def test_increasing(self) -> None:
        assert calc_trend(0.50, 0.70) == "increasing"

    def test_decreasing(self) -> None:
        assert calc_trend(0.80, 0.60) == "decreasing"

    def test_stable(self) -> None:
        assert calc_trend(0.80, 0.77) == "stable"

    def test_boundary_within_threshold(self) -> None:
        # diff = 0.04 → stable
        assert calc_trend(0.50, 0.54) == "stable"
        # diff = -0.04 → stable
        assert calc_trend(0.54, 0.50) == "stable"

    def test_boundary_just_above_threshold(self) -> None:
        # diff = 0.06 → increasing
        assert calc_trend(0.50, 0.56) == "increasing"
        # diff = -0.06 → decreasing
        assert calc_trend(0.56, 0.50) == "decreasing"


# ═══════════════════════════════════════════════════════════════════════
# merge_nodes_from_got
# ═══════════════════════════════════════════════════════════════════════


class TestMergeNodesFromGot:
    def test_new_nodes_added(self) -> None:
        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}]}
        result = merge_nodes_from_got(got, [], alpha=0.3)
        assert len(result) == 1
        assert result[0]["label"] == "번아웃"
        assert result[0]["weight"] == 0.8
        assert result[0]["mention_count"] == 1
        assert result[0]["trend"] == "stable"

    def test_existing_node_ema_update(self) -> None:
        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.7}]}
        existing = [{"label": "번아웃", "grp": "emotional_exhaustion", "weight": 0.8, "mention_count": 1, "first_seen": "2026-01-01"}]
        result = merge_nodes_from_got(got, existing, alpha=0.3)
        assert len(result) == 1
        assert round(result[0]["weight"], 2) == 0.77
        assert result[0]["mention_count"] == 2
        assert result[0]["first_seen"] == "2026-01-01"  # 유지

    def test_mixed_new_and_existing(self) -> None:
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.7},
                {"id": "2", "label": "업무과부하", "group": "work_structure", "intensity": 0.9},
            ]
        }
        existing = [{"label": "번아웃", "grp": "emotional_exhaustion", "weight": 0.8, "mention_count": 2}]
        result = merge_nodes_from_got(got, existing, alpha=0.3)
        assert len(result) == 2
        labels = {n["label"] for n in result}
        assert labels == {"번아웃", "업무과부하"}

    def test_invalid_group_corrected(self) -> None:
        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "INVALID", "intensity": 0.5}]}
        result = merge_nodes_from_got(got, [], alpha=0.3)
        assert result[0]["grp"] == "emotional_exhaustion"  # keyword fallback

    def test_trend_calculation(self) -> None:
        got = {"nodes": [{"id": "1", "label": "업무과부하", "group": "work_structure", "intensity": 0.9}]}
        existing = [{"label": "업무과부하", "grp": "work_structure", "weight": 0.5, "mention_count": 1}]
        result = merge_nodes_from_got(got, existing, alpha=0.3)
        # new_weight = 0.3*0.9 + 0.7*0.5 = 0.62, diff = 0.12 > 0.05
        assert result[0]["trend"] == "increasing"


# ═══════════════════════════════════════════════════════════════════════
# merge_edges_from_got
# ═══════════════════════════════════════════════════════════════════════


class TestMergeEdgesFromGot:
    def test_new_edge_added(self) -> None:
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion"},
                {"id": "2", "label": "업무과부하", "group": "work_structure"},
            ],
            "edges": [{"from": "1", "to": "2", "relationship": "causes"}],
        }
        result = merge_edges_from_got(got, [])
        assert len(result) == 1
        assert result[0]["source_label"] == "번아웃"
        assert result[0]["target_label"] == "업무과부하"
        assert result[0]["weight"] == 1

    def test_existing_edge_weight_incremented(self) -> None:
        got = {
            "nodes": [
                {"id": "1", "label": "번아웃", "group": "emotional_exhaustion"},
                {"id": "2", "label": "업무과부하", "group": "work_structure"},
            ],
            "edges": [{"from": "1", "to": "2"}],
        }
        existing = [{
            "source_label": "번아웃",
            "source_grp": "emotional_exhaustion",
            "target_label": "업무과부하",
            "target_grp": "work_structure",
            "weight": 2,
        }]
        result = merge_edges_from_got(got, existing)
        assert result[0]["weight"] == 3

    def test_self_loop_skipped(self) -> None:
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion"}],
            "edges": [{"from": "1", "to": "1"}],
        }
        result = merge_edges_from_got(got, [])
        assert len(result) == 0

    def test_missing_node_reference_skipped(self) -> None:
        got = {
            "nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion"}],
            "edges": [{"from": "1", "to": "999"}],  # 999 존재하지 않음
        }
        result = merge_edges_from_got(got, [])
        assert len(result) == 0

    def test_multiple_edges(self) -> None:
        got = {
            "nodes": [
                {"id": "1", "label": "A", "group": "work_structure"},
                {"id": "2", "label": "B", "group": "leadership"},
                {"id": "3", "label": "C", "group": "peer_relations"},
            ],
            "edges": [
                {"from": "1", "to": "2"},
                {"from": "2", "to": "3"},
            ],
        }
        result = merge_edges_from_got(got, [])
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════
# publish_graph_cumulative_mode_a (비동기)
# ═══════════════════════════════════════════════════════════════════════


class TestPublishGraphModeA:
    @pytest.mark.asyncio
    async def test_success(self, mock_backend_client) -> None:
        mock_load_resp = MagicMock()
        mock_load_resp.data = [{"nodes": [], "edges": []}]
        mock_backend_client.load.return_value = mock_load_resp
        mock_backend_client.update.return_value = MagicMock(success=True)

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_cumulative_mode_a(got, state)
        assert result is True
        mock_backend_client.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_failure_continues(self, mock_backend_client) -> None:
        mock_backend_client.load.side_effect = Exception("connection error")
        mock_backend_client.update.return_value = MagicMock(success=True)

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_cumulative_mode_a(got, state)
        assert result is True  # load 실패해도 최초 저장으로 진행

    @pytest.mark.asyncio
    async def test_update_failure_returns_false(self, mock_backend_client) -> None:
        mock_load_resp = MagicMock()
        mock_load_resp.data = []
        mock_backend_client.load.return_value = mock_load_resp
        mock_backend_client.update.side_effect = Exception("server error")

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_cumulative_mode_a(got, state)
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_got_returns_true(self, mock_backend_client) -> None:
        got = {"nodes": [], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_cumulative_mode_a(got, state)
        assert result is True


# ═══════════════════════════════════════════════════════════════════════
# publish_graph_raw_mode_b (비동기)
# ═══════════════════════════════════════════════════════════════════════


class TestPublishGraphModeB:
    @pytest.mark.asyncio
    async def test_success(self, mock_backend_client) -> None:
        mock_backend_client.save.return_value = MagicMock(success=True)

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_raw_mode_b(got, state, "ep_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_group_validated(self, mock_backend_client) -> None:
        mock_backend_client.save.return_value = MagicMock(success=True)

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "INVALID", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_raw_mode_b(got, state, "ep_123")
        assert result is True
        # save 호출 시 group이 검증되었는지 확인
        call_args = mock_backend_client.save.call_args
        saved_data = call_args[0][1]  # SaveRequest
        nodes = saved_data.data["got_result"]["nodes"]
        assert nodes[0]["group"] == "emotional_exhaustion"

    @pytest.mark.asyncio
    async def test_save_failure_returns_false(self, mock_backend_client) -> None:
        mock_backend_client.save.side_effect = Exception("server error")

        got = {"nodes": [{"id": "1", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.8}], "edges": []}
        state = {"user_id": "u1", "session_id": "s1"}

        result = await publish_graph_raw_mode_b(got, state, "ep_123")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════
# publish_graph_to_rdb (디스패처)
# ═══════════════════════════════════════════════════════════════════════


class TestPublishGraphToRdb:
    @pytest.mark.asyncio
    async def test_dispatches_mode_a(self) -> None:
        mock_settings = MagicMock()
        mock_settings.graph_upsert_mode = "ai_server"
        mock_settings.graph_ema_alpha = 0.3

        with patch("src.api.graph_cumulative.get_settings", return_value=mock_settings), \
             patch("src.api.graph_cumulative.publish_graph_cumulative_mode_a", new_callable=AsyncMock) as mock_a:
            mock_a.return_value = True
            result = await publish_graph_to_rdb({"nodes": []}, {"user_id": "u1"})
            mock_a.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_dispatches_mode_b(self) -> None:
        mock_settings = MagicMock()
        mock_settings.graph_upsert_mode = "backend"

        with patch("src.api.graph_cumulative.get_settings", return_value=mock_settings), \
             patch("src.api.graph_cumulative.publish_graph_raw_mode_b", new_callable=AsyncMock) as mock_b:
            mock_b.return_value = True
            result = await publish_graph_to_rdb({"nodes": []}, {"user_id": "u1"}, "ep_123")
            mock_b.assert_called_once()
            assert result is True

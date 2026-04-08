"""tests/api/test_graph_cumulative.py — GoT → Backend 전송 모듈 테스트."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.graph_cumulative import publish_graph_to_rdb

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
# publish_graph_to_rdb
# ═══════════════════════════════════════════════════════════════════════


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

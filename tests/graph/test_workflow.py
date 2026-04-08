"""tests/graph/test_workflow.py — async_post_processing_node 단위 테스트."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.graph.workflow import async_post_processing_node


@pytest.mark.asyncio
async def test_async_post_calls_episode_memory_save_when_flag_set():
    """memory_write=True인 state에서 EpisodeMemoryAgent._save_to_store가 호출된다."""
    state = {
        "memory_write": True,
        "memory_text": "오늘의 팟캐스트 에피소드 텍스트입니다.",
        "memory_metadata": {
            "user_id": "user_01",
            "session_id": "sess_01",
            "episode_id": "ep_01",
            "episode_title": "테스트",
        },
        "final_output": '{"episode_id": "ep_01"}',
    }

    with patch("src.graph.workflow.EpisodeMemoryAgent") as MockEpisodeMemory:
        mock_instance = MagicMock()
        mock_instance._save_to_store = AsyncMock(return_value=True)
        MockEpisodeMemory.return_value = mock_instance

        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            await async_post_processing_node(state)

        mock_instance._save_to_store.assert_called_once_with(
            "오늘의 팟캐스트 에피소드 텍스트입니다.",
            {
                "user_id": "user_01",
                "session_id": "sess_01",
                "episode_id": "ep_01",
                "episode_title": "테스트",
            },
        )


@pytest.mark.asyncio
async def test_async_post_skips_memory_save_when_flag_not_set():
    """memory_write가 없거나 False이면 EpisodeMemoryAgent가 생성되지 않는다."""
    state = {
        "final_output": '{"episode_id": "ep_01"}',
    }

    with patch("src.graph.workflow.EpisodeMemoryAgent") as MockEpisodeMemory:
        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            await async_post_processing_node(state)

        MockEpisodeMemory.assert_not_called()


@pytest.mark.asyncio
async def test_async_post_memory_save_failure_does_not_raise():
    """EpisodeMemoryAgent._save_to_store가 예외를 던져도 파이프라인에 영향 없음."""
    state = {
        "memory_write": True,
        "memory_text": "텍스트",
        "memory_metadata": {"user_id": "u1"},
    }

    with patch("src.graph.workflow.EpisodeMemoryAgent") as MockEpisodeMemory:
        mock_instance = MagicMock()
        mock_instance._save_to_store = AsyncMock(side_effect=RuntimeError("Pinecone 연결 실패"))
        MockEpisodeMemory.return_value = mock_instance

        with patch("src.graph.workflow.learning_node", new_callable=AsyncMock) as mock_learning:
            mock_learning.return_value = {}
            result = await async_post_processing_node(state)

        assert isinstance(result, dict)

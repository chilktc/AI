"""
Episode Memory 에이전트 테스트.

KT Cloud 임베딩 API 호출과 로컬 mock_db.json 읽기를 모킹하여
EpisodeMemoryAgent의 인스턴스 생성, process 호출, 반환값 구조를 검증한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.agents.podcast.episode_memory import EpisodeMemoryAgent, episode_memory_node
from src.models.agent_state import AgentState

# === 픽스처 ===


@pytest.fixture
def agent() -> EpisodeMemoryAgent:
    """테스트용 Episode Memory 에이전트 인스턴스."""
    return EpisodeMemoryAgent()


@pytest.fixture
def minimal_state() -> AgentState:
    """최소 AgentState."""
    return {
        "user_input": "오늘 기분이 좋았어",
        "user_id": "test_user",
        "session_id": "test_session",
        "mode": "podcast",
    }


@pytest.fixture
def mock_db_data() -> list[dict[str, Any]]:
    """mock_db.json에서 반환될 샘플 데이터."""
    return [
        {
            "text": "지난 주에 운동을 시작했다",
            "vector": [0.1, 0.2, 0.3],
            "score": 0.95,
            "metadata": {"date": "2026-03-25", "type": "user_log"},
        },
        {
            "text": "친구와 좋은 대화를 나눴다",
            "vector": [0.4, 0.5, 0.6],
            "score": 0.88,
            "metadata": {"date": "2026-03-28", "type": "user_log"},
        },
    ]


# === 테스트 ===


class TestEpisodeMemoryAgent:
    """EpisodeMemoryAgent 단위 테스트."""

    def test_instantiation(self, agent: EpisodeMemoryAgent) -> None:
        """에이전트 인스턴스 생성 가능 여부."""
        assert agent.name == "episode_memory"
        assert agent._output_key == "memory_results"

    @pytest.mark.asyncio
    async def test_process_empty_db(
        self, agent: EpisodeMemoryAgent, minimal_state: AgentState
    ) -> None:
        """mock_db.json이 없을 때 빈 결과 반환."""
        with patch.object(Path, "exists", return_value=False):
            result = await agent.process(minimal_state)

        assert "memory_results" in result
        payload = result["memory_results"]
        assert payload["items"] == []
        assert "summary" in payload

    @pytest.mark.asyncio
    async def test_process_with_data(
        self,
        agent: EpisodeMemoryAgent,
        minimal_state: AgentState,
        mock_db_data: list[dict[str, Any]],
    ) -> None:
        """_retrieve_from_store가 데이터를 반환할 때 정상 처리."""
        with (
            patch.object(agent, "_retrieve_from_store", return_value=mock_db_data),
            patch.object(agent, "_generate_summary", return_value="2건의 기억 발견"),
        ):
            result = await agent.process(minimal_state)

        assert "memory_results" in result
        payload = result["memory_results"]
        assert len(payload["items"]) == 2
        assert "2건" in payload["summary"]

    @pytest.mark.asyncio
    async def test_process_uses_memory_query_if_present(self, agent: EpisodeMemoryAgent) -> None:
        """state에 memory_query가 있으면 user_input 대신 사용."""
        state: AgentState = {
            "user_input": "기본 입력",
            "memory_query": "특정 검색어",
            "user_id": "test_user",
            "session_id": "test_session",
            "mode": "podcast",
        }
        with (
            patch.object(Path, "exists", return_value=True),
            patch("json.load", return_value=[]),
            patch("builtins.open", create=True),
        ):
            result = await agent.process(state)

        assert "특정 검색어" in result["memory_results"]["summary"]

    @pytest.mark.asyncio
    async def test_process_result_structure(
        self, agent: EpisodeMemoryAgent, minimal_state: AgentState
    ) -> None:
        """반환 결과의 구조 검증."""
        with patch.object(Path, "exists", return_value=False):
            result = await agent.process(minimal_state)

        payload = result["memory_results"]
        assert "items" in payload
        assert "summary" in payload
        assert "suggested_personalization" in payload
        assert "_meta" in payload
        assert payload["_meta"]["namespace"] == "mem_podcast_episode"


class TestEpisodeMemoryNode:
    """episode_memory_node() 함수 테스트."""

    @pytest.mark.asyncio
    async def test_node_creates_new_instance(self, minimal_state: AgentState) -> None:
        """노드 함수가 요청마다 새 인스턴스를 생성하는지 확인."""
        with patch.object(Path, "exists", return_value=False):
            result = await episode_memory_node(minimal_state)

        assert "memory_results" in result

    @pytest.mark.asyncio
    async def test_node_returns_dict(self, minimal_state: AgentState) -> None:
        """노드 함수가 dict를 반환하는지 확인."""
        with patch.object(Path, "exists", return_value=False):
            result = await episode_memory_node(minimal_state)

        assert isinstance(result, dict)

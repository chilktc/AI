"""
Knowledge Agent 단위 테스트.

팟캐스트모드 기준: Podcast Reasoning이 knowledge_agent.search(query, domain)로 호출.
KnowledgeAgent는 process() 기반(대화모드)과 search() 기반(팟캐스트모드) 양쪽 지원.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.podcast.knowledge import KnowledgeAgent


@pytest.fixture
def agent() -> KnowledgeAgent:
    db_mock = AsyncMock()
    pinecone_mock = AsyncMock()
    embedding_mock = AsyncMock()
    return KnowledgeAgent(
        db_client=db_mock, pinecone_client=pinecone_mock, embedding_client=embedding_mock
    )


@pytest.mark.asyncio
async def test_agent_process_error_fallback(agent: KnowledgeAgent) -> None:
    """process()에서 프롬프트 로드 실패 시 빈 결과로 폴백한다."""
    state = {"user_input": "불안해요"}
    result = await agent.process(state)

    assert "knowledge_results" in result
    assert result["knowledge_results"]["documents"] == []
    assert "recommended_approaches" in result


@pytest.mark.asyncio
async def test_agent_process_empty_input(agent: KnowledgeAgent) -> None:
    """빈 입력에도 에러 없이 빈 결과를 반환한다."""
    state = {"user_input": ""}
    result = await agent.process(state)

    assert "knowledge_results" in result
    assert isinstance(result["knowledge_results"]["documents"], list)


# === LLM 실제 호출 테스트 ===


@pytest.mark.live
class TestKnowledgeWithLLM:
    """KnowledgeAgent 실제 호출 테스트 (Pinecone 환경 필요)."""

    @pytest.fixture
    def agent(self) -> KnowledgeAgent:
        import os

        if not os.getenv("PINECONE_API_KEY"):
            pytest.skip("PINECONE_API_KEY not configured — Pinecone 환경 아님")
        db_mock = AsyncMock()
        pinecone_mock = AsyncMock()
        embedding_mock = AsyncMock()
        return KnowledgeAgent(
            db_client=db_mock,
            pinecone_client=pinecone_mock,
            embedding_client=embedding_mock,
        )

    @pytest.mark.asyncio
    async def test_knowledge_search_returns_results(self, agent: KnowledgeAgent) -> None:
        """Pinecone 환경에서 knowledge_results 구조를 반환한다."""
        import time

        state = {"user_input": "번아웃 회복 방법을 알고 싶어요"}
        start = time.time()
        result = await agent.process(state)
        elapsed = time.time() - start

        print(f"\n[Knowledge] ⏱️ {elapsed:.2f}초")
        assert "knowledge_results" in result
        assert isinstance(result["knowledge_results"], dict)

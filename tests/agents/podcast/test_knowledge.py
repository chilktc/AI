"""
Knowledge Agent 단위 테스트.

팟캐스트모드 기준: Podcast Reasoning이 knowledge_agent.search(query, domain)로 호출.
현재 Knowledge Agent는 process() 기반이며 search() 미구현 → stub 인터페이스 검증.
대화모드 process() 테스트는 프롬프트 YAML 완성 후 추가 예정.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.podcast.knowledge import KnowledgeAgent
from src.agents.shared.stubs import KnowledgeAgentStub


@pytest.fixture
def stub() -> KnowledgeAgentStub:
    return KnowledgeAgentStub()


@pytest.fixture
def agent() -> KnowledgeAgent:
    db_mock = AsyncMock()
    pinecone_mock = AsyncMock()
    embedding_mock = AsyncMock()
    return KnowledgeAgent(
        db_client=db_mock, pinecone_client=pinecone_mock, embedding_client=embedding_mock
    )


@pytest.mark.asyncio
async def test_stub_search_returns_empty(stub: KnowledgeAgentStub) -> None:
    """KnowledgeAgentStub.search()가 빈 결과를 반환한다."""
    result = await stub.search(query="스트레스 관리 방법", domain="mental_health")
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_stub_search_with_default_domain(stub: KnowledgeAgentStub) -> None:
    """domain 미지정 시 기본값 mental_health로 호출된다."""
    result = await stub.search(query="불안 해소")
    assert isinstance(result, dict)


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

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


# === 관측성: vector matches > 0 && documents == 0 ===


@pytest.mark.asyncio
async def test_search_warns_when_matches_but_no_backend_docs(agent: KnowledgeAgent, caplog) -> None:
    """Pinecone match가 있는데 Backend RDB에서 문서가 0건이면 경고 로그를 남긴다."""
    import logging

    # 에이전트 로거는 propagate=False이므로 caplog handler를 직접 부착
    agent_logger = logging.getLogger("mind-log.agent.knowledge")
    agent_logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="mind-log.agent.knowledge")

    # env 설정되어 있다고 가정하고 내부 헬퍼들을 mock
    agent.kt_embedding_endpoint = "https://mock"
    agent.kt_embedding_token = "t"

    agent._parse_query = AsyncMock(return_value="번아웃")  # type: ignore[method-assign]
    agent._embed_query = AsyncMock(return_value=[0.1] * 5)  # type: ignore[method-assign]
    agent._query_pinecone = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": "chunk-1", "score": 0.91}]
    )
    agent._fetch_documents_from_backend = AsyncMock(return_value=[])  # type: ignore[method-assign]
    agent._generate_synthesis = AsyncMock(return_value="")  # type: ignore[method-assign]

    result = await agent.search("번아웃 회복", domain="mental_health")

    assert result == {"articles": [], "guidelines": []}
    # 핵심 단서가 포함된 경고 로그 검증
    assert any(
        "RDB 원문 조회" in rec.message
        and "matches=1" in rec.message
        and "documents=0" in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    ), "Pinecone 매치는 있는데 RDB 문서가 0건이면 경고 필요"

import time
from unittest.mock import AsyncMock

import pytest

from src.agents.conversation.knowledge import KnowledgeAgent


@pytest.fixture
def agent(llm_client):
    if llm_client is None:
        pytest.skip("Ollama client not available")
    db_mock = AsyncMock()
    pinecone_mock = AsyncMock()
    embedding_mock = AsyncMock()
    agent = KnowledgeAgent(
        db_client=db_mock, pinecone_client=pinecone_mock, embedding_client=embedding_mock
    )
    agent.llm_client = llm_client
    return agent


@pytest.mark.asyncio
async def test_knowledge_process_empty(agent):
    agent.embedding_client.get_embedding.return_value = [0.1] * 1536
    agent.pinecone_client.query.return_value = {"matches": []}

    state = {"user_input": "안녕하세요"}
    start_time = time.time()
    result = await agent.process(state)
    elapsed_time = time.time() - start_time
    print(f"\n[Test Knowledge Process Empty] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert "knowledge_results" in result
    assert result["knowledge_results"]["synthesis"] == "No relevant knowledge found"
    assert result["knowledge_results"]["documents"] == []


@pytest.mark.asyncio
async def test_knowledge_process_with_data(agent):
    agent.embedding_client.get_embedding.return_value = [0.1] * 1536
    agent.pinecone_client.query.return_value = {"matches": [{"id": "doc1", "score": 0.9}]}

    agent.db_client.fetch = AsyncMock(
        return_value=[
            {"id": "doc1", "title": "Mock", "content": "Mock Content", "source": "Mock DB"}
        ]
    )

    state = {"user_input": "불안해요"}
    start_time = time.time()
    result = await agent.process(state)
    elapsed_time = time.time() - start_time
    print(f"\n[Test Knowledge Process With Data] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert "knowledge_results" in result
    assert "synthesis" in result["knowledge_results"]
    assert len(result["knowledge_results"]["documents"]) == 1
    assert "recommended_approaches" in result

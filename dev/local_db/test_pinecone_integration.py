"""Pinecone Mock 벡터 검색 통합 테스트."""
from __future__ import annotations

import pytest

from dev.local_db.seed import _generate_deterministic_vector

pytestmark = pytest.mark.asyncio


class TestPineconeMockQueries:
    """PineconeMockClient 시드 데이터 기반 검색 테스트."""

    async def test_knowledge_domain_filter_search(self, pinecone_client):
        """KnowledgeAgent 패턴: domain 필터로 psychology 문서를 검색한다."""
        query_vector = _generate_deterministic_vector(42, 384)  # doc001과 동일

        result = await pinecone_client.query(
            index="expert_knowledge",
            vector=query_vector,
            filter={"domain": {"$in": ["psychology"]}},
            top_k=5,
            namespace="psychology",
        )

        matches = result["matches"]
        assert len(matches) >= 1
        assert matches[0]["id"] == "vec_knowledge_doc001"
        assert matches[0]["metadata"]["domain"] == "psychology"

    async def test_episode_memory_namespace_search(self, pinecone_client):
        """EpisodeMemory 패턴: 사용자 namespace에서 에피소드를 검색한다."""
        query_vector = _generate_deterministic_vector(200, 384)  # ep001 시드

        result = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=query_vector,
            top_k=5,
            namespace="test-user-001",
        )

        matches = result["matches"]
        assert len(matches) >= 1
        assert matches[0]["metadata"]["episode_id"] == "ep-test-001"

    async def test_upsert_and_retrieve(self, pinecone_client):
        """라운드트립: upsert 후 동일 벡터로 query하여 검색한다."""
        test_vec = _generate_deterministic_vector(999, 384)

        await pinecone_client.upsert(
            index="test_index",
            vectors=[{
                "id": "vec_inttest_001",
                "values": test_vec,
                "metadata": {"label": "integration_test"},
            }],
            namespace="inttest",
        )

        result = await pinecone_client.query(
            index="test_index",
            vector=test_vec,
            top_k=5,
            namespace="inttest",
        )

        matches = result["matches"]
        assert len(matches) == 1
        assert matches[0]["id"] == "vec_inttest_001"

    async def test_filter_excludes_non_matching(self, pinecone_client):
        """$ne 필터: psychology가 아닌 문서만 반환한다."""
        query_vector = _generate_deterministic_vector(42, 384)

        result = await pinecone_client.query(
            index="expert_knowledge",
            vector=query_vector,
            filter={"domain": {"$ne": "psychology"}},
            top_k=10,
            namespace="psychology",
        )

        matches = result["matches"]
        for match in matches:
            assert match["metadata"]["domain"] != "psychology"

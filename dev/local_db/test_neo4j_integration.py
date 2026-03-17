"""Neo4j 에이전트 쿼리 패턴 통합 테스트."""
from __future__ import annotations

import pytest

from dev.local_db.conftest import requires_neo4j

pytestmark = pytest.mark.asyncio


@requires_neo4j
class TestNeo4jAgentQueries:
    """PodcastReasoning 등 에이전트가 사용하는 Neo4j 쿼리 패턴을 검증한다."""

    async def test_topic_lookup(self, neo4j_client, seed_data):
        """PodcastReasoning: Topic 노드 조회."""
        query = "MATCH (n:Topic) WHERE n.topic_name = $name RETURN n"
        results = await neo4j_client.execute_query(query, params={"name": "work_stress"})

        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        node = results[0]["n"]
        assert node["domain"] == "work"

    async def test_got_traversal(self, neo4j_client, seed_data):
        """PodcastReasoning: GoTNode 그래프 탐색 (1~3 hop)."""
        query = (
            "MATCH (root:GoTNode {got_node_id: $id})-[:LEADS_TO*1..3]->(leaf:GoTNode) "
            "RETURN leaf.got_node_id AS id, leaf.label AS label, leaf.node_type AS type"
        )
        results = await neo4j_client.execute_query(query, params={"id": "got-test-001"})

        assert len(results) >= 1, f"Expected >= 1 results, got {len(results)}"
        ids = [r["id"] for r in results]
        assert "got-test-002" in ids, f"got-test-002 not found in {ids}"
        assert "got-test-003" in ids, f"got-test-003 not found in {ids}"

    async def test_full_reasoning_chain(self, neo4j_client, seed_data):
        """Session → GoTNode 전체 체인 탐색."""
        query = (
            "MATCH (s:Session {session_id: $sid})-[:REASONED_BY]->(root:GoTNode)"
            "-[:LEADS_TO*0..5]->(node:GoTNode) "
            "RETURN node.got_node_id AS id, node.node_type AS type"
        )
        results = await neo4j_client.execute_query(
            query, params={"sid": "sess_test000001"}
        )

        assert len(results) >= 3, f"Expected >= 3 results, got {len(results)}"
        types = [r["type"] for r in results]
        assert "root" in types, f"'root' type not found in {types}"
        assert "leaf" in types, f"'leaf' type not found in {types}"

    async def test_session_covers_topic(self, neo4j_client, seed_data):
        """Session → Topic COVERS 관계 조회."""
        query = (
            "MATCH (s:Session {session_id: $sid})-[:COVERS]->(t:Topic) "
            "RETURN t.topic_name AS topic, t.domain AS domain"
        )
        results = await neo4j_client.execute_query(
            query, params={"sid": "sess_test000001"}
        )

        assert len(results) >= 1, f"Expected >= 1 results, got {len(results)}"
        topics = [r["topic"] for r in results]
        assert "work_stress" in topics, f"'work_stress' not found in {topics}"

    async def test_emotion_cooccurrence(self, neo4j_client, seed_data):
        """Emotion 동시 발생 관계 조회."""
        query = (
            "MATCH (e1:Emotion {emotion_key: $key})-[r:OFTEN_COOCCURS]->(e2:Emotion) "
            "RETURN e2.emotion_key AS cooccurs_with, r.count AS count"
        )
        results = await neo4j_client.execute_query(query, params={"key": "anxiety"})

        assert len(results) >= 1, f"Expected >= 1 results, got {len(results)}"
        cooccurs = [r["cooccurs_with"] for r in results]
        assert "stress" in cooccurs, f"'stress' not found in {cooccurs}"

    async def test_create_and_cleanup_got_node(self, neo4j_client):
        """GoTNode 생성 → 조회 → 삭제 라이프사이클."""
        node_id = "got-inttest-001"
        try:
            # CREATE
            create_query = (
                "CREATE (g:GoTNode {"
                "  got_node_id: $id,"
                "  node_type: 'root',"
                "  label: '통합테스트 루트',"
                "  episode_id: 'ep-inttest'"
                "}) RETURN g"
            )
            await neo4j_client.execute_query(create_query, params={"id": node_id})

            # 조회 확인
            read_query = (
                "MATCH (g:GoTNode {got_node_id: $id}) "
                "RETURN g.got_node_id AS id, g.node_type AS type"
            )
            results = await neo4j_client.execute_query(read_query, params={"id": node_id})

            assert len(results) == 1, f"Expected 1 result, got {len(results)}"
            assert results[0]["type"] == "root"
        finally:
            # DETACH DELETE
            cleanup_query = (
                "MATCH (g:GoTNode {got_node_id: $id}) DETACH DELETE g"
            )
            await neo4j_client.execute_query(cleanup_query, params={"id": node_id})

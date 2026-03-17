"""미니 파이프라인 + 데이터 정리 통합 테스트."""
from __future__ import annotations

import pytest

from dev.local_db.conftest import requires_all_db, requires_mysql, requires_neo4j

pytestmark = pytest.mark.asyncio


# ===========================================================================
# TestMiniPipeline — TIER별 DB 접근 순서 시뮬레이션
# ===========================================================================


@requires_all_db
class TestMiniPipeline:
    """팟캐스트 파이프라인의 TIER별 DB 접근 순서를 시뮬레이션한다."""

    async def test_podcast_pipeline_db_flow(
        self, mysql_client, neo4j_client, pinecone_client
    ) -> None:
        """TIER 0→1→4 순서로 각 에이전트의 DB 접근 패턴을 검증한다."""
        user_id = "test-user-001"
        session_id = "sess_test000001"

        # --- TIER 1: Emotion Agent — MySQL 감정 로그 최신 1건 조회 ---
        emotion_rows = await mysql_client.fetch(
            "SELECT primary_emotion, intensity "
            "FROM emotion_logs "
            "WHERE user_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        assert len(emotion_rows) == 1, f"EmotionAgent: 감정 로그 1건 기대, {len(emotion_rows)}건"
        assert emotion_rows[0]["primary_emotion"], "EmotionAgent: primary_emotion이 비어있음"
        assert float(emotion_rows[0]["intensity"]) > 0, "EmotionAgent: intensity > 0 기대"

        # --- TIER 1: PodcastReasoning — Neo4j Session→Topic 조회 ---
        topic_results = await neo4j_client.execute_query(
            "MATCH (s:Session {session_id: $sid})-[:COVERS]->(t:Topic) "
            "RETURN t.topic_name AS topic",
            params={"sid": session_id},
        )
        assert len(topic_results) >= 1, (
            f"PodcastReasoning: Topic 1건 이상 기대, {len(topic_results)}건"
        )
        assert topic_results[0]["topic"], "PodcastReasoning: topic_name이 비어있음"

        # --- TIER 1: PodcastReasoning — Neo4j GoT 그래프 탐색 ---
        got_results = await neo4j_client.execute_query(
            "MATCH (s:Session)-[:REASONED_BY]->(root:GoTNode)"
            "-[:LEADS_TO*0..5]->(node:GoTNode) "
            "RETURN node.label AS label",
        )
        assert len(got_results) >= 1, (
            f"PodcastReasoning GoT: 1건 이상 기대, {len(got_results)}건"
        )
        assert got_results[0]["label"], "PodcastReasoning GoT: label이 비어있음"

        # --- TIER 1: Knowledge Agent — Pinecone expert_knowledge 검색 ---
        from dev.local_db.seed import _generate_deterministic_vector

        knowledge_vector = _generate_deterministic_vector(seed=42, dimension=384)
        knowledge_result = await pinecone_client.query(
            index="expert_knowledge",
            vector=knowledge_vector,
            filter={"domain": {"$in": ["psychology", "mental_health"]}},
            top_k=5,
            namespace="psychology",
        )
        knowledge_matches = knowledge_result.get("matches", [])
        assert len(knowledge_matches) >= 1, (
            f"Knowledge: 매칭 1건 이상 기대, {len(knowledge_matches)}건"
        )
        # --- TIER 1: EpisodeMemory — Pinecone mem_podcast_episode 검색 ---
        memory_vector = _generate_deterministic_vector(seed=200, dimension=384)
        memory_result = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=memory_vector,
            top_k=5,
            namespace=user_id,
        )
        memory_matches = memory_result.get("matches", [])
        assert len(memory_matches) >= 1, (
            f"EpisodeMemory: 매칭 1건 이상 기대, {len(memory_matches)}건"
        )

        # --- TIER 4: ScriptPersonalizer — MySQL 사용자 프로필 조회 ---
        profile_rows = await mysql_client.fetch(
            "SELECT preferred_style, preferred_attitude "
            "FROM users WHERE user_id = %s",
            (user_id,),
        )
        assert len(profile_rows) == 1, (
            f"ScriptPersonalizer: 사용자 프로필 1건 기대, {len(profile_rows)}건"
        )
        assert profile_rows[0]["preferred_style"], "ScriptPersonalizer: preferred_style이 비어있음"
        assert profile_rows[0]["preferred_attitude"], "ScriptPersonalizer: preferred_attitude이 비어있음"


# ===========================================================================
# TestDataCleanupMySQL — MySQL 데이터 정리 검증
# ===========================================================================


@requires_mysql
class TestDataCleanupMySQL:
    """MySQL 데이터 삽입/삭제 및 FK CASCADE 동작을 검증한다."""

    async def test_cleanup_removes_test_data(self, mysql_client) -> None:
        """INSERT → 확인 → DELETE → 0건 확인."""
        test_user_id = "test-user-cleanup-001"
        try:
            # INSERT
            await mysql_client.execute(
                "INSERT INTO users (user_id, age_group, preferred_style, preferred_attitude) "
                "VALUES (%s, %s, %s, %s)",
                (test_user_id, "20s", "casual", "balanced"),
            )

            # 존재 확인
            rows = await mysql_client.fetch(
                "SELECT user_id FROM users WHERE user_id = %s",
                (test_user_id,),
            )
            assert len(rows) == 1, f"INSERT 후 1건 기대, {len(rows)}건"

            # DELETE
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s",
                (test_user_id,),
            )

            # 삭제 확인
            rows = await mysql_client.fetch(
                "SELECT user_id FROM users WHERE user_id = %s",
                (test_user_id,),
            )
            assert len(rows) == 0, f"DELETE 후 0건 기대, {len(rows)}건"

        except Exception:
            # 정리 보장
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s",
                (test_user_id,),
            )
            raise

    async def test_fk_cascade_delete(self, mysql_client) -> None:
        """users 삭제 시 sessions FK CASCADE 동작을 검증한다."""
        test_user_id = "test-user-cleanup-002"
        test_session_id = "sess_test_cleanup_002"
        try:
            # INSERT user
            await mysql_client.execute(
                "INSERT INTO users (user_id, age_group, preferred_style, preferred_attitude) "
                "VALUES (%s, %s, %s, %s)",
                (test_user_id, "30s", "warm", "supportive"),
            )

            # INSERT session (FK → users)
            await mysql_client.execute(
                "INSERT INTO sessions (session_id, user_id, mode) "
                "VALUES (%s, %s, %s)",
                (test_session_id, test_user_id, "conversation"),
            )

            # session 존재 확인
            session_rows = await mysql_client.fetch(
                "SELECT session_id FROM sessions WHERE session_id = %s",
                (test_session_id,),
            )
            assert len(session_rows) == 1, f"session INSERT 후 1건 기대, {len(session_rows)}건"

            # DELETE user (CASCADE로 session도 삭제되어야 함)
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s",
                (test_user_id,),
            )

            # session도 삭제되었는지 확인
            session_rows = await mysql_client.fetch(
                "SELECT session_id FROM sessions WHERE session_id = %s",
                (test_session_id,),
            )
            assert len(session_rows) == 0, (
                f"FK CASCADE 후 sessions 0건 기대, {len(session_rows)}건"
            )

        except Exception:
            # 정리 보장 (역순 삭제)
            await mysql_client.execute(
                "DELETE FROM sessions WHERE session_id = %s",
                (test_session_id,),
            )
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s",
                (test_user_id,),
            )
            raise


# ===========================================================================
# TestDataCleanupNeo4j — Neo4j DETACH DELETE 검증
# ===========================================================================


@requires_neo4j
class TestDataCleanupNeo4j:
    """Neo4j DETACH DELETE로 노드 + 관계가 함께 삭제되는지 검증한다."""

    async def test_detach_delete_removes_node_and_relations(self, neo4j_client) -> None:
        """GoTNode 2개 + LEADS_TO 관계 생성 → DETACH DELETE → 0건 확인."""
        node_id_1 = "got-cleanup-001"
        node_id_2 = "got-cleanup-002"
        try:
            # CREATE 2 GoTNode + LEADS_TO 관계
            await neo4j_client.execute_query(
                "CREATE (a:GoTNode {got_node_id: $id1, node_type: 'root', label: 'cleanup root'}) "
                "CREATE (b:GoTNode {got_node_id: $id2, node_type: 'leaf', label: 'cleanup leaf'}) "
                "CREATE (a)-[:LEADS_TO {weight: 1.0}]->(b)",
                params={"id1": node_id_1, "id2": node_id_2},
            )

            # 생성 확인
            results = await neo4j_client.execute_query(
                "MATCH (n:GoTNode) WHERE n.got_node_id STARTS WITH $prefix "
                "RETURN n.got_node_id AS id",
                params={"prefix": "got-cleanup-"},
            )
            assert len(results) == 2, f"CREATE 후 2건 기대, {len(results)}건"

            # 관계 확인
            rel_results = await neo4j_client.execute_query(
                "MATCH (a:GoTNode {got_node_id: $id1})-[r:LEADS_TO]->(b:GoTNode {got_node_id: $id2}) "
                "RETURN type(r) AS rel_type",
                params={"id1": node_id_1, "id2": node_id_2},
            )
            assert len(rel_results) == 1, f"LEADS_TO 관계 1건 기대, {len(rel_results)}건"

            # DETACH DELETE by prefix
            await neo4j_client.execute_query(
                "MATCH (n:GoTNode) WHERE n.got_node_id STARTS WITH $prefix "
                "DETACH DELETE n",
                params={"prefix": "got-cleanup-"},
            )

            # 삭제 확인
            results = await neo4j_client.execute_query(
                "MATCH (n:GoTNode) WHERE n.got_node_id STARTS WITH $prefix "
                "RETURN n.got_node_id AS id",
                params={"prefix": "got-cleanup-"},
            )
            assert len(results) == 0, f"DETACH DELETE 후 0건 기대, {len(results)}건"

        except Exception:
            # 정리 보장
            await neo4j_client.execute_query(
                "MATCH (n:GoTNode) WHERE n.got_node_id STARTS WITH $prefix "
                "DETACH DELETE n",
                params={"prefix": "got-cleanup-"},
            )
            raise

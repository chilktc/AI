"""Factory 패턴 + 크로스 DB 일관성 통합 테스트."""
from __future__ import annotations

import pytest

from dev.local_db.conftest import requires_all_db

pytestmark = pytest.mark.asyncio


# ============================================================
# TestFactoryWiring — factory.py 가 올바른 타입을 반환하는지 검증
# ============================================================


class TestFactoryWiring:
    """create_rdb_client / create_graph_client 팩토리 함수 검증."""

    @requires_all_db
    async def test_factory_returns_correct_types(self) -> None:
        """팩토리가 STORAGE_MODE=local 일 때 직접 클라이언트를 반환한다."""
        from src.db.factory import create_graph_client, create_rdb_client
        from src.db.mysql_client import MySQLClient
        from src.db.neo4j_client import Neo4jClient

        rdb = create_rdb_client()
        graph = create_graph_client()
        try:
            assert isinstance(rdb, MySQLClient)
            assert isinstance(graph, Neo4jClient)
        finally:
            await rdb.close()
            await graph.close()

    @requires_all_db
    async def test_factory_clients_can_query(self) -> None:
        """팩토리에서 생성한 클라이언트로 기본 쿼리를 실행할 수 있다."""
        from src.db.factory import create_graph_client, create_rdb_client

        rdb = create_rdb_client()
        graph = create_graph_client()
        try:
            # MySQL ping
            rows = await rdb.fetch("SELECT 1 AS ping")
            assert rows[0]["ping"] == 1

            # Neo4j ping
            records = await graph.execute_query("RETURN 1 AS ping")
            assert records[0]["ping"] == 1
        finally:
            await rdb.close()
            await graph.close()


# ============================================================
# TestCrossDBConsistency — MySQL / Neo4j / Pinecone 간 데이터 일관성
# ============================================================


class TestCrossDBConsistency:
    """시드 데이터가 여러 DB에 걸쳐 일관성 있게 존재하는지 검증한다."""

    @requires_all_db
    async def test_user_ids_match(
        self, mysql_client, neo4j_client
    ) -> None:
        """MySQL과 Neo4j의 테스트 user_id 집합이 동일하다."""
        # MySQL
        mysql_rows = await mysql_client.fetch(
            "SELECT user_id FROM users WHERE user_id LIKE 'test-user-%%'"
        )
        mysql_ids = {row["user_id"] for row in mysql_rows}

        # Neo4j
        neo4j_rows = await neo4j_client.execute_query(
            "MATCH (u:User) WHERE u.user_id STARTS WITH 'test-user-' "
            "RETURN u.user_id AS uid"
        )
        neo4j_ids = {row["uid"] for row in neo4j_rows}

        assert mysql_ids == neo4j_ids

    @requires_all_db
    async def test_session_ids_match(
        self, mysql_client, neo4j_client
    ) -> None:
        """Neo4j의 테스트 session_id가 MySQL session_id의 부분집합이다."""
        # MySQL
        mysql_rows = await mysql_client.fetch(
            "SELECT session_id FROM sessions WHERE session_id LIKE 'sess_test%%'"
        )
        mysql_ids = {row["session_id"] for row in mysql_rows}

        # Neo4j
        neo4j_rows = await neo4j_client.execute_query(
            "MATCH (s:Session) WHERE s.session_id STARTS WITH 'sess_test' "
            "RETURN s.session_id AS sid"
        )
        neo4j_ids = {row["sid"] for row in neo4j_rows}

        assert neo4j_ids.issubset(mysql_ids)

    @requires_all_db
    async def test_episode_ids_in_pinecone_match_mysql(
        self, mysql_client, pinecone_client
    ) -> None:
        """Pinecone의 팟캐스트 에피소드 벡터가 MySQL에 대응 레코드를 갖는다."""
        from dev.local_db.seed import _generate_deterministic_vector

        query_vector = _generate_deterministic_vector(seed=200, dimension=384)

        result = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=query_vector,
            top_k=10,
            namespace="test-user-001",
            include_metadata=True,
        )

        matches = result.get("matches", [])
        assert len(matches) > 0, "Pinecone에서 에피소드 벡터를 찾을 수 없습니다"

        for match in matches:
            episode_id = match["metadata"]["episode_id"]
            rows = await mysql_client.fetch(
                "SELECT episode_id FROM podcast_episodes WHERE episode_id = %s",
                (episode_id,),
            )
            assert len(rows) == 1, (
                f"episode_id={episode_id}가 MySQL podcast_episodes에 존재하지 않습니다"
            )

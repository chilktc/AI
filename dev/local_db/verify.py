"""
로컬 DB 전체 검증 스크립트 (개발 전용).

연결, 스키마, CRUD, 에이전트 쿼리 패턴까지 전체 파이프라인을 검증한다.
기존 src/db/ 클라이언트를 import하여 사용하며, 기존 코드를 수정하지 않는다.

사용법:
    python -m dev.local_db.verify
    python -m dev.local_db.verify --mysql      # MySQL만
    python -m dev.local_db.verify --neo4j      # Neo4j만
    python -m dev.local_db.verify --pinecone   # Pinecone Mock만
    python -m dev.local_db.verify --factory    # Factory 검증만
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

RESULTS: list[tuple[str, bool, str]] = []  # (name, passed, detail)


def _record(name: str, passed: bool, detail: str = "") -> None:
    """테스트 결과를 기록한다."""
    status = "PASS" if passed else "FAIL"
    RESULTS.append((name, passed, detail))
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    logger.info(msg)


# ============================================================
# MySQL 검증
# ============================================================

EXPECTED_TABLES = {
    "users", "sessions", "emotion_logs", "podcast_episodes",
    "podcast_segments", "learning_patterns", "visualization_meta",
}


async def verify_mysql_connection() -> bool:
    """MySQL 연결을 검증한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    try:
        rows = await client.fetch("SELECT 1 AS ping")
        ok = len(rows) == 1 and rows[0].get("ping") == 1
        _record("MySQL 연결", ok)
        return ok
    except Exception as e:
        _record("MySQL 연결", False, str(e))
        return False
    finally:
        await client.close()


async def verify_mysql_schema() -> bool:
    """MySQL 스키마 (7개 테이블)를 검증한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    try:
        rows = await client.fetch("SHOW TABLES")
        table_names = {list(r.values())[0] for r in rows}
        missing = EXPECTED_TABLES - table_names
        ok = len(missing) == 0
        detail = f"{len(table_names)}개 테이블" if ok else f"누락: {missing}"
        _record("MySQL 스키마 (7 테이블)", ok, detail)
        return ok
    except Exception as e:
        _record("MySQL 스키마 (7 테이블)", False, str(e))
        return False
    finally:
        await client.close()


async def verify_mysql_crud() -> bool:
    """MySQL CRUD 동작을 검증한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    test_uid = "verify-test-user"
    test_sid = "sess_verify00001"
    try:
        # INSERT user
        await client.execute(
            "INSERT IGNORE INTO users (user_id, display_name) VALUES (%s, %s)",
            (test_uid, "검증유저"),
        )
        # INSERT session
        await client.execute(
            "INSERT IGNORE INTO sessions (session_id, user_id, mode) VALUES (%s, %s, %s)",
            (test_sid, test_uid, "podcast"),
        )
        # SELECT
        rows = await client.fetch(
            "SELECT * FROM users WHERE user_id = %s", (test_uid,)
        )
        found = len(rows) == 1 and rows[0]["user_id"] == test_uid

        # UPDATE
        await client.execute(
            "UPDATE users SET display_name = %s WHERE user_id = %s",
            ("업데이트됨", test_uid),
        )
        rows = await client.fetch(
            "SELECT display_name FROM users WHERE user_id = %s", (test_uid,)
        )
        updated = len(rows) == 1 and rows[0]["display_name"] == "업데이트됨"

        # DELETE (cascade)
        await client.execute("DELETE FROM users WHERE user_id = %s", (test_uid,))
        rows = await client.fetch(
            "SELECT * FROM sessions WHERE session_id = %s", (test_sid,)
        )
        cascaded = len(rows) == 0  # FK cascade로 sessions도 삭제

        ok = found and updated and cascaded
        detail = f"INSERT={'OK' if found else 'FAIL'}, UPDATE={'OK' if updated else 'FAIL'}, CASCADE={'OK' if cascaded else 'FAIL'}"
        _record("MySQL CRUD", ok, detail)
        return ok
    except Exception as e:
        _record("MySQL CRUD", False, str(e))
        # 정리 시도
        try:
            await client.execute("DELETE FROM sessions WHERE session_id = %s", (test_sid,))
            await client.execute("DELETE FROM users WHERE user_id = %s", (test_uid,))
        except Exception:
            pass
        return False
    finally:
        await client.close()


async def verify_mysql_agent_queries() -> bool:
    """에이전트가 사용하는 MySQL 쿼리 패턴을 검증한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    try:
        results: list[bool] = []

        # ScriptPersonalizer 패턴: users 테이블에서 프로필 조회
        rows = await client.fetch(
            "SELECT user_id, age_group, preferred_style, preferred_attitude, accessibility_needs "
            "FROM users WHERE user_id = %s",
            ("test-user-001",),
        )
        results.append(len(rows) >= 0)  # 데이터 유무와 무관하게 쿼리 성공

        # LearningAgent 패턴: learning_patterns 조회
        rows = await client.fetch(
            "SELECT * FROM learning_patterns WHERE user_id = %s ORDER BY created_at DESC",
            ("test-user-001",),
        )
        results.append(len(rows) >= 0)

        # 에피소드 조회 패턴
        rows = await client.fetch(
            "SELECT episode_id, episode_title, themes, key_insights "
            "FROM podcast_episodes WHERE user_id = %s ORDER BY created_at DESC",
            ("test-user-001",),
        )
        results.append(len(rows) >= 0)

        # 세그먼트 JOIN 패턴
        rows = await client.fetch(
            "SELECT s.segment_id, s.segment_type, s.script_text "
            "FROM podcast_segments s "
            "JOIN podcast_episodes e ON s.episode_id = e.episode_id "
            "WHERE e.user_id = %s ORDER BY s.segment_order",
            ("test-user-001",),
        )
        results.append(len(rows) >= 0)

        ok = all(results)
        _record("MySQL 에이전트 쿼리", ok, f"{sum(results)}/{len(results)} 쿼리 성공")
        return ok
    except Exception as e:
        _record("MySQL 에이전트 쿼리", False, str(e))
        return False
    finally:
        await client.close()


# ============================================================
# Neo4j 검증
# ============================================================

async def verify_neo4j_connection() -> bool:
    """Neo4j 연결을 검증한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    try:
        result = await client.execute_query("RETURN 1 AS ping")
        ok = len(result) == 1 and result[0].get("ping") == 1
        _record("Neo4j 연결", ok)
        return ok
    except Exception as e:
        _record("Neo4j 연결", False, str(e))
        return False
    finally:
        await client.close()


async def verify_neo4j_schema() -> bool:
    """Neo4j 제약조건/인덱스를 검증한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    try:
        # 제약조건 실행 (멱등)
        cypher_path = Path(__file__).parent / "neo4j" / "init.cypher"
        if cypher_path.exists():
            cypher_text = cypher_path.read_text(encoding="utf-8")
            for statement in cypher_text.split(";"):
                statement = statement.strip()
                lines = [
                    line for line in statement.split("\n")
                    if line.strip() and not line.strip().startswith("//")
                ]
                statement = "\n".join(lines).strip()
                if statement:
                    await client.execute_query(statement)

        # 제약조건 확인
        constraints = await client.execute_query("SHOW CONSTRAINTS")
        constraint_count = len(constraints)
        ok = constraint_count >= 5
        _record("Neo4j 스키마 (5 제약조건)", ok, f"{constraint_count}개 제약조건")
        return ok
    except Exception as e:
        _record("Neo4j 스키마 (5 제약조건)", False, str(e))
        return False
    finally:
        await client.close()


async def verify_neo4j_crud_and_queries() -> bool:
    """Neo4j CRUD 및 에이전트 쿼리 패턴을 검증한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    test_prefix = "verify_"
    try:
        results: list[bool] = []

        # CREATE 노드
        await client.execute_query(
            "MERGE (u:User {user_id: $uid}) SET u.display_name = $name",
            {"uid": f"{test_prefix}user", "name": "검증유저"},
        )
        await client.execute_query(
            "MERGE (t:Topic {topic_name: $name}) SET t.domain = $domain",
            {"name": f"{test_prefix}topic", "domain": "test"},
        )
        await client.execute_query(
            "MERGE (e:Emotion {emotion_key: $key}) SET e.emotion_kr = $kr, e.category = $cat",
            {"key": f"{test_prefix}emotion", "kr": "테스트감정", "cat": "neutral"},
        )
        results.append(True)

        # CREATE 관계
        await client.execute_query(
            "MATCH (u:User {user_id: $uid}) "
            "MERGE (s:Session {session_id: $sid}) SET s.mode = 'podcast' "
            "MERGE (u)-[:HAS_SESSION]->(s)",
            {"uid": f"{test_prefix}user", "sid": f"{test_prefix}session"},
        )
        results.append(True)

        # PodcastReasoning 패턴: Topic 조회
        topic_result = await client.execute_query(
            "MATCH (n:Topic) WHERE n.topic_name = $name RETURN n",
            {"name": f"{test_prefix}topic"},
        )
        results.append(len(topic_result) == 1)

        # GoTNode + LEADS_TO 패턴
        await client.execute_query(
            "MERGE (g1:GoTNode {got_node_id: $id1}) SET g1.label = $l1, g1.node_type = 'root' "
            "MERGE (g2:GoTNode {got_node_id: $id2}) SET g2.label = $l2, g2.node_type = 'branch' "
            "MERGE (g1)-[:LEADS_TO {weight: 0.9, relation_type: 'test'}]->(g2)",
            {
                "id1": f"{test_prefix}got1", "l1": "루트노드",
                "id2": f"{test_prefix}got2", "l2": "분기노드",
            },
        )
        got_result = await client.execute_query(
            "MATCH (g1:GoTNode)-[r:LEADS_TO]->(g2:GoTNode) "
            "WHERE g1.got_node_id = $id RETURN g1, r, g2",
            {"id": f"{test_prefix}got1"},
        )
        results.append(len(got_result) == 1)

        # 관계 탐색 패턴
        rel_result = await client.execute_query(
            "MATCH (u:User {user_id: $uid})-[:HAS_SESSION]->(s:Session) RETURN s",
            {"uid": f"{test_prefix}user"},
        )
        results.append(len(rel_result) >= 1)

        ok = all(results)
        _record("Neo4j CRUD + 에이전트 쿼리", ok, f"{sum(results)}/{len(results)} 검증 성공")

        # 정리
        await client.execute_query(
            "MATCH (n) WHERE n.user_id STARTS WITH $prefix "
            "OR n.session_id STARTS WITH $prefix "
            "OR n.topic_name STARTS WITH $prefix "
            "OR n.emotion_key STARTS WITH $prefix "
            "OR n.got_node_id STARTS WITH $prefix "
            "DETACH DELETE n",
            {"prefix": test_prefix},
        )

        return ok
    except Exception as e:
        _record("Neo4j CRUD + 에이전트 쿼리", False, str(e))
        # 정리 시도
        try:
            await client.execute_query(
                "MATCH (n) WHERE n.user_id STARTS WITH $prefix "
                "OR n.session_id STARTS WITH $prefix "
                "OR n.topic_name STARTS WITH $prefix "
                "OR n.emotion_key STARTS WITH $prefix "
                "OR n.got_node_id STARTS WITH $prefix "
                "DETACH DELETE n",
                {"prefix": test_prefix},
            )
        except Exception:
            pass
        return False
    finally:
        await client.close()


# ============================================================
# Pinecone Mock 검증
# ============================================================

async def verify_pinecone_mock() -> bool:
    """Pinecone Mock 클라이언트를 검증한다."""
    from dev.local_db.pinecone_mock import PineconeMockClient
    from dev.local_db.seed import _generate_deterministic_vector

    client = PineconeMockClient()
    try:
        results: list[bool] = []

        # Upsert
        vectors = [
            {
                "id": f"vec_verify_{i}",
                "values": _generate_deterministic_vector(i * 100, 384),
                "metadata": {"domain": "psychology" if i < 3 else "mental_health"},
            }
            for i in range(5)
        ]
        upsert_result = await client.upsert("expert_knowledge", vectors, namespace="test")
        results.append(upsert_result.get("upserted_count") == 5)

        # KnowledgeAgent 패턴: 벡터 검색 + 필터
        query_vector = _generate_deterministic_vector(0, 384)  # vec_verify_0과 유사
        search_result = await client.query(
            index="expert_knowledge",
            vector=query_vector,
            filter={"domain": {"$in": ["psychology"]}},
            top_k=3,
            namespace="test",
            include_metadata=True,
        )
        matches = search_result.get("matches", [])
        results.append(len(matches) > 0)
        # 첫 번째 결과가 가장 유사해야 함
        if matches:
            results.append(matches[0]["id"] == "vec_verify_0")
            results.append("metadata" in matches[0])

        # EpisodeMemory 패턴: namespace별 검색
        ep_vectors = [
            {
                "id": "vec_ep_001",
                "values": _generate_deterministic_vector(200, 384),
                "metadata": {"episode_id": "ep-001", "title": "테스트 에피소드"},
            }
        ]
        await client.upsert("mem_podcast_episode", ep_vectors, namespace="user-001")
        ep_result = await client.query(
            index="mem_podcast_episode",
            vector=_generate_deterministic_vector(200, 384),
            filter={},
            top_k=5,
            namespace="user-001",
        )
        results.append(len(ep_result.get("matches", [])) == 1)

        ok = all(results)
        _record("Pinecone Mock 검증", ok, f"{sum(results)}/{len(results)} 검증 성공")
        return ok
    except Exception as e:
        _record("Pinecone Mock 검증", False, str(e))
        return False
    finally:
        await client.close()


# ============================================================
# Factory 검증
# ============================================================

async def verify_factory() -> bool:
    """Factory 패턴이 올바른 클라이언트를 반환하는지 검증한다."""
    try:
        # STORAGE_MODE=local 확인
        storage_mode = os.getenv("STORAGE_MODE", "local")
        if storage_mode != "local":
            _record("Factory 검증", False, f"STORAGE_MODE={storage_mode} (local 필요)")
            return False

        from src.db.factory import create_graph_client, create_rdb_client
        from src.db.mysql_client import MySQLClient
        from src.db.neo4j_client import Neo4jClient

        rdb = create_rdb_client()
        graph = create_graph_client()

        rdb_ok = isinstance(rdb, MySQLClient)
        graph_ok = isinstance(graph, Neo4jClient)

        await rdb.close()
        await graph.close()

        ok = rdb_ok and graph_ok
        _record(
            "Factory 검증",
            ok,
            f"RDB={'MySQLClient' if rdb_ok else type(rdb).__name__}, "
            f"Graph={'Neo4jClient' if graph_ok else type(graph).__name__}",
        )
        return ok
    except Exception as e:
        _record("Factory 검증", False, str(e))
        return False


# ============================================================
# 메인
# ============================================================

async def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 DB 전체 검증")
    parser.add_argument("--mysql", action="store_true", help="MySQL만 검증")
    parser.add_argument("--neo4j", action="store_true", help="Neo4j만 검증")
    parser.add_argument("--pinecone", action="store_true", help="Pinecone Mock만 검증")
    parser.add_argument("--factory", action="store_true", help="Factory만 검증")
    args = parser.parse_args()

    run_all = not (args.mysql or args.neo4j or args.pinecone or args.factory)

    logger.info("========== 로컬 DB 검증 ==========")
    logger.info("")

    step = 0

    if run_all or args.mysql:
        step += 1
        logger.info(f"[{step}] MySQL 연결 검증...")
        if await verify_mysql_connection():
            step += 1
            logger.info(f"[{step}] MySQL 스키마 검증...")
            await verify_mysql_schema()

            step += 1
            logger.info(f"[{step}] MySQL CRUD 검증...")
            await verify_mysql_crud()

            step += 1
            logger.info(f"[{step}] MySQL 에이전트 쿼리 검증...")
            await verify_mysql_agent_queries()
        else:
            logger.info("  → MySQL 연결 실패로 나머지 검증 건너뜀")

    if run_all or args.neo4j:
        step += 1
        logger.info(f"[{step}] Neo4j 연결 검증...")
        if await verify_neo4j_connection():
            step += 1
            logger.info(f"[{step}] Neo4j 스키마 검증...")
            await verify_neo4j_schema()

            step += 1
            logger.info(f"[{step}] Neo4j CRUD + 에이전트 쿼리 검증...")
            await verify_neo4j_crud_and_queries()
        else:
            logger.info("  → Neo4j 연결 실패로 나머지 검증 건너뜀")

    if run_all or args.pinecone:
        step += 1
        logger.info(f"[{step}] Pinecone Mock 검증...")
        await verify_pinecone_mock()

    if run_all or args.factory:
        step += 1
        logger.info(f"[{step}] Factory 검증...")
        await verify_factory()

    # 결과 요약
    logger.info("")
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = total - passed

    logger.info(f"========== {passed}/{total} PASS ==========")
    if failed > 0:
        logger.info("")
        logger.info("실패 항목:")
        for name, ok, detail in RESULTS:
            if not ok:
                logger.info(f"  [FAIL] {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

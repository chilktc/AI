"""
JSON 픽스처 → DB 시드 데이터 로드 스크립트 (개발 전용).

기존 src/db/ 클라이언트를 읽기 전용으로 import하여 사용한다.
Pinecone은 dev/local_db/pinecone_mock.py를 직접 사용한다.

사용법:
    python -m dev.local_db.seed              # 전체 시드
    python -m dev.local_db.seed --mysql      # MySQL만
    python -m dev.local_db.seed --neo4j      # Neo4j만
    python -m dev.local_db.seed --pinecone   # Pinecone Mock만
    python -m dev.local_db.seed --clean      # 시드 데이터 삭제
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "seed_data.json"

# 시드 데이터에서 생성된 test ID prefix (정리용)
TEST_USER_PREFIX = "test-user-"
TEST_SESSION_PREFIX = "sess_test"


def _load_fixtures() -> dict[str, Any]:
    """JSON 픽스처 파일을 로드한다."""
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _generate_deterministic_vector(seed: int, dimension: int) -> list[float]:
    """시드 기반 결정론적 벡터를 생성한다 (재현 가능)."""
    import struct

    values: list[float] = []
    for i in range(dimension):
        h = hashlib.md5(f"{seed}_{i}".encode()).digest()
        val = struct.unpack("f", h[:4])[0]
        # -1 ~ 1 범위로 정규화
        val = (val % 2.0) - 1.0
        values.append(round(val, 6))
    return values


# ============================================================
# MySQL 시드
# ============================================================

async def seed_mysql(data: dict[str, Any]) -> None:
    """MySQL에 시드 데이터를 삽입한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    try:
        mysql_data = data["mysql"]

        # 삽입 순서: FK 의존성 순서
        table_order = [
            "users", "sessions", "emotion_logs",
            "podcast_episodes", "podcast_segments",
            "learning_patterns", "visualization_meta",
        ]

        for table_name in table_order:
            rows = mysql_data.get(table_name, [])
            if not rows:
                continue

            for row in rows:
                # JSON 필드를 문자열로 변환
                processed = {}
                for key, value in row.items():
                    if isinstance(value, (list, dict)):
                        processed[key] = json.dumps(value, ensure_ascii=False)
                    elif isinstance(value, bool):
                        processed[key] = int(value)
                    else:
                        processed[key] = value

                columns = ", ".join(processed.keys())
                placeholders = ", ".join(["%s"] * len(processed))
                query = f"INSERT IGNORE INTO {table_name} ({columns}) VALUES ({placeholders})"
                await client.execute(query, tuple(processed.values()))

            logger.info(f"  MySQL: {table_name} — {len(rows)}건 삽입")

    finally:
        await client.close()


async def clean_mysql() -> None:
    """MySQL에서 테스트 시드 데이터를 삭제한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    try:
        # 역순 삭제 (FK 의존성)
        tables_reverse = [
            "visualization_meta", "learning_patterns", "podcast_segments",
            "podcast_episodes", "emotion_logs", "sessions", "users",
        ]
        for table in tables_reverse:
            if table == "users":
                await client.execute(
                    f"DELETE FROM {table} WHERE user_id LIKE %s",
                    (f"{TEST_USER_PREFIX}%",),
                )
            elif table == "sessions":
                await client.execute(
                    f"DELETE FROM {table} WHERE session_id LIKE %s",
                    (f"{TEST_SESSION_PREFIX}%",),
                )
            else:
                # FK cascade가 처리하므로 users/sessions 삭제 시 자동 삭제
                # 명시적으로도 삭제 (cascade 미동작 시 대비)
                await client.execute(
                    f"DELETE FROM {table} WHERE user_id LIKE %s",
                    (f"{TEST_USER_PREFIX}%",),
                )
            logger.info(f"  MySQL: {table} 테스트 데이터 삭제")
    finally:
        await client.close()


# ============================================================
# Neo4j 시드
# ============================================================

async def seed_neo4j(data: dict[str, Any]) -> None:
    """Neo4j에 시드 데이터를 삽입한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    try:
        neo4j_data = data["neo4j"]

        # 제약조건/인덱스 먼저 실행 (이미 존재하면 무시)
        cypher_path = Path(__file__).parent / "neo4j" / "init.cypher"
        if cypher_path.exists():
            cypher_text = cypher_path.read_text(encoding="utf-8")
            for statement in cypher_text.split(";"):
                statement = statement.strip()
                # 주석 라인 제거
                lines = [
                    line for line in statement.split("\n")
                    if line.strip() and not line.strip().startswith("//")
                ]
                statement = "\n".join(lines).strip()
                if statement:
                    try:
                        await client.execute_query(statement)
                    except Exception as e:
                        logger.warning(f"  Neo4j: 제약조건/인덱스 스킵 — {e}")
            logger.info("  Neo4j: 제약조건/인덱스 적용 완료")

        # 노드 생성
        for label, nodes in neo4j_data.get("nodes", {}).items():
            for node in nodes:
                props_str = ", ".join(f"n.{k} = ${k}" for k in node.keys())
                # 고유 키 결정
                if label == "User":
                    match_key = "user_id"
                elif label == "Session":
                    match_key = "session_id"
                elif label == "Emotion":
                    match_key = "emotion_key"
                elif label == "Topic":
                    match_key = "topic_name"
                elif label == "GoTNode":
                    match_key = "got_node_id"
                else:
                    match_key = list(node.keys())[0]

                query = (
                    f"MERGE (n:{label} {{{match_key}: ${match_key}}}) "
                    f"SET {props_str}"
                )
                await client.execute_query(query, node)
            logger.info(f"  Neo4j: :{label} — {len(nodes)}개 노드 생성")

        # 관계 생성
        rels = neo4j_data.get("relationships", [])
        for rel in rels:
            rel_type = rel["type"]
            from_info = rel["from"]
            to_info = rel["to"]
            props = rel.get("props", {})

            props_clause = ""
            if props:
                props_parts = [f"{k}: $prop_{k}" for k in props.keys()]
                props_clause = " {" + ", ".join(props_parts) + "}"

            query = (
                f"MATCH (a:{from_info['label']} {{{from_info['match_key']}: $from_val}}) "
                f"MATCH (b:{to_info['label']} {{{to_info['match_key']}: $to_val}}) "
                f"MERGE (a)-[r:{rel_type}{props_clause}]->(b)"
            )
            params: dict[str, Any] = {
                "from_val": from_info["match_value"],
                "to_val": to_info["match_value"],
            }
            for k, v in props.items():
                params[f"prop_{k}"] = v

            await client.execute_query(query, params)

        logger.info(f"  Neo4j: {len(rels)}개 관계 생성")

    finally:
        await client.close()


async def clean_neo4j() -> None:
    """Neo4j에서 테스트 시드 데이터를 삭제한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    try:
        # 테스트 데이터만 삭제 (test- prefix)
        await client.execute_query(
            "MATCH (n) WHERE n.user_id STARTS WITH $prefix "
            "OR n.session_id STARTS WITH $sess_prefix "
            "OR n.got_node_id STARTS WITH $got_prefix "
            "DETACH DELETE n",
            {
                "prefix": TEST_USER_PREFIX,
                "sess_prefix": TEST_SESSION_PREFIX,
                "got_prefix": "got-test-",
            },
        )
        # Emotion/Topic 테스트 노드도 삭제
        await client.execute_query(
            "MATCH (n) WHERE n.mysql_id STARTS WITH 'emotion_' "
            "OR n.mysql_id STARTS WITH 'topic_' "
            "DETACH DELETE n"
        )
        logger.info("  Neo4j: 테스트 데이터 삭제 완료")
    finally:
        await client.close()


# ============================================================
# Pinecone Mock 시드
# ============================================================

async def seed_pinecone(data: dict[str, Any]) -> PineconeMockClient | None:
    """Pinecone Mock에 시드 데이터를 삽입한다."""
    from dev.local_db.pinecone_mock import PineconeMockClient

    client = PineconeMockClient()
    pinecone_data = data["pinecone"]

    for index_name, index_data in pinecone_data.items():
        namespace = index_data.get("namespace", "")
        vectors = []
        for vec in index_data.get("vectors", []):
            values = _generate_deterministic_vector(
                vec["values_seed"], vec["dimension"]
            )
            vectors.append({
                "id": vec["id"],
                "values": values,
                "metadata": vec["metadata"],
            })

        if vectors:
            await client.upsert(index_name, vectors, namespace=namespace)
            logger.info(f"  Pinecone Mock: {index_name}/{namespace} — {len(vectors)}개 벡터")

    return client


# ============================================================
# 메인
# ============================================================

# PineconeMockClient 타입을 위한 forward reference
try:
    from dev.local_db.pinecone_mock import PineconeMockClient
except ImportError:
    PineconeMockClient = None  # type: ignore[assignment, misc]


async def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 DB 시드 데이터 관리")
    parser.add_argument("--mysql", action="store_true", help="MySQL만 시드")
    parser.add_argument("--neo4j", action="store_true", help="Neo4j만 시드")
    parser.add_argument("--pinecone", action="store_true", help="Pinecone Mock만 시드")
    parser.add_argument("--clean", action="store_true", help="시드 데이터 삭제")
    args = parser.parse_args()

    # 아무 옵션도 없으면 전체 실행
    run_all = not (args.mysql or args.neo4j or args.pinecone)

    if args.clean:
        logger.info("========== 시드 데이터 삭제 ==========")
        if run_all or args.mysql:
            try:
                await clean_mysql()
            except Exception as e:
                logger.error(f"  MySQL 삭제 실패: {e}")
        if run_all or args.neo4j:
            try:
                await clean_neo4j()
            except Exception as e:
                logger.error(f"  Neo4j 삭제 실패: {e}")
        logger.info("========== 삭제 완료 ==========")
        return

    data = _load_fixtures()
    logger.info("========== 시드 데이터 로드 ==========")

    if run_all or args.mysql:
        try:
            await seed_mysql(data)
        except Exception as e:
            logger.error(f"  MySQL 시드 실패: {e}")

    if run_all or args.neo4j:
        try:
            await seed_neo4j(data)
        except Exception as e:
            logger.error(f"  Neo4j 시드 실패: {e}")

    if run_all or args.pinecone:
        try:
            await seed_pinecone(data)
            logger.info("  (Pinecone Mock: 인메모리 — verify.py에서 검증)")
        except Exception as e:
            logger.error(f"  Pinecone Mock 시드 실패: {e}")

    logger.info("========== 시드 완료 ==========")


if __name__ == "__main__":
    asyncio.run(main())

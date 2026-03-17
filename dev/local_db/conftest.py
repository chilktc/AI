"""
로컬 DB 통합 테스트용 pytest conftest.

Docker Compose로 기동한 MySQL/Neo4j에 대한 연결 프로브,
skip 마커, 클라이언트 fixture를 제공한다.
Pinecone은 인메모리 Mock을 사용한다.

사용법:
    pytest dev/local_db/ -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# 1. 프로젝트 루트를 sys.path에 추가 (src/db/ import 지원)
# ---------------------------------------------------------------------------
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# 2. .env.db 자동 로드 (기존 환경변수는 덮어쓰지 않음)
# ---------------------------------------------------------------------------
_env_db_path = Path(__file__).parent / ".env.db"
if _env_db_path.exists():
    with open(_env_db_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#"):
                continue
            if "=" not in _line:
                continue
            _key, _, _value = _line.partition("=")
            os.environ.setdefault(_key.strip(), _value.strip())

# ---------------------------------------------------------------------------
# 3. DB 연결 프로브 (세션 시작 시 1회만 실행, 모듈 레벨 캐시)
# ---------------------------------------------------------------------------

_mysql_available: bool | None = None
_neo4j_available: bool | None = None


def _probe_mysql() -> bool:
    """PyMySQL로 MySQL 연결을 시도한다."""
    global _mysql_available
    if _mysql_available is not None:
        return _mysql_available

    try:
        import pymysql
        from src.db.mysql_client import _parse_mysql_url

        url = os.getenv(
            "MYSQL_URL", "mysql+pymysql://root:@localhost:3306/mindlog"
        )
        params = _parse_mysql_url(url)
        params["connect_timeout"] = 3
        conn = pymysql.connect(**params)
        conn.close()
        _mysql_available = True
    except Exception:
        _mysql_available = False

    return _mysql_available


def _probe_neo4j() -> bool:
    """Neo4j 동기 드라이버로 연결을 시도한다."""
    global _neo4j_available
    if _neo4j_available is not None:
        return _neo4j_available

    try:
        from neo4j import GraphDatabase

        url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")
        driver = GraphDatabase.driver(url, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        _neo4j_available = True
    except Exception:
        _neo4j_available = False

    return _neo4j_available


# ---------------------------------------------------------------------------
# 4. Skip 마커
# ---------------------------------------------------------------------------

requires_mysql = pytest.mark.skipif(
    not _probe_mysql(),
    reason="MySQL이 실행 중이지 않습니다 (docker compose up -d 필요)",
)

requires_neo4j = pytest.mark.skipif(
    not _probe_neo4j(),
    reason="Neo4j가 실행 중이지 않습니다 (docker compose up -d 필요)",
)

requires_all_db = pytest.mark.skipif(
    not (_probe_mysql() and _probe_neo4j()),
    reason="MySQL 및 Neo4j가 모두 실행 중이어야 합니다",
)

# ---------------------------------------------------------------------------
# 5. 클라이언트 Fixture (pytest-asyncio)
# ---------------------------------------------------------------------------

import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def mysql_client():
    """MySQLClient 인스턴스를 생성하고 테스트 후 정리한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def neo4j_client():
    """Neo4jClient 인스턴스를 생성하고 테스트 후 정리한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def pinecone_client():
    """PineconeMockClient 인스턴스를 생성하고 시드 데이터를 로드한다."""
    from dev.local_db.pinecone_mock import PineconeMockClient
    from dev.local_db.seed import _generate_deterministic_vector, _load_fixtures

    client = PineconeMockClient()

    # 시드 데이터 로드
    data = _load_fixtures()
    pinecone_data = data.get("pinecone", {})
    for index_name, index_data in pinecone_data.items():
        namespace = index_data.get("namespace", "")
        vectors: list[dict[str, Any]] = []
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

    yield client
    await client.close()


# ---------------------------------------------------------------------------
# 6. 시드 데이터 Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_data() -> dict[str, Any]:
    """JSON 시드 데이터를 dict로 반환한다."""
    from dev.local_db.seed import _load_fixtures

    return _load_fixtures()

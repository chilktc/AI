# 로컬 DB 통합 테스트 구현 계획서

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `dev/local_db/` 환경의 실제 DB(MySQL, Neo4j, Pinecone Mock)를 대상으로 pytest 기반 통합 테스트를 작성하여, 에이전트가 사용하는 쿼리 패턴이 실제 DB에서 올바르게 동작하는지 검증한다.

**Architecture:** `dev/local_db/conftest.py`에서 DB 연결 프로브 + 클라이언트 fixture를 제공하고, `dev/local_db/test_db_integration.py`에서 7개 테스트 클래스(~25개 테스트 메서드)를 실행한다. Docker 미실행 시 자동 skip되며, 기존 `src/` 코드를 일절 수정하지 않는다.

**Tech Stack:** pytest, pytest-asyncio, MySQLClient(`src/db/mysql_client.py`), Neo4jClient(`src/db/neo4j_client.py`), PineconeMockClient(`dev/local_db/pinecone_mock.py`)

---

## 전제 조건

- Docker Compose DB가 실행 중이어야 한다: `docker compose -f dev/local_db/docker-compose.db.yml up -d`
- 시드 데이터가 로드되어 있어야 한다: `python3 -m dev.local_db.seed`
- 환경변수가 로드되어 있어야 한다: `export $(cat dev/local_db/.env.db | xargs)`
- Docker 미실행 시 모든 테스트가 `pytest.skip()`으로 건너뜀

## 파일 구조

```
dev/local_db/
├── conftest.py                    ← 신규: DB fixture + skip 마커
├── test_db_integration.py         ← 신규: 7개 테스트 클래스
├── (기존 파일들 무수정)
```

## 실행 명령어

```bash
# 전체 실행
pytest dev/local_db/test_db_integration.py -v

# 특정 클래스만
pytest dev/local_db/test_db_integration.py::TestMySQLAgentQueries -v

# 특정 테스트만
pytest dev/local_db/test_db_integration.py::TestNeo4jAgentQueries::test_got_traversal -v
```

---

### Task 1: conftest.py — DB 연결 프로브 및 클라이언트 Fixture

**Files:**
- Create: `dev/local_db/conftest.py`

**Step 1: conftest.py 작성**

```python
"""
로컬 DB 통합 테스트 conftest.

Docker DB 실행 여부를 프로브하여 미실행 시 자동 skip한다.
기존 src/db/ 클라이언트를 그대로 사용하며 코드를 수정하지 않는다.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env.db 환경변수 로드 (이미 export되지 않은 경우 대비)
_env_db_path = Path(__file__).parent / ".env.db"
if _env_db_path.exists():
    for line in _env_db_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ===================================================================
# DB 연결 프로브 (session scope)
# ===================================================================
def _probe_mysql() -> bool:
    """MySQL 접속 가능 여부를 확인한다."""
    try:
        import pymysql
        from src.db.mysql_client import _parse_mysql_url

        url = os.getenv("MYSQL_URL", "mysql+pymysql://root:@localhost:3306/mindlog")
        params = _parse_mysql_url(url)
        conn = pymysql.connect(**params, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _probe_neo4j() -> bool:
    """Neo4j 접속 가능 여부를 확인한다."""
    try:
        from neo4j import GraphDatabase

        url = os.getenv("NEO4J_URL", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")
        driver = GraphDatabase.driver(url, auth=(user, password))
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


# 세션 시작 시 1회만 프로브
_mysql_available: bool | None = None
_neo4j_available: bool | None = None


def _is_mysql_available() -> bool:
    global _mysql_available
    if _mysql_available is None:
        _mysql_available = _probe_mysql()
    return _mysql_available


def _is_neo4j_available() -> bool:
    global _neo4j_available
    if _neo4j_available is None:
        _neo4j_available = _probe_neo4j()
    return _neo4j_available


# ===================================================================
# Skip 마커
# ===================================================================
requires_mysql = pytest.mark.skipif(
    not _is_mysql_available(),
    reason="MySQL 미실행 (docker compose -f dev/local_db/docker-compose.db.yml up -d)",
)

requires_neo4j = pytest.mark.skipif(
    not _is_neo4j_available(),
    reason="Neo4j 미실행 (docker compose -f dev/local_db/docker-compose.db.yml up -d)",
)

requires_all_db = pytest.mark.skipif(
    not (_is_mysql_available() and _is_neo4j_available()),
    reason="MySQL 또는 Neo4j 미실행",
)


# ===================================================================
# 클라이언트 Fixture
# ===================================================================
@pytest_asyncio.fixture
async def mysql_client():
    """MySQLClient 인스턴스를 제공하고, 테스트 후 정리한다."""
    from src.db.mysql_client import MySQLClient

    client = MySQLClient()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def neo4j_client():
    """Neo4jClient 인스턴스를 제공하고, 테스트 후 정리한다."""
    from src.db.neo4j_client import Neo4jClient

    client = Neo4jClient()
    yield client
    await client.close()


@pytest_asyncio.fixture
async def pinecone_client():
    """PineconeMockClient 인스턴스를 제공한다 (시드 데이터 포함)."""
    from dev.local_db.pinecone_mock import PineconeMockClient
    from dev.local_db.seed import _generate_deterministic_vector, _load_fixtures

    client = PineconeMockClient()
    data = _load_fixtures()

    # 시드 데이터 로드
    for index_name, index_data in data["pinecone"].items():
        namespace = index_data.get("namespace", "")
        vectors = []
        for vec in index_data.get("vectors", []):
            values = _generate_deterministic_vector(vec["values_seed"], vec["dimension"])
            vectors.append({
                "id": vec["id"],
                "values": values,
                "metadata": vec["metadata"],
            })
        if vectors:
            await client.upsert(index_name, vectors, namespace=namespace)

    yield client
    await client.close()


# ===================================================================
# 시드 데이터 참조 Fixture
# ===================================================================
@pytest.fixture
def seed_data() -> dict:
    """seed_data.json을 dict로 반환한다."""
    from dev.local_db.seed import _load_fixtures

    return _load_fixtures()
```

**Step 2: 테스트 실행으로 conftest 로드 확인**

Run: `pytest dev/local_db/ --collect-only 2>&1 | head -20`
Expected: conftest가 정상 로드됨 (ImportError 없음)

**Step 3: 커밋**

```bash
git add dev/local_db/conftest.py
git commit -m "test: dev/local_db conftest — DB 프로브 + 클라이언트 fixture"
```

---

### Task 2: TestMySQLAgentQueries — MySQL 에이전트 쿼리 패턴 검증

**Files:**
- Create: `dev/local_db/test_db_integration.py`

**Step 1: MySQL 테스트 클래스 작성**

```python
"""
로컬 DB 통합 테스트.

Docker DB + 시드 데이터가 필요하며, 미실행 시 자동 skip된다.
기존 src/ 코드를 수정하지 않고, 에이전트가 사용하는 쿼리 패턴을 실제 DB에서 검증한다.

실행:
    pytest dev/local_db/test_db_integration.py -v
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from dev.local_db.conftest import requires_all_db, requires_mysql, requires_neo4j

pytestmark = pytest.mark.asyncio


# ===================================================================
# 1. MySQL 에이전트 쿼리 패턴
# ===================================================================
@requires_mysql
class TestMySQLAgentQueries:
    """에이전트가 사용하는 MySQL 쿼리 패턴을 실제 DB에서 검증한다."""

    async def test_user_profile_lookup(self, mysql_client, seed_data):
        """ScriptPersonalizer 패턴: users 테이블에서 프로필 조회.

        참조: src/agents/podcast/script_personalizer.py
        """
        rows = await mysql_client.fetch(
            "SELECT user_id, age_group, preferred_style, preferred_attitude, "
            "accessibility_needs FROM users WHERE user_id = %s",
            ("test-user-001",),
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == "test-user-001"
        assert row["age_group"] == "30s"
        assert row["preferred_style"] == "warm"
        assert row["preferred_attitude"] == "supportive"

    async def test_learning_pattern_insert_and_query(self, mysql_client):
        """LearningAgent 패턴: learning_patterns INSERT + 조회.

        참조: src/agents/shared/learning.py
        """
        test_id = "lp-inttest-001"
        try:
            await mysql_client.execute(
                "INSERT IGNORE INTO learning_patterns "
                "(pattern_id, session_id, user_id, mode, preferred_topics, "
                "emotional_patterns, effectiveness_score) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    test_id,
                    "sess_test000001",
                    "test-user-001",
                    "podcast",
                    json.dumps(["테스트주제"]),
                    json.dumps(["테스트패턴"]),
                    0.75,
                ),
            )
            rows = await mysql_client.fetch(
                "SELECT * FROM learning_patterns WHERE user_id = %s "
                "ORDER BY created_at DESC",
                ("test-user-001",),
            )
            assert len(rows) >= 1
            found = any(r["pattern_id"] == test_id for r in rows)
            assert found, f"{test_id}가 조회 결과에 없음"
        finally:
            await mysql_client.execute(
                "DELETE FROM learning_patterns WHERE pattern_id = %s",
                (test_id,),
            )

    async def test_episode_segment_join(self, mysql_client, seed_data):
        """에피소드 + 세그먼트 JOIN 쿼리.

        참조: src/agents/podcast/script_personalizer.py, episode_memory.py
        """
        rows = await mysql_client.fetch(
            "SELECT e.episode_id, e.episode_title, s.segment_id, "
            "s.segment_type, s.script_text "
            "FROM podcast_episodes e "
            "JOIN podcast_segments s ON e.episode_id = s.episode_id "
            "WHERE e.user_id = %s ORDER BY e.episode_id, s.segment_order",
            ("test-user-001",),
        )
        assert len(rows) >= 3  # ep-test-001 has 3 segments
        episode_ids = {r["episode_id"] for r in rows}
        assert "ep-test-001" in episode_ids
        segment_types = [r["segment_type"] for r in rows if r["episode_id"] == "ep-test-001"]
        assert "opening" in segment_types
        assert "closing" in segment_types

    async def test_emotion_log_query(self, mysql_client, seed_data):
        """EmotionAgent 패턴: emotion_logs 조회.

        참조: src/agents/podcast/emotion.py
        """
        rows = await mysql_client.fetch(
            "SELECT log_id, primary_emotion, intensity, valence, arousal, "
            "secondary_emotions FROM emotion_logs "
            "WHERE user_id = %s AND session_id = %s",
            ("test-user-001", "sess_test000001"),
        )
        assert len(rows) >= 1
        row = rows[0]
        assert row["primary_emotion"] == "anxiety"
        assert 0.0 <= row["intensity"] <= 1.0
        assert -1.0 <= row["valence"] <= 1.0

    async def test_visualization_meta_query(self, mysql_client, seed_data):
        """VisualizationAgent 패턴: visualization_meta 조회.

        참조: src/agents/podcast/visualization.py
        """
        rows = await mysql_client.fetch(
            "SELECT visualization_id, s3_key, cdn_url, image_prompt "
            "FROM visualization_meta "
            "WHERE user_id = %s AND episode_id = %s",
            ("test-user-001", "ep-test-001"),
        )
        assert len(rows) >= 1
        row = rows[0]
        assert row["s3_key"].startswith("vis/")
        assert row["image_prompt"]  # 비어있지 않음
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestMySQLAgentQueries -v`
Expected: 5 tests PASSED (Docker 실행 중일 때)

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: MySQL 에이전트 쿼리 패턴 통합 테스트 (5개)"
```

---

### Task 3: TestNeo4jAgentQueries — Neo4j 에이전트 쿼리 패턴 검증

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: Neo4j 테스트 클래스 추가**

```python
# ===================================================================
# 2. Neo4j 에이전트 쿼리 패턴
# ===================================================================
@requires_neo4j
class TestNeo4jAgentQueries:
    """에이전트가 사용하는 Neo4j 쿼리 패턴을 실제 DB에서 검증한다."""

    async def test_topic_lookup(self, neo4j_client, seed_data):
        """PodcastReasoning 패턴: Topic 노드 조회.

        참조: src/agents/podcast/podcast_reasoning.py
        """
        result = await neo4j_client.execute_query(
            "MATCH (n:Topic) WHERE n.topic_name = $name RETURN n",
            {"name": "work_stress"},
        )
        assert len(result) == 1
        node = result[0]["n"]
        assert node["domain"] == "work"

    async def test_got_traversal(self, neo4j_client, seed_data):
        """PodcastReasoning 패턴: GoTNode LEADS_TO 관계 탐색.

        참조: src/agents/podcast/podcast_reasoning.py
        """
        result = await neo4j_client.execute_query(
            "MATCH (root:GoTNode {got_node_id: $id})"
            "-[:LEADS_TO*1..3]->(leaf:GoTNode) "
            "RETURN leaf.got_node_id AS id, leaf.label AS label, leaf.node_type AS type",
            {"id": "got-test-001"},
        )
        assert len(result) >= 1
        ids = {r["id"] for r in result}
        assert "got-test-002" in ids  # 직접 연결
        assert "got-test-003" in ids  # 2-hop 연결

    async def test_full_reasoning_chain(self, neo4j_client, seed_data):
        """세션 → GoTNode 전체 체인 조회.

        참조: src/agents/podcast/podcast_reasoning.py (그래프 구성 후 탐색)
        """
        result = await neo4j_client.execute_query(
            "MATCH (s:Session {session_id: $sid})-[:REASONED_BY]->(root:GoTNode)"
            "-[:LEADS_TO*0..5]->(node:GoTNode) "
            "RETURN node.got_node_id AS id, node.node_type AS type",
            {"sid": "sess_test000001"},
        )
        assert len(result) >= 3  # root + branch + leaf
        types = {r["type"] for r in result}
        assert "root" in types
        assert "leaf" in types

    async def test_session_covers_topic(self, neo4j_client, seed_data):
        """세션이 다루는 주제(Topic) 관계 조회."""
        result = await neo4j_client.execute_query(
            "MATCH (s:Session {session_id: $sid})-[:COVERS]->(t:Topic) "
            "RETURN t.topic_name AS topic, t.domain AS domain",
            {"sid": "sess_test000001"},
        )
        assert len(result) >= 1
        topics = {r["topic"] for r in result}
        assert "work_stress" in topics

    async def test_emotion_cooccurrence(self, neo4j_client, seed_data):
        """감정 동시 출현(OFTEN_COOCCURS) 관계 조회.

        참조: Emotion Agent 감정 패턴 분석
        """
        result = await neo4j_client.execute_query(
            "MATCH (e1:Emotion {emotion_key: $key})-[r:OFTEN_COOCCURS]->(e2:Emotion) "
            "RETURN e2.emotion_key AS cooccurs_with, r.count AS count",
            {"key": "anxiety"},
        )
        assert len(result) >= 1
        cooccurs = {r["cooccurs_with"] for r in result}
        assert "stress" in cooccurs

    async def test_create_and_cleanup_got_node(self, neo4j_client):
        """GoTNode 생성 → 조회 → 삭제 라이프사이클.

        PodcastReasoning이 추론 그래프를 동적으로 생성하는 패턴 검증.
        """
        test_id = "got-inttest-001"
        try:
            await neo4j_client.execute_query(
                "CREATE (g:GoTNode {got_node_id: $id, node_type: 'root', "
                "label: '통합테스트 루트', episode_id: 'ep-inttest'})",
                {"id": test_id},
            )
            result = await neo4j_client.execute_query(
                "MATCH (g:GoTNode {got_node_id: $id}) RETURN g",
                {"id": test_id},
            )
            assert len(result) == 1
            assert result[0]["g"]["node_type"] == "root"
        finally:
            await neo4j_client.execute_query(
                "MATCH (g:GoTNode {got_node_id: $id}) DETACH DELETE g",
                {"id": test_id},
            )
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestNeo4jAgentQueries -v`
Expected: 6 tests PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: Neo4j 에이전트 쿼리 패턴 통합 테스트 (6개)"
```

---

### Task 4: TestPineconeMockQueries — Pinecone Mock 벡터 검색 검증

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: Pinecone 테스트 클래스 추가**

```python
# ===================================================================
# 3. Pinecone Mock 벡터 검색
# ===================================================================
class TestPineconeMockQueries:
    """Pinecone Mock 클라이언트의 벡터 검색 동작을 검증한다."""

    async def test_knowledge_domain_filter_search(self, pinecone_client, seed_data):
        """KnowledgeAgent 패턴: domain 필터 + 벡터 검색.

        참조: src/agents/conversation/knowledge.py
        """
        from dev.local_db.seed import _generate_deterministic_vector

        query_vector = _generate_deterministic_vector(42, 384)  # doc001과 동일 시드
        result = await pinecone_client.query(
            index="expert_knowledge",
            vector=query_vector,
            filter={"domain": {"$in": ["psychology"]}},
            top_k=5,
            namespace="psychology",
            include_metadata=True,
        )
        matches = result["matches"]
        assert len(matches) >= 1
        assert matches[0]["id"] == "vec_knowledge_doc001"  # 자기 자신이 가장 유사
        assert matches[0]["score"] > 0.99  # 동일 벡터이므로 ~1.0
        assert matches[0]["metadata"]["domain"] == "psychology"

    async def test_episode_memory_namespace_search(self, pinecone_client, seed_data):
        """EpisodeMemory 패턴: user namespace별 에피소드 검색.

        참조: src/agents/podcast/episode_memory.py
        """
        from dev.local_db.seed import _generate_deterministic_vector

        query_vector = _generate_deterministic_vector(200, 384)  # ep001 시드
        result = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=query_vector,
            top_k=5,
            namespace="test-user-001",
            include_metadata=True,
        )
        matches = result["matches"]
        assert len(matches) >= 1
        assert matches[0]["metadata"]["episode_id"] == "ep-test-001"

    async def test_upsert_and_retrieve(self, pinecone_client):
        """벡터 upsert → 즉시 조회 라운드트립."""
        from dev.local_db.seed import _generate_deterministic_vector

        test_vec = _generate_deterministic_vector(999, 384)
        await pinecone_client.upsert(
            "test_index",
            [{"id": "vec_inttest_001", "values": test_vec, "metadata": {"label": "test"}}],
            namespace="inttest",
        )
        result = await pinecone_client.query(
            index="test_index",
            vector=test_vec,
            top_k=1,
            namespace="inttest",
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["id"] == "vec_inttest_001"

    async def test_filter_excludes_non_matching(self, pinecone_client, seed_data):
        """$ne 필터로 특정 domain 제외 검증."""
        from dev.local_db.seed import _generate_deterministic_vector

        query_vector = _generate_deterministic_vector(42, 384)
        result = await pinecone_client.query(
            index="expert_knowledge",
            vector=query_vector,
            filter={"domain": {"$ne": "psychology"}},
            top_k=10,
            namespace="psychology",
            include_metadata=True,
        )
        for match in result["matches"]:
            assert match["metadata"]["domain"] != "psychology"
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestPineconeMockQueries -v`
Expected: 4 tests PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: Pinecone Mock 벡터 검색 통합 테스트 (4개)"
```

---

### Task 5: TestFactoryWiring — Factory 패턴 검증

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: Factory 테스트 클래스 추가**

```python
# ===================================================================
# 4. Factory 패턴 검증
# ===================================================================
@requires_all_db
class TestFactoryWiring:
    """STORAGE_MODE=local에서 Factory가 올바른 클라이언트를 반환하는지 검증한다."""

    async def test_factory_returns_correct_types(self):
        """create_rdb_client/create_graph_client가 직접 클라이언트를 반환한다."""
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

    async def test_factory_clients_can_query(self):
        """Factory가 반환한 클라이언트로 실제 쿼리가 실행된다."""
        from src.db.factory import create_graph_client, create_rdb_client

        rdb = create_rdb_client()
        graph = create_graph_client()

        try:
            # MySQL ping
            mysql_rows = await rdb.fetch("SELECT 1 AS ping")
            assert mysql_rows[0]["ping"] == 1

            # Neo4j ping
            neo4j_rows = await graph.execute_query("RETURN 1 AS ping")
            assert neo4j_rows[0]["ping"] == 1
        finally:
            await rdb.close()
            await graph.close()
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestFactoryWiring -v`
Expected: 2 tests PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: Factory 패턴 통합 테스트 (2개)"
```

---

### Task 6: TestCrossDBConsistency — 크로스 DB 데이터 일관성 검증

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: 크로스 DB 테스트 클래스 추가**

```python
# ===================================================================
# 5. 크로스 DB 데이터 일관성
# ===================================================================
@requires_all_db
class TestCrossDBConsistency:
    """MySQL과 Neo4j 간 시드 데이터의 ID 일관성을 검증한다."""

    async def test_user_ids_match(self, mysql_client, neo4j_client, seed_data):
        """MySQL users.user_id와 Neo4j User.user_id가 일치한다."""
        mysql_rows = await mysql_client.fetch("SELECT user_id FROM users WHERE user_id LIKE 'test-user-%'")
        mysql_ids = {r["user_id"] for r in mysql_rows}

        neo4j_rows = await neo4j_client.execute_query(
            "MATCH (u:User) WHERE u.user_id STARTS WITH 'test-user-' RETURN u.user_id AS uid"
        )
        neo4j_ids = {r["uid"] for r in neo4j_rows}

        assert mysql_ids == neo4j_ids, f"불일치: MySQL={mysql_ids}, Neo4j={neo4j_ids}"

    async def test_session_ids_match(self, mysql_client, neo4j_client, seed_data):
        """MySQL sessions.session_id와 Neo4j Session.session_id가 일치한다."""
        mysql_rows = await mysql_client.fetch(
            "SELECT session_id FROM sessions WHERE session_id LIKE 'sess_test%'"
        )
        mysql_ids = {r["session_id"] for r in mysql_rows}

        neo4j_rows = await neo4j_client.execute_query(
            "MATCH (s:Session) WHERE s.session_id STARTS WITH 'sess_test' "
            "RETURN s.session_id AS sid"
        )
        neo4j_ids = {r["sid"] for r in neo4j_rows}

        # Neo4j에는 시드된 세션만 있을 수 있음 (MySQL이 더 많을 수 있음)
        assert neo4j_ids.issubset(mysql_ids), (
            f"Neo4j에만 존재하는 세션: {neo4j_ids - mysql_ids}"
        )

    async def test_episode_ids_in_pinecone_match_mysql(
        self, mysql_client, pinecone_client, seed_data
    ):
        """Pinecone mem_podcast_episode의 episode_id가 MySQL에 존재한다."""
        from dev.local_db.seed import _generate_deterministic_vector

        # Pinecone에서 모든 에피소드 벡터 조회
        query_vector = _generate_deterministic_vector(200, 384)
        result = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=query_vector,
            top_k=100,
            namespace="test-user-001",
            include_metadata=True,
        )
        pinecone_ep_ids = {m["metadata"]["episode_id"] for m in result["matches"]}

        # MySQL에서 해당 에피소드 존재 확인
        for ep_id in pinecone_ep_ids:
            rows = await mysql_client.fetch(
                "SELECT episode_id FROM podcast_episodes WHERE episode_id = %s",
                (ep_id,),
            )
            assert len(rows) == 1, f"Pinecone에 있지만 MySQL에 없는 에피소드: {ep_id}"
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestCrossDBConsistency -v`
Expected: 3 tests PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: 크로스 DB 데이터 일관성 검증 (3개)"
```

---

### Task 7: TestMiniPipeline — TIER별 데이터 흐름 시뮬레이션

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: 미니 파이프라인 테스트 추가**

```python
# ===================================================================
# 6. 미니 파이프라인 (TIER별 데이터 흐름)
# ===================================================================
@requires_all_db
class TestMiniPipeline:
    """실제 에이전트 파이프라인의 DB 접근 순서를 시뮬레이션한다."""

    async def test_podcast_pipeline_db_flow(
        self, mysql_client, neo4j_client, pinecone_client, seed_data
    ):
        """팟캐스트 파이프라인의 DB 접근 순서를 시뮬레이션한다.

        TIER 0 → 1 → 2 → 4 순서로 각 에이전트가 DB에서 읽고 쓰는 패턴을 검증.
        """
        user_id = "test-user-001"
        session_id = "sess_test000001"

        # --- TIER 1: Emotion Agent — emotion_logs 조회 ---
        emotion_rows = await mysql_client.fetch(
            "SELECT primary_emotion, intensity FROM emotion_logs "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        assert len(emotion_rows) >= 1
        primary_emotion = emotion_rows[0]["primary_emotion"]

        # --- TIER 1: PodcastReasoning — Neo4j Topic 탐색 ---
        topics = await neo4j_client.execute_query(
            "MATCH (s:Session {session_id: $sid})-[:COVERS]->(t:Topic) "
            "RETURN t.topic_name AS topic",
            {"sid": session_id},
        )
        assert len(topics) >= 1

        # --- TIER 1: PodcastReasoning — Neo4j GoT 그래프 탐색 ---
        got_nodes = await neo4j_client.execute_query(
            "MATCH (s:Session {session_id: $sid})-[:REASONED_BY]->(root:GoTNode)"
            "-[:LEADS_TO*0..5]->(node:GoTNode) "
            "RETURN node.label AS label",
            {"sid": session_id},
        )
        assert len(got_nodes) >= 1

        # --- TIER 1: KnowledgeAgent — Pinecone 벡터 검색 ---
        from dev.local_db.seed import _generate_deterministic_vector

        query_vec = _generate_deterministic_vector(42, 384)
        knowledge = await pinecone_client.query(
            index="expert_knowledge",
            vector=query_vec,
            filter={"domain": {"$in": ["psychology", "mental_health"]}},
            top_k=3,
            namespace="psychology",
        )
        assert len(knowledge["matches"]) >= 1

        # --- TIER 1: EpisodeMemory — Pinecone namespace 검색 ---
        ep_vec = _generate_deterministic_vector(200, 384)
        past_episodes = await pinecone_client.query(
            index="mem_podcast_episode",
            vector=ep_vec,
            top_k=5,
            namespace=user_id,
        )
        assert len(past_episodes["matches"]) >= 1

        # --- TIER 4: ScriptPersonalizer — users 프로필 조회 ---
        profile = await mysql_client.fetch(
            "SELECT preferred_style, preferred_attitude "
            "FROM users WHERE user_id = %s",
            (user_id,),
        )
        assert len(profile) == 1
        assert profile[0]["preferred_style"] == "warm"
```

**Step 2: 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py::TestMiniPipeline -v`
Expected: 1 test PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: 미니 파이프라인 TIER별 DB 흐름 통합 테스트"
```

---

### Task 8: TestDataCleanup — 시드 데이터 정리 검증

**Files:**
- Modify: `dev/local_db/test_db_integration.py` (append)

**Step 1: 데이터 정리 테스트 추가**

```python
# ===================================================================
# 7. 데이터 정리 검증
# ===================================================================
@requires_mysql
class TestDataCleanupMySQL:
    """MySQL 테스트 데이터 정리가 올바르게 동작하는지 검증한다."""

    async def test_cleanup_removes_test_data(self, mysql_client):
        """테스트 prefix 데이터 삽입 → 삭제 → 조회 0건."""
        uid = "test-user-cleanup-001"
        try:
            await mysql_client.execute(
                "INSERT IGNORE INTO users (user_id, display_name) VALUES (%s, %s)",
                (uid, "정리테스트"),
            )
            rows = await mysql_client.fetch(
                "SELECT * FROM users WHERE user_id = %s", (uid,)
            )
            assert len(rows) == 1

            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s", (uid,)
            )
            rows = await mysql_client.fetch(
                "SELECT * FROM users WHERE user_id = %s", (uid,)
            )
            assert len(rows) == 0
        except Exception:
            # 정리 보장
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s", (uid,)
            )
            raise

    async def test_fk_cascade_delete(self, mysql_client):
        """FK CASCADE: users 삭제 시 sessions도 자동 삭제."""
        uid = "test-user-cascade-001"
        sid = "sess_test_cascade_001"
        try:
            await mysql_client.execute(
                "INSERT IGNORE INTO users (user_id) VALUES (%s)", (uid,)
            )
            await mysql_client.execute(
                "INSERT IGNORE INTO sessions (session_id, user_id, mode) VALUES (%s, %s, %s)",
                (sid, uid, "podcast"),
            )
            # users 삭제 → sessions도 cascade 삭제
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s", (uid,)
            )
            rows = await mysql_client.fetch(
                "SELECT * FROM sessions WHERE session_id = %s", (sid,)
            )
            assert len(rows) == 0, "FK CASCADE 미동작: sessions 레코드가 남아있음"
        except Exception:
            await mysql_client.execute(
                "DELETE FROM sessions WHERE session_id = %s", (sid,)
            )
            await mysql_client.execute(
                "DELETE FROM users WHERE user_id = %s", (uid,)
            )
            raise


@requires_neo4j
class TestDataCleanupNeo4j:
    """Neo4j 테스트 데이터 정리가 올바르게 동작하는지 검증한다."""

    async def test_detach_delete_removes_node_and_relations(self, neo4j_client):
        """DETACH DELETE로 노드와 관계가 모두 삭제된다."""
        test_id = "got-cleanup-001"
        try:
            await neo4j_client.execute_query(
                "CREATE (g1:GoTNode {got_node_id: $id1, node_type: 'root'})"
                "-[:LEADS_TO]->"
                "(g2:GoTNode {got_node_id: $id2, node_type: 'leaf'})",
                {"id1": test_id, "id2": f"{test_id}-leaf"},
            )
            await neo4j_client.execute_query(
                "MATCH (g:GoTNode) WHERE g.got_node_id STARTS WITH $prefix "
                "DETACH DELETE g",
                {"prefix": "got-cleanup-"},
            )
            result = await neo4j_client.execute_query(
                "MATCH (g:GoTNode) WHERE g.got_node_id STARTS WITH $prefix RETURN g",
                {"prefix": "got-cleanup-"},
            )
            assert len(result) == 0
        except Exception:
            await neo4j_client.execute_query(
                "MATCH (g:GoTNode) WHERE g.got_node_id STARTS WITH $prefix "
                "DETACH DELETE g",
                {"prefix": "got-cleanup-"},
            )
            raise
```

**Step 2: 전체 테스트 실행**

Run: `pytest dev/local_db/test_db_integration.py -v`
Expected: 전체 ~25개 테스트 PASSED

**Step 3: 커밋**

```bash
git add dev/local_db/test_db_integration.py
git commit -m "test: 데이터 정리 + FK cascade 검증 통합 테스트 (3개)"
```

---

## 전체 테스트 요약

| # | 클래스 | 테스트 수 | DB | 검증 대상 |
|---|--------|-----------|-----|---------|
| 1 | TestMySQLAgentQueries | 5 | MySQL | ScriptPersonalizer, LearningAgent, 에피소드 JOIN, 감정로그, 시각화 |
| 2 | TestNeo4jAgentQueries | 6 | Neo4j | Topic 조회, GoT 탐색, 전체 체인, COVERS, 감정 동시출현, 생성/삭제 |
| 3 | TestPineconeMockQueries | 4 | Pinecone | domain 필터, namespace 검색, upsert 라운드트립, $ne 필터 |
| 4 | TestFactoryWiring | 2 | All | 클라이언트 타입, 실제 쿼리 |
| 5 | TestCrossDBConsistency | 3 | All | user_id, session_id, episode_id 일관성 |
| 6 | TestMiniPipeline | 1 | All | TIER별 DB 접근 순서 시뮬레이션 |
| 7 | TestDataCleanupMySQL | 2 | MySQL | prefix 삭제, FK CASCADE |
| 8 | TestDataCleanupNeo4j | 1 | Neo4j | DETACH DELETE |
| **합계** | | **24** | | |

## 파일 변경 요약

| 파일 | 작업 | 비고 |
|------|------|------|
| `dev/local_db/conftest.py` | **신규** | DB 프로브 + skip 마커 + 클라이언트 fixture |
| `dev/local_db/test_db_integration.py` | **신규** | 8개 테스트 클래스, 24개 테스트 메서드 |

**기존 파일 수정: 없음** (`src/`, `tests/`, `config/` 등 무수정)

## 실행 순서

```bash
# 1. DB 시작 + 시드 (이미 완료된 경우 생략)
docker compose -f dev/local_db/docker-compose.db.yml up -d
export $(cat dev/local_db/.env.db | xargs)
python3 -m dev.local_db.seed

# 2. 전체 통합 테스트 실행
pytest dev/local_db/test_db_integration.py -v

# 3. 특정 DB만 테스트
pytest dev/local_db/test_db_integration.py -v -k "MySQL"
pytest dev/local_db/test_db_integration.py -v -k "Neo4j"
pytest dev/local_db/test_db_integration.py -v -k "Pinecone"

# 4. Docker 미실행 시 → 자동 skip (에러 아님)
```

## 삭제 방법

```bash
# 테스트 파일만 삭제
rm dev/local_db/conftest.py dev/local_db/test_db_integration.py

# 전체 로컬 DB 환경 삭제
docker compose -f dev/local_db/docker-compose.db.yml down -v
rm -rf dev/local_db/
```

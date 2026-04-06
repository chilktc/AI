"""
Neo4j 그래프 DB 직접 클라이언트.

PodcastReasoning 에이전트의 지식 그래프 노드 구성/탐색용.
external_schemas.py의 Neo4j 노드/관계 스키마와 연동한다.

사용법:
    async with Neo4jClient() as client:
        results = await client.execute_query(
            "MATCH (n:Topic) WHERE n.name = $name RETURN n",
            params={"name": "anxiety"},
        )
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neo4j import AsyncGraphDatabase

from src.db.base import BaseGraphClient

logger = logging.getLogger(__name__)


class Neo4jClient(BaseGraphClient):
    """Neo4j 그래프 DB 비동기 클라이언트.

    환경변수:
        NEO4J_URL: Neo4j 접속 URI (bolt://...)
        NEO4J_USER: 인증 사용자명
        NEO4J_PASSWORD: 인증 비밀번호
    """

    def __init__(
        self,
        url: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._url = url if url is not None else os.getenv("NEO4J_URL", "bolt://localhost:7687")
        self._user = user if user is not None else os.getenv("NEO4J_USER", "neo4j")
        self._password = password if password is not None else os.getenv("NEO4J_PASSWORD", "")
        assert isinstance(self._url, str)
        assert isinstance(self._user, str) and isinstance(self._password, str)
        self._driver = AsyncGraphDatabase.driver(
            self._url,
            auth=(self._user, self._password),
        )

    async def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Cypher 쿼리를 실행한다."""
        async with self._driver.session() as session:
            result = await session.run(query, parameters=params or {})
            records = await result.data()
            return records

    async def close(self) -> None:
        """드라이버 연결을 정리한다."""
        await self._driver.close()
        logger.debug("Neo4jClient closed")

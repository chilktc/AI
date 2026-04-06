"""
MySQL 관계형 DB 직접 클라이언트.

KnowledgeAgent의 _get_documents() 및
ScriptPersonalizer의 사용자 프로필 조회와 호환되는 인터페이스를 제공한다.

PyMySQL + asyncio.to_thread() 래핑 패턴 (llm_client.py와 동일).

사용법:
    async with MySQLClient() as client:
        rows = await client.fetch(
            "SELECT * FROM documents WHERE id IN (%s, %s)",
            params=("doc1", "doc2"),
        )
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

import pymysql
import pymysql.cursors

from src.db.base import BaseRDBClient

logger = logging.getLogger(__name__)


def _parse_mysql_url(url: str) -> dict[str, Any]:
    """MySQL URL을 pymysql 연결 파라미터로 변환한다."""
    parsed = urlparse(url.replace("mysql+pymysql://", "mysql://"))
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "database": parsed.path.lstrip("/") if parsed.path else "",
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }


class MySQLClient(BaseRDBClient):
    """MySQL 직접 클라이언트 (PyMySQL + asyncio.to_thread).

    환경변수:
        MYSQL_URL: MySQL 접속 URL (mysql+pymysql://user:pass@host:port/db)
    """

    def __init__(self, url: str | None = None) -> None:
        self._url = (
            url
            if url is not None
            else os.getenv("MYSQL_URL", "mysql+pymysql://root:@localhost:3306/mindlog")
        )
        assert isinstance(self._url, str)
        self._conn_params = _parse_mysql_url(self._url)
        self._connection: pymysql.Connection | None = None

    def _get_connection(self) -> pymysql.Connection:
        """커넥션을 생성하거나 재사용한다."""
        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(**self._conn_params)
        return self._connection

    def _do_fetch(self, query: str, params: Any) -> list[dict[str, Any]]:
        """동기 SELECT 실행."""
        conn = self._get_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall())

    def _do_execute(self, query: str, params: Any) -> int:
        """동기 INSERT/UPDATE/DELETE 실행."""
        conn = self._get_connection()
        with conn.cursor() as cursor:
            affected = cursor.execute(query, params)
            conn.commit()
            return int(affected)

    async def fetch(
        self,
        query: str,
        params: Any = None,
    ) -> list[dict[str, Any]]:
        """SELECT 쿼리를 비동기로 실행한다."""
        return await asyncio.to_thread(self._do_fetch, query, params)

    async def execute(
        self,
        query: str,
        params: Any = None,
    ) -> int:
        """INSERT/UPDATE/DELETE를 비동기로 실행한다."""
        return await asyncio.to_thread(self._do_execute, query, params)

    async def close(self) -> None:
        """커넥션을 닫는다."""
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None
        logger.debug("MySQLClient closed")

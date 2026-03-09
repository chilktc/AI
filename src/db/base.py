"""
저장소 추상 인터페이스.

DB 접근 전략 패턴의 ABC(Abstract Base Class) 계층을 정의한다.
STORAGE_MODE 환경변수에 따라 직접 클라이언트 또는 Backend API 프록시 구현체를 선택한다.

구현체:
  - 직접: pinecone_client, neo4j_client, mysql_client, s3_client
  - 프록시: api_proxy (Backend API 경유)

사용법:
    from src.db import create_vector_client
    client = create_vector_client()  # STORAGE_MODE에 따라 자동 선택
    result = await client.query(index="...", vector=[...], filter={}, top_k=5)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Self


class _AsyncCloseable(ABC):
    """공통 라이프사이클 — close() + 컨텍스트 매니저.

    모든 DB 클라이언트의 부모 클래스. 커넥션 정리를 보장한다.
    """

    @abstractmethod
    async def close(self) -> None:
        """리소스를 정리한다."""
        ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


class BaseVectorClient(_AsyncCloseable):
    """벡터 DB 추상 인터페이스 — Pinecone 또는 API 프록시.

    KnowledgeAgent, BaseMemoryAgent가 사용한다.
    """

    @abstractmethod
    async def query(
        self,
        index: str,
        vector: list[float],
        filter: dict[str, Any],
        top_k: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """벡터 유사도 검색을 수행한다.

        Args:
            index: 인덱스 이름
            vector: 쿼리 임베딩 벡터
            filter: 메타데이터 필터 (예: {"domain": {"$in": ["psychology"]}})
            top_k: 반환할 최대 결과 수
            **kwargs: 추가 옵션 (include_metadata 등)

        Returns:
            검색 결과 dict (matches, namespace 등)
        """
        ...

    @abstractmethod
    async def upsert(
        self,
        index: str,
        vectors: list[dict[str, Any]],
        namespace: str = "",
    ) -> dict[str, Any]:
        """벡터를 삽입/갱신한다.

        Args:
            index: 인덱스 이름
            vectors: 벡터 데이터 리스트 (id, values, metadata)
            namespace: 네임스페이스 (mem_conversation, mem_podcast_episode 등)

        Returns:
            upsert 결과 dict
        """
        ...


class BaseGraphClient(_AsyncCloseable):
    """그래프 DB 추상 인터페이스 — Neo4j 또는 API 프록시.

    PodcastReasoning 에이전트가 지식 그래프 노드 구성/탐색에 사용한다.
    external_schemas.py의 Neo4j 노드/관계 스키마와 연동.
    """

    @abstractmethod
    async def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Cypher 쿼리를 실행한다.

        Args:
            query: Cypher 쿼리 문자열
            params: 쿼리 파라미터

        Returns:
            쿼리 결과 레코드 리스트
        """
        ...


class BaseRDBClient(_AsyncCloseable):
    """관계형 DB 추상 인터페이스 — MySQL 또는 API 프록시.

    KnowledgeAgent, ScriptPersonalizer가 사용한다.
    """

    @abstractmethod
    async def fetch(
        self,
        query: str,
        params: Any = None,
    ) -> list[dict[str, Any]]:
        """SELECT 쿼리를 실행하고 결과를 반환한다.

        Args:
            query: SQL 쿼리 문자열
            params: 쿼리 파라미터

        Returns:
            결과 행 리스트 (각 행은 dict)
        """
        ...

    @abstractmethod
    async def execute(
        self,
        query: str,
        params: Any = None,
    ) -> int:
        """INSERT/UPDATE/DELETE 쿼리를 실행한다.

        Args:
            query: SQL 쿼리 문자열
            params: 쿼리 파라미터

        Returns:
            영향 받은 행 수
        """
        ...


class BaseStorageClient(_AsyncCloseable):
    """오브젝트 스토리지 추상 인터페이스 — S3 직접 또는 Backend 프록시.

    C-3(읽기: s3:Get*, s3:List*) + 4-4(쓰기: s3:PutObject) 통합.
    """

    @abstractmethod
    async def get_object(self, key: str) -> bytes:
        """S3 오브젝트를 읽는다.

        Args:
            key: S3 객체 키

        Returns:
            객체 바이트 데이터
        """
        ...

    @abstractmethod
    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        """S3에 오브젝트를 업로드한다.

        Args:
            key: S3 객체 키
            data: 업로드할 바이트 데이터
            content_type: MIME 타입

        Returns:
            boto3 put_object 응답 dict (ETag 등 메타데이터 포함)
        """
        ...

    @abstractmethod
    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 100,
    ) -> list[dict[str, Any]]:
        """S3 오브젝트 목록을 조회한다.

        Args:
            prefix: 키 프리픽스 필터
            max_keys: 최대 반환 수

        Returns:
            객체 메타데이터 리스트
        """
        ...

    @abstractmethod
    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """S3 Presigned URL을 생성한다.

        Args:
            key: S3 객체 키
            expires_in: URL 유효 기간 (초, 기본 1시간)

        Returns:
            Presigned URL 문자열
        """
        ...

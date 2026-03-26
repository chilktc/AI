"""
Backend API 프록시 구현체 4종 (Vector, Graph, RDB, Storage).

STORAGE_MODE=proxy 또는 hybrid 모드에서 사용.
기존 BackendClient를 내부에서 활용하여 Backend 서버를 경유한다.

모든 TODO(backend) 주석은 Backend팀과의 협의 사항을 표시한다.
검색: grep -rn "TODO(backend)" src/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.backend_resources import (
    RESOURCE_GRAPH_QUERY,
    RESOURCE_STORAGE_OBJECT,
    RESOURCE_STORAGE_UPLOAD,
    RESOURCE_VECTOR_SEARCH,
)
from src.api.client import BackendClient
from src.api.contracts import SaveRequest
from src.db.base import BaseGraphClient, BaseRDBClient, BaseStorageClient, BaseVectorClient

logger = logging.getLogger(__name__)


class VectorProxyClient(BaseVectorClient):
    """Pinecone 대신 Backend API 경유 벡터 검색."""

    def __init__(self, backend_client: BackendClient) -> None:
        self._client = backend_client

    async def query(
        self,
        index: str,
        vector: list[float],
        filter: dict[str, Any],
        top_k: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Backend API를 통해 벡터 검색을 수행한다.

        TODO(backend): 4-3 벡터 검색 엔드포인트 POST /api/v1/vector/search 확인 필요
        TODO(backend): 4-3 요청/응답 스키마 확정 필요
        """
        request = SaveRequest(
            user_id="",
            session_id="",
            type="vector_search",
            data={
                "index": index,
                "vector": vector,
                "filter": filter,
                "top_k": top_k,
                **kwargs,
            },
            timestamp=datetime.now(timezone.utc),
        )
        response = await self._client.save(RESOURCE_VECTOR_SEARCH, request)
        return {"success": response.success, "id": response.id}

    async def upsert(
        self,
        index: str,
        vectors: list[dict[str, Any]],
        namespace: str = "",
    ) -> dict[str, Any]:
        """Backend API를 통해 벡터를 삽입/갱신한다.

        TODO(backend): 4-3 벡터 upsert 엔드포인트 확인 필요
        """
        request = SaveRequest(
            user_id="",
            session_id="",
            type="vector_upsert",
            data={
                "index": index,
                "vectors": vectors,
                "namespace": namespace,
            },
            timestamp=datetime.now(timezone.utc),
        )
        response = await self._client.save(RESOURCE_VECTOR_SEARCH, request)
        return {"success": response.success, "id": response.id}

    async def close(self) -> None:
        """BackendClient 리소스를 정리한다."""
        await self._client.close()
        logger.debug("VectorProxyClient closed")


class GraphProxyClient(BaseGraphClient):
    """Neo4j 대신 Backend API 경유 그래프 쿼리.

    PodcastReasoning 에이전트의 지식 그래프 조회용.
    """

    def __init__(self, backend_client: BackendClient) -> None:
        self._client = backend_client

    async def execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Backend API를 통해 그래프 쿼리를 실행한다.

        TODO(backend): 4-3 그래프 쿼리 엔드포인트 POST /api/v1/graph/query 확인 필요
        TODO(backend): 4-3 Cypher 쿼리 프록시 가능 여부 확인
        """
        request = SaveRequest(
            user_id="",
            session_id="",
            type="graph_query",
            data={
                "query": query,
                "params": params or {},
            },
            timestamp=datetime.now(timezone.utc),
        )
        response = await self._client.save(RESOURCE_GRAPH_QUERY, request)
        return [{"success": response.success, "id": response.id}]

    async def close(self) -> None:
        """BackendClient 리소스를 정리한다."""
        await self._client.close()
        logger.debug("GraphProxyClient closed")


class RDBProxyClient(BaseRDBClient):
    """MySQL 대신 Backend API 경유 (load 활용)."""

    def __init__(self, backend_client: BackendClient) -> None:
        self._client = backend_client

    async def fetch(
        self,
        query: str,
        params: Any = None,
    ) -> list[dict[str, Any]]:
        """Backend API를 통해 데이터를 조회한다.

        TODO(backend): 4-2 resource 경로 + 쿼리 파라미터 매핑 확정 필요
        TODO(backend): 4-3 SQL 쿼리 프록시 vs REST resource 방식 결정
        """
        response = await self._client.load(
            "data",
            user_id="",
            query=query,
        )
        return response.data

    async def execute(
        self,
        query: str,
        params: Any = None,
    ) -> int:
        """Backend API를 통해 데이터를 변경한다.

        TODO(backend): 4-3 쓰기 프록시 엔드포인트 확인 필요
        """
        request = SaveRequest(
            user_id="",
            session_id="",
            type="rdb_execute",
            data={"query": query, "params": params},
            timestamp=datetime.now(timezone.utc),
        )
        response = await self._client.save("data", request)
        return 1 if response.success else 0

    async def close(self) -> None:
        """BackendClient 리소스를 정리한다."""
        await self._client.close()
        logger.debug("RDBProxyClient closed")


class StorageProxyClient(BaseStorageClient):
    """S3 대신 Backend API 경유 (4-4 Backend 프록시 경로)."""

    def __init__(self, backend_client: BackendClient) -> None:
        self._client = backend_client

    async def get_object(self, key: str) -> bytes:
        """Backend API를 통해 S3 객체를 조회한다.

        TODO(backend): 4-4 S3 객체 조회 엔드포인트 확인 필요
        """
        response = await self._client.load(
            RESOURCE_STORAGE_OBJECT,
            user_id="",
            key=key,
        )
        if response.data:
            import base64

            return base64.b64decode(response.data[0].get("content", ""))
        return b""

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        """Backend API를 통해 S3에 업로드한다.

        TODO(backend): 4-4 이미지 업로드 엔드포인트 POST /api/v1/storage/upload 확인
        TODO(backend): 4-4 바이너리 데이터 전송 방식 확정 (base64 vs multipart)
        """
        import base64

        request = SaveRequest(
            user_id="",
            session_id="",
            type="storage_upload",
            data={
                "key": key,
                "content": base64.b64encode(data).decode(),
                "content_type": content_type,
            },
            timestamp=datetime.now(timezone.utc),
        )
        response = await self._client.save(RESOURCE_STORAGE_UPLOAD, request)
        return {"success": response.success, "id": response.id}

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 100,
    ) -> list[dict[str, Any]]:
        """Backend API를 통해 S3 객체 목록을 조회한다.

        TODO(backend): 4-4 객체 목록 조회 엔드포인트 확인 필요
        """
        response = await self._client.load(
            RESOURCE_STORAGE_OBJECT,
            user_id="",
            prefix=prefix,
            max_keys=str(max_keys),
        )
        return response.data

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """Backend API를 통해 Presigned URL을 생성한다.

        TODO(backend): 4-4 Presigned URL 생성 엔드포인트 확인 필요
        """
        response = await self._client.load(
            RESOURCE_STORAGE_OBJECT,
            user_id="",
            key=key,
            presign="true",
            expires_in=str(expires_in),
        )
        if response.data:
            return str(response.data[0].get("url", ""))
        return ""

    async def close(self) -> None:
        """BackendClient 리소스를 정리한다."""
        await self._client.close()
        logger.debug("StorageProxyClient closed")

"""
Pinecone 벡터 DB 직접 클라이언트.

KnowledgeAgent의 _search_knowledge_base() 및
BaseMemoryAgent의 벡터 검색과 호환되는 인터페이스를 제공한다.

사용 경로:
    - factory.py create_vector_client() → local/hybrid 모드에서 반환
    - KnowledgeAgent(Plan #19): 전문지식 인덱스(rag-suite-knowledge) 직접 쿼리
    - EpisodeMemoryAgent는 KT Cloud REST API 사용 → 이 클라이언트 미사용

사용법:
    client = PineconeClient()
    result = await client.query(
        index="rag-suite-knowledge",
        vector=embedding,
        filter={"domain": {"$in": ["psychology"]}},
        top_k=5,
        include_metadata=True,
    )
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pinecone import Pinecone

from src.db.base import BaseVectorClient
from src.utils.logger import get_agent_logger

logger = get_agent_logger("db.pinecone_client")


class PineconeClient(BaseVectorClient):
    """Pinecone 벡터 DB 직접 클라이언트.

    환경변수:
        PINECONE_API_KEY: Pinecone API 키
        PINECONE_ENVIRONMENT: Pinecone 환경 (선택)
    """

    def __init__(
        self,
        api_key: str | None = None,
        environment: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("PINECONE_API_KEY", "")
        self._environment = environment or os.getenv("PINECONE_ENVIRONMENT", "")
        self._pc = Pinecone(api_key=self._api_key)
        self._indexes: dict[str, Any] = {}

    def _get_index(self, index_name: str) -> Any:
        """인덱스 객체를 캐싱하여 반환한다."""
        if index_name not in self._indexes:
            self._indexes[index_name] = self._pc.Index(index_name)
        return self._indexes[index_name]

    async def query(
        self,
        index: str,
        vector: list[float],
        filter: dict[str, Any],
        top_k: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """벡터 유사도 검색을 수행한다."""
        idx = self._get_index(index)
        result = await asyncio.to_thread(
            idx.query,
            vector=vector,
            filter=filter,
            top_k=top_k,
            **kwargs,
        )
        return result.to_dict() if hasattr(result, "to_dict") else dict(result)

    async def upsert(
        self,
        index: str,
        vectors: list[dict[str, Any]],
        namespace: str = "",
    ) -> dict[str, Any]:
        """벡터를 삽입/갱신한다."""
        idx = self._get_index(index)
        result = await asyncio.to_thread(
            idx.upsert,
            vectors=vectors,
            namespace=namespace,
        )
        return result.to_dict() if hasattr(result, "to_dict") else dict(result)

    async def close(self) -> None:
        """리소스를 정리한다."""
        self._indexes.clear()
        logger.debug("PineconeClient closed")

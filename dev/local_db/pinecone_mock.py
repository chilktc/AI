"""
인메모리 Pinecone Mock 클라이언트 (개발 전용).

API 키 없이 로컬에서 벡터 검색을 테스트할 수 있는 standalone Mock.
기존 src/db/factory.py를 수정하지 않으며, 검증 스크립트에서만 직접 import하여 사용한다.

사용법:
    from dev.local_db.pinecone_mock import PineconeMockClient

    client = PineconeMockClient()
    await client.upsert("expert_knowledge", vectors=[...], namespace="psychology")
    result = await client.query("expert_knowledge", vector=[...], filter={...})
    await client.close()
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터 간 코사인 유사도를 계산한다."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _match_filter(metadata: dict[str, Any], filter_dict: dict[str, Any]) -> bool:
    """Pinecone 스타일 메타데이터 필터를 매칭한다.

    지원하는 연산자: $eq (기본), $in, $ne
    """
    for key, condition in filter_dict.items():
        value = metadata.get(key)
        if isinstance(condition, dict):
            for op, expected in condition.items():
                if op == "$eq" and value != expected:
                    return False
                if op == "$ne" and value == expected:
                    return False
                if op == "$in" and value not in expected:
                    return False
        else:
            if value != condition:
                return False
    return True


class PineconeMockClient:
    """인메모리 Pinecone Mock.

    BaseVectorClient 인터페이스와 동일한 메서드 시그니처를 제공한다.
    내부 저장 구조: {index_name: {namespace: [(id, vector, metadata)]}}
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, list[tuple[str, list[float], dict[str, Any]]]]] = {}
        logger.info("PineconeMockClient 초기화 (인메모리 모드)")

    async def query(
        self,
        index: str,
        vector: list[float],
        filter: dict[str, Any] | None = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """벡터 유사도 검색을 수행한다."""
        namespace = kwargs.get("namespace", "")
        include_metadata = kwargs.get("include_metadata", True)

        ns_store = self._store.get(index, {}).get(namespace, [])

        scored: list[tuple[float, str, dict[str, Any]]] = []
        for vec_id, stored_vector, metadata in ns_store:
            if filter and not _match_filter(metadata, filter):
                continue
            score = _cosine_similarity(vector, stored_vector)
            scored.append((score, vec_id, metadata))

        scored.sort(key=lambda x: x[0], reverse=True)
        matches = []
        for score, vec_id, metadata in scored[:top_k]:
            match: dict[str, Any] = {"id": vec_id, "score": score}
            if include_metadata:
                match["metadata"] = metadata
            matches.append(match)

        return {"matches": matches, "namespace": namespace}

    async def upsert(
        self,
        index: str,
        vectors: list[dict[str, Any]],
        namespace: str = "",
    ) -> dict[str, Any]:
        """벡터를 삽입/갱신한다."""
        if index not in self._store:
            self._store[index] = {}
        if namespace not in self._store[index]:
            self._store[index][namespace] = []

        ns_store = self._store[index][namespace]
        existing_ids = {item[0] for item in ns_store}

        upserted = 0
        for vec in vectors:
            vec_id = vec["id"]
            values = vec["values"]
            metadata = vec.get("metadata", {})

            if vec_id in existing_ids:
                ns_store[:] = [
                    (vid, val, meta) if vid != vec_id else (vec_id, values, metadata)
                    for vid, val, meta in ns_store
                ]
            else:
                ns_store.append((vec_id, values, metadata))
                existing_ids.add(vec_id)
            upserted += 1

        return {"upserted_count": upserted}

    async def close(self) -> None:
        """리소스를 정리한다."""
        self._store.clear()
        logger.debug("PineconeMockClient closed")

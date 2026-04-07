"""PineconeMockClient 및 헬퍼 함수 단위 테스트.

dev/local_db/pinecone_mock.py의 _cosine_similarity, _match_filter,
PineconeMockClient 엣지케이스를 검증한다.
"""
from __future__ import annotations

import math

import pytest

from dev.local_db.pinecone_mock import (
    PineconeMockClient,
    _cosine_similarity,
    _match_filter,
)


# ── _cosine_similarity 헬퍼 ─────────────────────────────────────────


class TestCosineSimilarity:
    """코사인 유사도 계산 헬퍼 테스트."""

    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_different_length_returns_zero(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_known_value(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        expected = 32.0 / (math.sqrt(14) * math.sqrt(77))
        assert _cosine_similarity(a, b) == pytest.approx(expected)


# ── _match_filter 헬퍼 ──────────────────────────────────────────────


class TestMatchFilter:
    """Pinecone 스타일 메타데이터 필터 매칭 테스트."""

    def test_eq_operator_match(self):
        metadata = {"domain": "psychology"}
        assert _match_filter(metadata, {"domain": {"$eq": "psychology"}}) is True

    def test_eq_operator_no_match(self):
        metadata = {"domain": "neuroscience"}
        assert _match_filter(metadata, {"domain": {"$eq": "psychology"}}) is False

    def test_ne_operator_match(self):
        metadata = {"domain": "neuroscience"}
        assert _match_filter(metadata, {"domain": {"$ne": "psychology"}}) is True

    def test_ne_operator_no_match(self):
        metadata = {"domain": "psychology"}
        assert _match_filter(metadata, {"domain": {"$ne": "psychology"}}) is False

    def test_in_operator_match(self):
        metadata = {"domain": "psychology"}
        assert _match_filter(metadata, {"domain": {"$in": ["psychology", "cbt"]}}) is True

    def test_in_operator_no_match(self):
        metadata = {"domain": "physics"}
        assert _match_filter(metadata, {"domain": {"$in": ["psychology", "cbt"]}}) is False

    def test_implicit_eq(self):
        """연산자 없이 값만 전달하면 $eq와 동일하게 동작한다."""
        metadata = {"label": "test"}
        assert _match_filter(metadata, {"label": "test"}) is True
        assert _match_filter(metadata, {"label": "other"}) is False

    def test_missing_key_returns_false(self):
        metadata = {"domain": "psychology"}
        assert _match_filter(metadata, {"missing_key": {"$eq": "value"}}) is False

    def test_empty_filter_always_matches(self):
        metadata = {"domain": "psychology"}
        assert _match_filter(metadata, {}) is True

    def test_multiple_conditions_all_must_match(self):
        metadata = {"domain": "psychology", "level": "advanced"}
        assert _match_filter(metadata, {
            "domain": {"$eq": "psychology"},
            "level": {"$eq": "advanced"},
        }) is True
        assert _match_filter(metadata, {
            "domain": {"$eq": "psychology"},
            "level": {"$eq": "beginner"},
        }) is False


# ── PineconeMockClient 엣지케이스 ──────────────────────────────────


@pytest.mark.asyncio
class TestPineconeMockClientEdgeCases:
    """PineconeMockClient 엣지케이스 테스트."""

    async def test_query_empty_store(self):
        client = PineconeMockClient()
        result = await client.query(
            index="nonexistent",
            vector=[1.0, 0.0],
            top_k=5,
        )
        assert result["matches"] == []
        assert result["namespace"] == ""

    async def test_query_empty_namespace(self):
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "v1", "values": [1.0, 0.0], "metadata": {"a": 1}},
        ], namespace="ns1")

        result = await client.query(
            index="idx", vector=[1.0, 0.0], top_k=5, namespace="ns2",
        )
        assert result["matches"] == []

    async def test_upsert_overwrite_existing_vector(self):
        """동일 ID로 upsert 시 벡터가 덮어써진다."""
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "v1", "values": [1.0, 0.0], "metadata": {"version": 1}},
        ])
        await client.upsert("idx", [
            {"id": "v1", "values": [0.0, 1.0], "metadata": {"version": 2}},
        ])

        result = await client.query(
            index="idx", vector=[0.0, 1.0], top_k=1,
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["metadata"]["version"] == 2

    async def test_query_top_k_limit(self):
        client = PineconeMockClient()
        vectors = [
            {"id": f"v{i}", "values": [float(i), 0.0], "metadata": {}}
            for i in range(10)
        ]
        await client.upsert("idx", vectors)

        result = await client.query(
            index="idx", vector=[5.0, 0.0], top_k=3,
        )
        assert len(result["matches"]) == 3

    async def test_query_sorted_by_similarity(self):
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "far", "values": [0.0, 1.0], "metadata": {}},
            {"id": "close", "values": [1.0, 0.0], "metadata": {}},
            {"id": "mid", "values": [0.7, 0.7], "metadata": {}},
        ])

        result = await client.query(
            index="idx", vector=[1.0, 0.0], top_k=3,
        )
        ids = [m["id"] for m in result["matches"]]
        assert ids[0] == "close"

    async def test_query_exclude_metadata(self):
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "v1", "values": [1.0], "metadata": {"secret": "data"}},
        ])

        result = await client.query(
            index="idx", vector=[1.0], top_k=1, include_metadata=False,
        )
        assert "metadata" not in result["matches"][0]

    async def test_upsert_returns_count(self):
        client = PineconeMockClient()
        result = await client.upsert("idx", [
            {"id": "v1", "values": [1.0], "metadata": {}},
            {"id": "v2", "values": [2.0], "metadata": {}},
        ])
        assert result["upserted_count"] == 2

    async def test_close_clears_all_data(self):
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "v1", "values": [1.0], "metadata": {}},
        ])
        await client.close()

        result = await client.query(index="idx", vector=[1.0], top_k=1)
        assert result["matches"] == []

    async def test_upsert_without_metadata(self):
        """metadata 키 없이 upsert해도 빈 dict로 기본 설정된다."""
        client = PineconeMockClient()
        await client.upsert("idx", [
            {"id": "v1", "values": [1.0, 0.0]},
        ])

        result = await client.query(
            index="idx", vector=[1.0, 0.0], top_k=1,
        )
        assert result["matches"][0]["metadata"] == {}

    async def test_multiple_indexes_isolated(self):
        """서로 다른 인덱스의 데이터가 격리된다."""
        client = PineconeMockClient()
        await client.upsert("idx_a", [
            {"id": "v1", "values": [1.0, 0.0], "metadata": {"src": "a"}},
        ])
        await client.upsert("idx_b", [
            {"id": "v2", "values": [0.0, 1.0], "metadata": {"src": "b"}},
        ])

        result_a = await client.query(index="idx_a", vector=[1.0, 0.0], top_k=10)
        result_b = await client.query(index="idx_b", vector=[0.0, 1.0], top_k=10)

        assert len(result_a["matches"]) == 1
        assert result_a["matches"][0]["id"] == "v1"
        assert len(result_b["matches"]) == 1
        assert result_b["matches"][0]["id"] == "v2"

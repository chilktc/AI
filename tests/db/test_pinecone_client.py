"""PineconeClient 단위 테스트.

Pinecone SDK를 sys.modules 레벨에서 mock하여
외부 패키지 설치 여부에 관계없이 PineconeClient의
query, upsert, close, 인덱스 캐싱 동작을 검증한다.
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _mock_pinecone_module():
    """pinecone 패키지를 sys.modules에 가짜 모듈로 주입한다.

    pinecone-client(구버전)가 설치된 환경에서도 import 에러 없이 테스트가 동작한다.
    """
    fake_pinecone = ModuleType("pinecone")
    fake_pinecone.Pinecone = MagicMock  # type: ignore[attr-defined]

    saved = sys.modules.get("pinecone")
    sys.modules["pinecone"] = fake_pinecone

    # src.db.pinecone_client 모듈을 강제 리로드하여 fake pinecone을 사용하게 한다
    if "src.db.pinecone_client" in sys.modules:
        del sys.modules["src.db.pinecone_client"]

    yield

    # 원복
    if saved is not None:
        sys.modules["pinecone"] = saved
    else:
        sys.modules.pop("pinecone", None)
    sys.modules.pop("src.db.pinecone_client", None)


def _get_fresh_client(api_key: str = "test-key-123"):
    """테스트용 PineconeClient를 fresh import로 생성한다."""
    mod = importlib.import_module("src.db.pinecone_client")
    return mod.PineconeClient(api_key=api_key)


class TestPineconeClientInit:
    """PineconeClient 초기화 테스트."""

    def test_init_with_explicit_key(self):
        client = _get_fresh_client(api_key="explicit-key")
        assert client._api_key == "explicit-key"

    def test_init_with_env_var(self, monkeypatch):
        monkeypatch.setenv("PINECONE_API_KEY", "env-key-456")
        client = _get_fresh_client(api_key="")
        # api_key=""이면 os.getenv fallback이 아니라 빈 문자열 사용
        # 명시적으로 None을 전달해야 env var 폴백
        mod = importlib.import_module("src.db.pinecone_client")
        client2 = mod.PineconeClient()
        assert client2._api_key == "env-key-456"

    def test_init_empty_indexes_cache(self):
        client = _get_fresh_client()
        assert client._indexes == {}


class TestPineconeClientIndexCaching:
    """인덱스 객체 캐싱 동작 테스트."""

    def test_get_index_creates_on_first_call(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        client._pc.Index.return_value = mock_index

        result = client._get_index("expert-knowledge")

        client._pc.Index.assert_called_once_with("expert-knowledge")
        assert result is mock_index

    def test_get_index_caches_on_second_call(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        client._pc.Index.return_value = mock_index

        client._get_index("expert-knowledge")
        client._get_index("expert-knowledge")

        client._pc.Index.assert_called_once_with("expert-knowledge")

    def test_different_indexes_cached_separately(self):
        client = _get_fresh_client()
        mock_idx_a = MagicMock(name="idx_a")
        mock_idx_b = MagicMock(name="idx_b")
        client._pc.Index.side_effect = [mock_idx_a, mock_idx_b]

        result_a = client._get_index("expert-knowledge")
        result_b = client._get_index("mem-podcast-episode")

        assert result_a is mock_idx_a
        assert result_b is mock_idx_b
        assert client._pc.Index.call_count == 2


class TestPineconeClientQuery:
    """query() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_query_with_to_dict(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "matches": [{"id": "v1", "score": 0.95}],
            "namespace": "",
        }
        mock_index.query.return_value = mock_result
        client._pc.Index.return_value = mock_index

        result = await client.query(
            index="expert-knowledge",
            vector=[0.1] * 1024,
            filter={"domain": {"$in": ["psychology"]}},
            top_k=3,
        )

        assert result["matches"][0]["id"] == "v1"
        assert result["matches"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_query_without_to_dict(self):
        """to_dict 메서드가 없는 결과 객체 폴백 테스트."""
        client = _get_fresh_client()
        mock_index = MagicMock()
        raw_result = {"matches": [{"id": "v2", "score": 0.80}]}
        mock_index.query.return_value = raw_result
        client._pc.Index.return_value = mock_index

        result = await client.query(
            index="expert-knowledge",
            vector=[0.1] * 1024,
            filter={},
        )

        assert result["matches"][0]["id"] == "v2"

    @pytest.mark.asyncio
    async def test_query_passes_kwargs(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"matches": []}
        mock_index.query.return_value = mock_result
        client._pc.Index.return_value = mock_index

        await client.query(
            index="expert-knowledge",
            vector=[0.0],
            filter={},
            top_k=10,
            include_metadata=True,
        )

        mock_index.query.assert_called_once_with(
            vector=[0.0],
            filter={},
            top_k=10,
            include_metadata=True,
        )


class TestPineconeClientUpsert:
    """upsert() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_upsert_with_to_dict(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"upserted_count": 2}
        mock_index.upsert.return_value = mock_result
        client._pc.Index.return_value = mock_index

        vectors = [
            {"id": "v1", "values": [0.1, 0.2], "metadata": {"label": "a"}},
            {"id": "v2", "values": [0.3, 0.4], "metadata": {"label": "b"}},
        ]

        result = await client.upsert(
            index="expert-knowledge",
            vectors=vectors,
            namespace="test",
        )

        assert result["upserted_count"] == 2
        mock_index.upsert.assert_called_once_with(
            vectors=vectors,
            namespace="test",
        )

    @pytest.mark.asyncio
    async def test_upsert_default_namespace(self):
        client = _get_fresh_client()
        mock_index = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"upserted_count": 1}
        mock_index.upsert.return_value = mock_result
        client._pc.Index.return_value = mock_index

        await client.upsert(
            index="expert-knowledge",
            vectors=[{"id": "v1", "values": [0.1]}],
        )

        mock_index.upsert.assert_called_once_with(
            vectors=[{"id": "v1", "values": [0.1]}],
            namespace="",
        )


class TestPineconeClientClose:
    """close() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_close_clears_cache(self):
        client = _get_fresh_client()
        client._pc.Index.return_value = MagicMock()

        client._get_index("expert-knowledge")
        assert len(client._indexes) == 1

        await client.close()
        assert client._indexes == {}

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        mod = importlib.import_module("src.db.pinecone_client")
        async with mod.PineconeClient(api_key="test") as client:
            assert client._indexes == {}
        assert client._indexes == {}


class TestPineconeClientIsBaseVectorClient:
    """BaseVectorClient 인터페이스 준수 테스트."""

    def test_implements_interface(self):
        from src.db.base import BaseVectorClient

        client = _get_fresh_client()
        assert isinstance(client, BaseVectorClient)

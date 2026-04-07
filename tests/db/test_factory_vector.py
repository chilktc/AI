"""create_vector_client 팩토리 함수 테스트.

STORAGE_MODE에 따라 PineconeClient 또는 VectorProxyClient를 반환하는지 검증한다.
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_pinecone_module():
    """pinecone 패키지를 sys.modules에 가짜 모듈로 주입한다."""
    fake_pinecone = ModuleType("pinecone")
    fake_pinecone.Pinecone = MagicMock  # type: ignore[attr-defined]

    saved = sys.modules.get("pinecone")
    sys.modules["pinecone"] = fake_pinecone

    if "src.db.pinecone_client" in sys.modules:
        del sys.modules["src.db.pinecone_client"]

    yield

    if saved is not None:
        sys.modules["pinecone"] = saved
    else:
        sys.modules.pop("pinecone", None)
    sys.modules.pop("src.db.pinecone_client", None)


class TestCreateVectorClient:
    """create_vector_client 팩토리 테스트."""

    def test_local_mode_returns_pinecone_client(self):
        with patch("src.db.factory.get_settings") as mock_settings:
            mock_settings.return_value.storage_mode = "local"

            from src.db.factory import create_vector_client

            client = create_vector_client()

            mod = importlib.import_module("src.db.pinecone_client")
            assert isinstance(client, mod.PineconeClient)

    def test_hybrid_mode_returns_pinecone_client(self):
        with patch("src.db.factory.get_settings") as mock_settings:
            mock_settings.return_value.storage_mode = "hybrid"

            from src.db.factory import create_vector_client

            client = create_vector_client()

            mod = importlib.import_module("src.db.pinecone_client")
            assert isinstance(client, mod.PineconeClient)

    def test_proxy_mode_returns_proxy_client(self):
        with (
            patch("src.db.factory.get_settings") as mock_settings,
            patch("src.db.api_proxy.VectorProxyClient.__init__", return_value=None),
            patch("src.api.client.BackendClient.__init__", return_value=None),
        ):
            mock_settings.return_value.storage_mode = "proxy"

            from src.db.factory import create_vector_client

            client = create_vector_client()

            from src.db.api_proxy import VectorProxyClient

            assert isinstance(client, VectorProxyClient)

    def test_returns_base_vector_client_interface(self):
        with patch("src.db.factory.get_settings") as mock_settings:
            mock_settings.return_value.storage_mode = "local"

            from src.db.base import BaseVectorClient
            from src.db.factory import create_vector_client

            client = create_vector_client()
            assert isinstance(client, BaseVectorClient)

"""Pinecone dev/scripts 헬퍼 함수 테스트.

validate_pinecone_env.py, create_pinecone_indexes.py,
test_pinecone_connection.py의 핵심 로직을 검증한다.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── validate_pinecone_env ───────────────────────────────────────────


class TestValidatePineconeEnv:
    """환경변수 검증 스크립트 테스트."""

    def test_missing_api_key_exits_1(self, monkeypatch):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)
        monkeypatch.setenv("STORAGE_MODE", "local")

        from dev.scripts.validate_pinecone_env import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_valid_env_passes(self, monkeypatch, capsys):
        monkeypatch.setenv("PINECONE_API_KEY", "pc-test-key-123456")
        monkeypatch.setenv("STORAGE_MODE", "local")

        from dev.scripts.validate_pinecone_env import main

        main()
        captured = capsys.readouterr()
        assert "검증 통과" in captured.out

    def test_invalid_storage_mode_exits_1(self, monkeypatch):
        monkeypatch.setenv("PINECONE_API_KEY", "pc-test-key-123456")
        monkeypatch.setenv("STORAGE_MODE", "invalid_mode")

        from dev.scripts.validate_pinecone_env import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_proxy_mode_shows_warning(self, monkeypatch, capsys):
        monkeypatch.setenv("PINECONE_API_KEY", "pc-test-key-123456")
        monkeypatch.setenv("STORAGE_MODE", "proxy")

        from dev.scripts.validate_pinecone_env import main

        main()
        captured = capsys.readouterr()
        assert "WARN" in captured.out
        assert "검증 통과" in captured.out

    def test_masked_key_output(self, monkeypatch, capsys):
        monkeypatch.setenv("PINECONE_API_KEY", "pc-secret-key-12345")
        monkeypatch.setenv("STORAGE_MODE", "local")

        from dev.scripts.validate_pinecone_env import main

        main()
        captured = capsys.readouterr()
        assert "pc-sec****" in captured.out
        assert "pc-secret-key-12345" not in captured.out


# ── test_pinecone_connection 헬퍼 함수 ──────────────────────────────


class TestPineconeConnectionHelpers:
    """연결 헬스체크 헬퍼 함수 테스트."""

    def test_api_connection_success(self, capsys):
        from dev.scripts.test_pinecone_connection import test_api_connection

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [
            {"name": "expert-knowledge"},
            {"name": "mem-podcast-episode"},
        ]

        result = test_api_connection(mock_pc)

        assert result is True
        captured = capsys.readouterr()
        assert "[OK]" in captured.out

    def test_api_connection_failure(self, capsys):
        from dev.scripts.test_pinecone_connection import test_api_connection

        mock_pc = MagicMock()
        mock_pc.list_indexes.side_effect = Exception("Connection refused")

        result = test_api_connection(mock_pc)

        assert result is False
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out

    def test_index_exists_all_present(self, capsys):
        from dev.scripts.test_pinecone_connection import test_index_exists

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [
            {"name": "expert-knowledge"},
            {"name": "mem-podcast-episode"},
        ]
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = {
            "total_vector_count": 100,
            "dimension": 1024,
        }
        mock_pc.Index.return_value = mock_index

        result = test_index_exists(mock_pc, ["expert-knowledge", "mem-podcast-episode"])

        assert result is True

    def test_index_exists_missing(self, capsys):
        from dev.scripts.test_pinecone_connection import test_index_exists

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [{"name": "expert-knowledge"}]

        result = test_index_exists(mock_pc, ["expert-knowledge", "mem-podcast-episode"])

        assert result is False
        captured = capsys.readouterr()
        assert "mem-podcast-episode" in captured.out
        assert "인덱스 없음" in captured.out

    def test_dummy_query_success(self, capsys):
        from dev.scripts.test_pinecone_connection import test_dummy_query

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [{"name": "expert-knowledge"}]
        mock_index = MagicMock()
        mock_index.query.return_value = {"matches": []}
        mock_pc.Index.return_value = mock_index

        result = test_dummy_query(mock_pc, "expert-knowledge", dimension=1024)

        assert result is True
        mock_index.query.assert_called_once()

    def test_dummy_query_skip_missing_index(self, capsys):
        from dev.scripts.test_pinecone_connection import test_dummy_query

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = []

        result = test_dummy_query(mock_pc, "expert-knowledge")

        assert result is True
        captured = capsys.readouterr()
        assert "[SKIP]" in captured.out

    def test_dummy_query_failure(self, capsys):
        from dev.scripts.test_pinecone_connection import test_dummy_query

        mock_pc = MagicMock()
        mock_pc.list_indexes.return_value = [{"name": "expert-knowledge"}]
        mock_index = MagicMock()
        mock_index.query.side_effect = Exception("Timeout")
        mock_pc.Index.return_value = mock_index

        result = test_dummy_query(mock_pc, "expert-knowledge")

        assert result is False
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out


# ── create_pinecone_indexes 설정값 ──────────────────────────────────


class TestCreatePineconeIndexesConfig:
    """인덱스 생성 스크립트 설정값 테스트."""

    def test_index_definitions(self):
        from dev.scripts.create_pinecone_indexes import CLOUD, INDEXES, REGION

        assert CLOUD == "aws"
        assert REGION == "us-east-1"
        assert len(INDEXES) == 2

        names = {idx["name"] for idx in INDEXES}
        assert names == {"expert-knowledge", "mem-podcast-episode"}

        for idx in INDEXES:
            assert idx["dimension"] == 1024
            assert idx["metric"] == "cosine"

    def test_missing_api_key_exits_1(self, monkeypatch):
        monkeypatch.delenv("PINECONE_API_KEY", raising=False)

        import sys
        from unittest.mock import patch as p

        with p.object(sys, "argv", ["create_pinecone_indexes.py"]):
            from dev.scripts.create_pinecone_indexes import main

            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

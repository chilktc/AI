"""
AgentDataPublisher 단위 테스트.

BackendClient를 mock 주입하여 실제 HTTP 호출 없이
publish() 메서드의 SaveRequest 생성, 성공/실패 분기, 로깅을 검증.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.api.contracts import SaveRequest
from src.api.publisher import AgentDataPublisher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_backend_client() -> AsyncMock:
    """BackendClient mock — save() 호출을 기록한다."""
    client = AsyncMock()
    client.save = AsyncMock(return_value=None)
    return client


@pytest.fixture
def publisher(mock_backend_client: AsyncMock) -> AgentDataPublisher:
    """mock BackendClient가 주입된 AgentDataPublisher."""
    return AgentDataPublisher(client=mock_backend_client)


# ---------------------------------------------------------------------------
# Tests: publish() 성공
# ---------------------------------------------------------------------------

class TestPublishSuccess:
    """publish() 정상 동작 테스트."""

    @pytest.mark.asyncio
    async def test_publish_calls_save_with_correct_args(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """BackendClient.save()에 올바른 resource와 SaveRequest가 전달되는지 확인."""
        await publisher.publish(
            resource="emotion_logs",
            data={"primary_emotion": "anxiety", "intensity": 0.7},
            user_id="user_456",
            session_id="sess_def",
        )

        mock_backend_client.save.assert_awaited_once()
        call_args = mock_backend_client.save.call_args

        # 첫 번째 인자: resource
        assert call_args[0][0] == "emotion_logs"

        # 두 번째 인자: SaveRequest
        request: SaveRequest = call_args[0][1]
        assert isinstance(request, SaveRequest)
        assert request.user_id == "user_456"
        assert request.session_id == "sess_def"
        assert request.type == "emotion_logs"
        assert request.data["primary_emotion"] == "anxiety"
        assert request.data["intensity"] == 0.7

    @pytest.mark.parametrize(
        "data_type, expected_type",
        [
            (None, "emotion_logs"),
            ("emotion_log", "emotion_log"),
        ],
        ids=["default_type", "custom_type"],
    )
    @pytest.mark.asyncio
    async def test_publish_data_type(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
        data_type: str | None,
        expected_type: str,
    ) -> None:
        """data_type 지정 여부에 따라 SaveRequest.type이 올바르게 설정된다."""
        kwargs: dict[str, Any] = dict(
            resource="emotion_logs",
            data={"mode": "podcast"},
            user_id="user_123",
            session_id="sess_abc",
        )
        if data_type is not None:
            kwargs["data_type"] = data_type

        result = await publisher.publish(**kwargs)
        assert result is True

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert request.type == expected_type

    @pytest.mark.parametrize(
        "trace_id, expect_in_data",
        [
            ("trace_xyz789", True),
            (None, False),
        ],
        ids=["with_trace_id", "without_trace_id"],
    )
    @pytest.mark.asyncio
    async def test_publish_trace_id(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
        trace_id: str | None,
        expect_in_data: bool,
    ) -> None:
        """trace_id 유무에 따라 payload 포함 여부가 결정된다."""
        kwargs: dict[str, Any] = dict(
            resource="content_analysis",
            data={"main_theme": "불안"},
            user_id="user_123",
            session_id="sess_abc",
        )
        if trace_id is not None:
            kwargs["trace_id"] = trace_id

        await publisher.publish(**kwargs)

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        if expect_in_data:
            assert request.data["trace_id"] == trace_id
        else:
            assert "trace_id" not in request.data

    @pytest.mark.asyncio
    async def test_publish_timestamp_and_immutability(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """UTC 타임스탬프 포함 + 원본 data dict 불변성."""
        original = {"primary_emotion": "calm"}

        await publisher.publish(
            resource="emotion_logs",
            data=original,
            user_id="user_123",
            session_id="sess_abc",
            trace_id="trace_001",
        )

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert request.timestamp.tzinfo is not None
        assert "trace_id" not in original  # 원본 불변


# ---------------------------------------------------------------------------
# Tests: publish() 실패
# ---------------------------------------------------------------------------

class TestPublishFailure:
    """publish() 실패 시 예외 미전파 + False 반환 테스트."""

    @pytest.mark.parametrize(
        "error",
        [RuntimeError("HTTP 500"), ConnectionError("네트워크 오류")],
        ids=["runtime_error", "connection_error"],
    )
    @pytest.mark.asyncio
    async def test_publish_returns_false_and_suppresses_exception(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
        error: Exception,
    ) -> None:
        """BackendClient.save() 예외 시 False 반환, 예외 미전파."""
        mock_backend_client.save.side_effect = error

        result = await publisher.publish(
            resource="emotion_logs",
            data={"intensity": 0.5},
            user_id="user_123",
            session_id="sess_abc",
        )

        assert result is False


# ---------------------------------------------------------------------------
# Tests: _get_client() lazy import
# ---------------------------------------------------------------------------

class TestGetClient:
    """_get_client() lazy import 테스트."""

    @pytest.mark.asyncio
    async def test_uses_injected_client(
        self, mock_backend_client: AsyncMock,
    ) -> None:
        """생성자에서 주입한 client를 사용한다."""
        pub = AgentDataPublisher(client=mock_backend_client)

        await pub.publish(
            resource="test",
            data={},
            user_id="u",
            session_id="s",
        )

        mock_backend_client.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lazy_import_when_client_none(self) -> None:
        """client=None이면 src.api.main.backend_client를 lazy import한다."""
        mock_client = AsyncMock()
        mock_client.save = AsyncMock(return_value=None)

        pub = AgentDataPublisher(client=None)

        with patch("src.api.main.backend_client", mock_client):
            result = await pub.publish(
                resource="test",
                data={"key": "value"},
                user_id="u",
                session_id="s",
            )

        assert result is True
        mock_client.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_backend_not_initialized(self) -> None:
        """backend_client가 None이면 RuntimeError → False 반환."""
        pub = AgentDataPublisher(client=None)

        with patch("src.api.main.backend_client", None):
            result = await pub.publish(
                resource="test",
                data={},
                user_id="u",
                session_id="s",
            )

        assert result is False

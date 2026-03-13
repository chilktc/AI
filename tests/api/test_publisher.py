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
    async def test_publish_returns_true_on_success(
        self, publisher: AgentDataPublisher,
    ) -> None:
        """정상 publish 시 True 반환."""
        result = await publisher.publish(
            resource="emotion_logs",
            data={"primary_emotion": "calm", "intensity": 0.6},
            user_id="user_123",
            session_id="sess_abc",
        )

        assert result is True

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

    @pytest.mark.asyncio
    async def test_publish_uses_custom_data_type(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """data_type이 지정되면 SaveRequest.type에 해당 값이 사용된다."""
        await publisher.publish(
            resource="emotion_logs",
            data={"mode": "podcast"},
            user_id="user_123",
            session_id="sess_abc",
            data_type="emotion_log",
        )

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert request.type == "emotion_log"

    @pytest.mark.asyncio
    async def test_publish_includes_trace_id_in_payload(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """trace_id가 지정되면 data payload에 포함된다."""
        await publisher.publish(
            resource="content_analysis",
            data={"main_theme": "불안"},
            user_id="user_123",
            session_id="sess_abc",
            trace_id="trace_xyz789",
        )

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert request.data["trace_id"] == "trace_xyz789"
        assert request.data["main_theme"] == "불안"

    @pytest.mark.asyncio
    async def test_publish_without_trace_id_excludes_it(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """trace_id가 None이면 payload에 포함되지 않는다."""
        await publisher.publish(
            resource="emotion_logs",
            data={"intensity": 0.5},
            user_id="user_123",
            session_id="sess_abc",
        )

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert "trace_id" not in request.data

    @pytest.mark.asyncio
    async def test_publish_has_utc_timestamp(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """SaveRequest.timestamp가 UTC timezone 정보를 포함한다."""
        await publisher.publish(
            resource="emotion_logs",
            data={},
            user_id="user_123",
            session_id="sess_abc",
        )

        request: SaveRequest = mock_backend_client.save.call_args[0][1]
        assert request.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_publish_does_not_mutate_original_data(
        self,
        publisher: AgentDataPublisher,
    ) -> None:
        """원본 data dict가 변경되지 않는다 (방어적 복사 확인)."""
        original = {"primary_emotion": "calm"}

        await publisher.publish(
            resource="emotion_logs",
            data=original,
            user_id="user_123",
            session_id="sess_abc",
            trace_id="trace_001",
        )

        # trace_id가 원본에 추가되지 않아야 함
        assert "trace_id" not in original


# ---------------------------------------------------------------------------
# Tests: publish() 실패
# ---------------------------------------------------------------------------

class TestPublishFailure:
    """publish() 실패 시 예외 미전파 + False 반환 테스트."""

    @pytest.mark.asyncio
    async def test_publish_returns_false_on_save_error(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """BackendClient.save()가 예외를 발생시키면 False 반환."""
        mock_backend_client.save.side_effect = RuntimeError("HTTP 500")

        result = await publisher.publish(
            resource="emotion_logs",
            data={"intensity": 0.5},
            user_id="user_123",
            session_id="sess_abc",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_publish_does_not_propagate_exception(
        self,
        publisher: AgentDataPublisher,
        mock_backend_client: AsyncMock,
    ) -> None:
        """save() 예외가 publish() 바깥으로 전파되지 않는다."""
        mock_backend_client.save.side_effect = ConnectionError("네트워크 오류")

        # 예외가 발생하지 않아야 함
        result = await publisher.publish(
            resource="emotion_logs",
            data={},
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

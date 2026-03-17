"""
BackendClient 단위 테스트.

httpx.AsyncClient를 mock하여 실제 HTTP 호출 없이
save/load 메서드의 요청 직렬화, 응답 파싱, 에러 핸들링을 검증.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.api.contracts import LoadResponse, SaveRequest, SaveResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_httpx_client():
    """httpx.AsyncClient를 mock한 객체."""
    client = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def backend_client(mock_httpx_client):
    """BackendClient 인스턴스 (httpx 클라이언트를 mock으로 교체)."""
    with patch("src.api.client.httpx.AsyncClient", return_value=mock_httpx_client):
        from src.api.client import BackendClient
        client = BackendClient(base_url="http://test-backend:8080/api/v1")
        # 내부 _client를 mock으로 직접 교체
        client._client = mock_httpx_client
        return client


@pytest.fixture
def valid_save_request() -> SaveRequest:
    """유효한 SaveRequest fixture."""
    return SaveRequest(
        user_id="user_123",
        session_id="sess_abc123",
        type="conversation",
        data={"turn": 1, "message": "안녕하세요"},
        timestamp=datetime.now(timezone.utc),
    )


def _make_response(status_code: int, json_data: dict[str, Any]) -> MagicMock:
    """httpx.Response mock 생성 헬퍼."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    return response


# ---------------------------------------------------------------------------
# Tests: save()
# ---------------------------------------------------------------------------

class TestBackendClientSave:
    """BackendClient.save() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_save_success_and_serialization(
        self, backend_client, mock_httpx_client, valid_save_request,
    ) -> None:
        """정상적인 save 요청 시 SaveResponse 반환 + 올바른 직렬화 확인."""
        mock_httpx_client.post = AsyncMock(
            return_value=_make_response(200, {
                "success": True,
                "id": "saved_001",
                "message": "saved",
            }),
        )

        result = await backend_client.save("conversations", valid_save_request)

        # SaveResponse 검증
        assert isinstance(result, SaveResponse)
        assert result.success is True
        assert result.id == "saved_001"

        # 직렬화 검증
        call_args = mock_httpx_client.post.call_args
        url = call_args[0][0]
        json_body = call_args[1]["json"]

        assert url == "http://test-backend:8080/api/v1/conversations"
        assert json_body["user_id"] == "user_123"
        assert json_body["session_id"] == "sess_abc123"
        assert json_body["type"] == "conversation"
        assert "data" in json_body
        assert "timestamp" in json_body

    @pytest.mark.asyncio
    async def test_save_http_error_raises(
        self, backend_client, mock_httpx_client, valid_save_request,
    ) -> None:
        """500 응답 시 httpx.HTTPStatusError 발생."""
        mock_httpx_client.post = AsyncMock(
            return_value=_make_response(500, {
                "success": False,
                "error": {"code": "SERVER_ERROR", "message": "내부 오류"},
            }),
        )

        with pytest.raises(httpx.HTTPStatusError):
            await backend_client.save("learning", valid_save_request)


# ---------------------------------------------------------------------------
# Tests: load()
# ---------------------------------------------------------------------------

class TestBackendClientLoad:
    """BackendClient.load() 메서드 테스트."""

    @pytest.mark.parametrize(
        "resource, kwargs, response_data, check",
        [
            (
                "learning",
                {"user_id": "user_123"},
                {"success": True, "data": [{"id": "1", "content": "데이터"}], "total": 1, "page": 1},
                lambda r, _: (
                    isinstance(r, LoadResponse)
                    and r.success is True
                    and len(r.data) == 1
                    and r.total == 1
                ),
            ),
            (
                "conversations",
                {"user_id": "user_123", "type": "conversation", "limit": 10},
                {"success": True, "data": [], "total": 0, "page": 1},
                lambda r, mock: (
                    r.data == []
                    and r.total == 0
                    and mock.get.call_args[1]["params"]["type"] == "conversation"
                    and mock.get.call_args[1]["params"]["limit"] == 10
                ),
            ),
        ],
        ids=["success_with_data", "empty_with_query_params"],
    )
    @pytest.mark.asyncio
    async def test_load(
        self, backend_client, mock_httpx_client,
        resource, kwargs, response_data, check,
    ) -> None:
        """load 성공 + 쿼리 파라미터 전달 + 빈 결과 검증."""
        mock_httpx_client.get = AsyncMock(
            return_value=_make_response(200, response_data),
        )

        result = await backend_client.load(resource, **kwargs)

        assert check(result, mock_httpx_client)


# ---------------------------------------------------------------------------
# Tests: 리소스 관리
# ---------------------------------------------------------------------------

class TestBackendClientLifecycle:
    """BackendClient 리소스 관리 테스트."""

    @pytest.mark.asyncio
    async def test_lifecycle(
        self, backend_client, mock_httpx_client,
    ) -> None:
        """base_url 설정 확인 + close() 호출 시 리소스 정리 검증."""
        assert backend_client._base_url == "http://test-backend:8080/api/v1"

        await backend_client.close()
        mock_httpx_client.aclose.assert_awaited_once()

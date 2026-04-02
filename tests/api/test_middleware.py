"""
RequestLoggingMiddleware 단위 테스트.

HTTP 요청 로깅, X-Request-ID 관리, 제외 경로 동작을 검증.
"""

from __future__ import annotations


class TestRequestLoggingMiddleware:
    """RequestLoggingMiddleware 동작 검증."""

    def test_preserves_client_request_id(self, test_client) -> None:
        """클라이언트가 전달한 X-Request-ID를 재사용."""
        custom_id = "my-custom-id"
        response = test_client.get(
            "/health",
            headers={"X-Request-ID": custom_id},
        )

        assert response.headers["x-request-id"] == custom_id

    def test_generates_request_id_if_missing(self, test_client) -> None:
        """클라이언트가 X-Request-ID를 보내지 않으면 서버가 자동 생성."""
        response = test_client.get("/health")

        request_id = response.headers.get("x-request-id")
        assert request_id is not None
        assert len(request_id) > 0

    def test_non_excluded_path_gets_request_id(self, test_client) -> None:
        """일반 경로도 X-Request-ID 헤더를 받아야 한다."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"user_id": "test_user", "mode": "podcast"},
        )

        assert "x-request-id" in response.headers

"""
Sessions 엔드포인트 테스트.

POST /api/v1/sessions (세션 생성) 및
POST /api/v1/sessions/{session_id}/close (세션 종료) 검증.
"""

from __future__ import annotations


class TestCreateSession:
    """POST /api/v1/sessions 엔드포인트 테스트."""

    def test_create_session_success(self, test_client) -> None:
        """유효한 요청으로 세션 생성 시 200과 세션 ID 반환."""
        response = test_client.post(
            "/api/v1/sessions",
            json={
                "user_id": "test_user_001",
                "mode": "podcast",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"].startswith("sess_")
        assert data["mode"] == "podcast"

    def test_create_session_default_mode(self, test_client) -> None:
        """mode 미지정 시 기본값 conversation."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"user_id": "test_user_002"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "conversation"

    def test_create_session_has_created_at(self, test_client) -> None:
        """응답에 created_at 필드가 포함."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"user_id": "test_user_003", "mode": "conversation"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "created_at" in data

    def test_create_session_tracing_ids(self, test_client) -> None:
        """응답에 tracing 필드가 포함되고 자동 생성된 ID를 가짐."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"user_id": "test_user_004", "mode": "podcast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "tracing" in data
        tracing = data["tracing"]
        assert tracing["request_id"].startswith("req_")
        assert tracing["trace_id"].startswith("trace_")

    def test_create_session_validation_error(self, test_client) -> None:
        """필수 필드(user_id) 누락 시 422 에러."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"mode": "podcast"},  # user_id 없음
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_session_invalid_mode(self, test_client) -> None:
        """유효하지 않은 mode 값 시 422 에러."""
        response = test_client.post(
            "/api/v1/sessions",
            json={"user_id": "test_user_005", "mode": "invalid_mode"},
        )

        assert response.status_code == 422


class TestCloseSession:
    """POST /api/v1/sessions/{session_id}/close 엔드포인트 테스트."""

    def test_close_session_success(self, test_client) -> None:
        """유효한 세션 종료 요청 시 200과 success=True."""
        response = test_client.post(
            "/api/v1/sessions/sess_abc123/close",
            json={
                "user_id": "test_user_001",
                "session_id": "sess_abc123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_close_session_with_feedback(self, test_client) -> None:
        """피드백 포함 세션 종료."""
        response = test_client.post(
            "/api/v1/sessions/sess_abc123/close",
            json={
                "user_id": "test_user_001",
                "session_id": "sess_abc123",
                "feedback": {
                    "rating": 4,
                    "helpful": True,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

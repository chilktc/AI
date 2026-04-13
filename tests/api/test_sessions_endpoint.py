"""
Sessions 엔드포인트 테스트.

POST /api/sessions (세션 생성) 및
POST /api/sessions/{session_id}/close (세션 종료) 검증.
"""

from __future__ import annotations

import pytest


class TestCreateSession:
    """POST /api/sessions 엔드포인트 테스트."""

    @pytest.mark.parametrize(
        "mode_input, expected_mode",
        [
            ("podcast", "podcast"),
            (None, "podcast"),
        ],
        ids=["explicit_podcast", "default_podcast"],
    )
    def test_create_session_mode(
        self,
        test_client,
        mode_input,
        expected_mode,
    ) -> None:
        """mode 지정/미지정 시 올바른 모드로 세션 생성 + 응답 필드 검증."""
        body = {"user_id": "test_user_001"}
        if mode_input is not None:
            body["mode"] = mode_input

        response = test_client.post("/api/sessions", json=body)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"].startswith("sess_")
        assert data["mode"] == expected_mode
        # 응답 필드 검증
        assert "created_at" in data
        assert "tracing" in data
        assert data["tracing"]["request_id"].startswith("req_")
        assert data["tracing"]["trace_id"].startswith("trace_")

    @pytest.mark.parametrize(
        "body, expected_status",
        [
            ({"mode": "podcast"}, 422),  # user_id 누락
            ({"user_id": "u", "mode": "invalid"}, 422),  # 잘못된 mode
        ],
        ids=["missing_user_id", "invalid_mode"],
    )
    def test_create_session_validation_error(
        self,
        test_client,
        body,
        expected_status,
    ) -> None:
        """필수 필드 누락/잘못된 값 시 422 에러."""
        response = test_client.post("/api/sessions", json=body)
        assert response.status_code == expected_status


class TestCloseSession:
    """POST /api/sessions/{session_id}/close 엔드포인트 테스트."""

    @pytest.mark.parametrize(
        "feedback",
        [None, {"rating": 4, "helpful": True}],
        ids=["without_feedback", "with_feedback"],
    )
    def test_close_session(self, test_client, feedback) -> None:
        """세션 종료 요청 (피드백 유무 무관) 시 200 + success=True."""
        body = {
            "user_id": "test_user_001",
            "session_id": "sess_abc123",
        }
        if feedback is not None:
            body["feedback"] = feedback

        response = test_client.post(
            "/api/sessions/sess_abc123/close",
            json=body,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

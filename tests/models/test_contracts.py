"""백엔드 API 요청/응답 스키마 단위 테스트."""

from datetime import datetime, timezone

from src.api.contracts import (
    ErrorDetail,
    ErrorResponse,
    LoadResponse,
    SaveRequest,
    SaveResponse,
)


class TestSaveRequest:
    def test_creation(self):
        req = SaveRequest(
            user_id="user_001",
            session_id="sess_001",
            type="podcast_episode",
            data={"title": "Test Episode"},
            timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        assert req.user_id == "user_001"
        assert req.type == "podcast_episode"
        assert req.data["title"] == "Test Episode"

    def test_serialization(self):
        req = SaveRequest(
            user_id="u1",
            session_id="s1",
            type="emotion_log",
            data={"valence": 0.5},
            timestamp=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        d = req.model_dump()
        assert d["user_id"] == "u1"
        assert d["type"] == "emotion_log"


class TestSaveResponse:
    def test_success(self):
        resp = SaveResponse(success=True, id="res_001", message="saved")
        assert resp.success is True
        assert resp.id == "res_001"

    def test_defaults(self):
        resp = SaveResponse(success=False)
        assert resp.id is None
        assert resp.message is None


class TestLoadResponse:
    def test_with_data(self):
        resp = LoadResponse(
            success=True,
            data=[{"id": "1"}, {"id": "2"}],
            total=10,
            page=1,
        )
        assert len(resp.data) == 2
        assert resp.total == 10

    def test_defaults(self):
        resp = LoadResponse(success=True)
        assert resp.data == []
        assert resp.total == 0
        assert resp.page == 1


class TestErrorDetail:
    def test_creation(self):
        err = ErrorDetail(code="NOT_FOUND", message="Resource not found")
        assert err.code == "NOT_FOUND"


class TestErrorResponse:
    def test_always_false(self):
        resp = ErrorResponse(error=ErrorDetail(code="SERVER_ERROR", message="fail"))
        assert resp.success is False

"""POST /api/stories/select 엔드포인트 테스트."""

from __future__ import annotations


class TestStoriesSelectEndpoint:
    """POST /api/stories/select 엔드포인트 테스트."""

    def test_valid_request_returns_200(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """올바른 페이로드 → 200 + success:true."""
        payload = {
            "session_id": "sess_test_001",
            "keywords": ["직장", "갈등"],
            "title": "나의 이야기",
            "description": "직장 내 갈등 상황",
        }
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 200
        assert response.json() == {"success": True}

    def test_missing_session_id_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """session_id 누락 → 422."""
        payload = {"keywords": ["직장"], "title": "T", "description": "D"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_missing_title_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """title 누락 → 422."""
        payload = {"session_id": "sess_001", "keywords": [], "description": "D"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_missing_description_returns_422(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """description 누락 → 422."""
        payload = {"session_id": "sess_001", "keywords": [], "title": "T"}
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 422

    def test_empty_keywords_is_valid(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """keywords가 빈 리스트여도 유효하다."""
        payload = {
            "session_id": "sess_002",
            "keywords": [],
            "title": "T",
            "description": "D",
        }
        response = test_client.post("/api/stories/select", json=payload)
        assert response.status_code == 200

    def test_stores_data_in_store(self, test_client) -> None:  # type: ignore[no-untyped-def]
        """수신 데이터가 StoriesStore에 저장되고 Event가 set된다."""
        from src.api.stories_store import stories_store

        session_id = "sess_store_check_001"
        payload = {
            "session_id": session_id,
            "keywords": ["감정"],
            "title": "감정 이야기",
            "description": "나의 감정",
        }
        test_client.post("/api/stories/select", json=payload)

        stored = stories_store._store.get(session_id)
        assert stored is not None
        assert stored["data"]["keywords"] == ["감정"]
        assert stored["event"].is_set()

        # 정리
        stories_store.delete_session(session_id)

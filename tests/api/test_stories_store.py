"""StoriesStore asyncio.Event 기반 단위 테스트."""

from __future__ import annotations

import asyncio

import pytest

from src.api.stories_store import StoriesStore


@pytest.fixture
def store() -> StoriesStore:
    return StoriesStore()


class TestSetStories:
    def test_set_stories_stores_data(self, store: StoriesStore) -> None:
        """set_stories 호출 후 데이터가 저장된다."""
        data = {"keywords": ["직장"], "title": "T", "description": "D"}
        store.set_stories("sess_001", data)
        assert store._store["sess_001"]["data"] == data

    def test_set_stories_sets_event(self, store: StoriesStore) -> None:
        """set_stories 호출 후 Event가 set 상태가 된다."""
        store.set_stories("sess_002", {"keywords": [], "title": "", "description": ""})
        assert store._store["sess_002"]["event"].is_set()


class TestWaitForStories:
    async def test_wait_returns_data_when_already_set(self, store: StoriesStore) -> None:
        """데이터가 이미 존재하면 즉시 반환한다."""
        data = {"keywords": ["감정"], "title": "제목", "description": "설명"}
        store.set_stories("sess_003", data)
        result = await store.wait_for_stories("sess_003", timeout=1.0)
        assert result == data

    async def test_wait_returns_data_when_set_concurrently(self, store: StoriesStore) -> None:
        """대기 중에 데이터가 도착하면 반환한다."""
        data = {"keywords": ["스트레스"], "title": "제목2", "description": "설명2"}

        async def delayed_set() -> None:
            await asyncio.sleep(0.05)
            store.set_stories("sess_004", data)

        asyncio.create_task(delayed_set())
        result = await store.wait_for_stories("sess_004", timeout=2.0)
        assert result == data

    async def test_wait_returns_none_on_timeout(self, store: StoriesStore) -> None:
        """타임아웃 초과 시 None을 반환한다."""
        result = await store.wait_for_stories("sess_nonexistent", timeout=0.1)
        assert result is None


class TestDeleteSession:
    def test_delete_removes_entry(self, store: StoriesStore) -> None:
        """delete_session 후 해당 세션이 store에서 제거된다."""
        store.set_stories("sess_005", {"keywords": [], "title": "", "description": ""})
        store.delete_session("sess_005")
        assert "sess_005" not in store._store

    def test_delete_nonexistent_session_is_safe(self, store: StoriesStore) -> None:
        """존재하지 않는 세션 삭제는 에러 없이 무시된다."""
        store.delete_session("nonexistent")  # 예외 없이 통과해야 함

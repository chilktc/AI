"""
Stories 수신 인프라 — asyncio.Event 기반 세션별 임시 저장소.

백엔드가 POST /api/stories/select로 stories 데이터를 전송하면
set_stories()가 Event를 set하고, wait_for_stories()가 해제를 기다린다.

get-or-create 패턴으로 set_stories와 wait_for_stories의 호출 순서에 무관하게 동작한다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.utils.logger import get_agent_logger

logger = get_agent_logger("stories_store")


class StoriesStore:
    """
    세션별 asyncio.Event를 관리하는 Stories 임시 저장소.

    FastAPI 앱과 생명주기를 공유하는 모듈 레벨 싱글톤(`stories_store`)으로 사용한다.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def _get_or_create(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._store:
            self._store[session_id] = {"event": asyncio.Event(), "data": None}
        return self._store[session_id]

    def set_stories(self, session_id: str, data: dict[str, Any]) -> None:
        """Stories 데이터를 저장하고 대기 중인 wait_for_stories를 깨운다."""
        entry = self._get_or_create(session_id)
        entry["data"] = data
        entry["event"].set()
        logger.info("[StoriesStore] 데이터 수신 완료 — session_id=%s", session_id)

    async def wait_for_stories(self, session_id: str, timeout: float) -> dict[str, Any] | None:
        """
        Stories 데이터 도착을 최대 timeout초 대기한다.

        Returns:
            dict: 데이터가 도착한 경우
            None: 타임아웃 초과
        """
        entry = self._get_or_create(session_id)
        try:
            await asyncio.wait_for(entry["event"].wait(), timeout=timeout)
            return entry["data"]  # type: ignore[no-any-return]
        except asyncio.TimeoutError:
            logger.warning(
                "[StoriesStore] 타임아웃 — session_id=%s, timeout=%.0fs",
                session_id,
                timeout,
            )
            return None

    def delete_session(self, session_id: str) -> None:
        """파이프라인 완료 후 메모리 정리. 존재하지 않는 세션은 무시한다."""
        self._store.pop(session_id, None)


# 모듈 레벨 싱글톤 (FastAPI 앱과 생명주기를 공유)
stories_store = StoriesStore()

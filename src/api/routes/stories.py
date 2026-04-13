"""
Stories 수신 라우터.

백엔드가 POST /api/stories/select로 Stories 데이터를 푸시한다.
수신 즉시 StoriesStore에 저장하고 대기 중인 파이프라인 노드를 깨운다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.stories_store import stories_store

router = APIRouter()


class StoriesSelectRequest(BaseModel):
    """POST /api/stories/select 요청 스키마."""

    session_id: str
    keywords: list[str]
    title: str
    description: str


@router.post("/select")
async def receive_stories(request: StoriesSelectRequest) -> dict[str, Any]:
    """
    Stories 데이터 수신.

    백엔드가 사용자의 Stories 선택 완료 후 호출한다.
    수신 즉시 StoriesStore에 저장하여 TIER 4 대기 노드를 깨운다.
    """
    stories_store.set_stories(
        request.session_id,
        {
            "keywords": request.keywords,
            "title": request.title,
            "description": request.description,
        },
    )
    return {"success": True}

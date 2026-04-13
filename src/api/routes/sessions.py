"""
세션 관리 라우터.

사용자의 상담/팟캐스트 대화 세션을 생성하고 종료한다.
종료 시 Learning Agent를 비동기로 트리거하여 세션 피드백을 학습한다.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.external_schemas import (
    ErrorResponse,
    SessionCloseRequest,
    SessionCreateRequest,
    SessionCreateResponse,
)

# from src.agents.podcast.learning import trigger_learning_agent (비동기 트리거용)

router = APIRouter()

# =========================================================================
# 개인화 맥락 수신 — in-memory 임시 저장소
# =========================================================================
# TODO: 추후 Redis 또는 영속 저장소로 교체
_personalization_context_store: dict[str, dict[str, Any]] = {}


class PersonalizationContextRequest(BaseModel):
    """Personalizer 사전 입력 수신 요청 스키마."""

    session_id: str
    keywords: list[str]
    title: str
    description: str


@router.post(
    "",
    response_model=SessionCreateResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"},
    },
)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """
    세션 생성.

    Backend 서버가 대화나 팟캐스트 모드 진입 시 호출한다.
    신규 세션 ID를 생성하여 반환.
    """

    # 서버에서 고유 세션 ID 생성
    new_session_id = f"sess_{uuid.uuid4().hex[:12]}"

    return SessionCreateResponse(
        session_id=new_session_id,
        mode=request.mode,
        created_at=datetime.now(timezone.utc),
        tracing=request.tracing,
    )


@router.post(
    "/{session_id}/close",
    response_model=dict,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"},
    },
)
async def close_session(session_id: str, request: SessionCloseRequest) -> dict:
    """
    세션 종료.

    대화가 끝났을 때 Backend 서버가 호출.
    비동기로 백그라운드 태스크나 Learning Agent를 트리거하여 세션 로그를 정리/학습할 수 있다.
    """

    # Learning Agent는 팟캐스트 파이프라인 내부(async_post_processing_node)에서 실행됨.
    # 세션 종료 시 별도 트리거는 불필요.

    return {"success": True, "message": f"Session {session_id} closed successfully"}


@router.post(
    "/{session_id}/personalization-context",
    response_model=dict,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"},
    },
)
async def receive_personalization_context(
    session_id: str,
    request: PersonalizationContextRequest,
) -> dict:
    """
    Personalizer 사전 입력 수신 스텁.

    Backend 서버가 Personalizer 실행 전 사용자 맥락 데이터를 AI 서버에 전달한다.
    수신한 데이터를 in-memory store에 session_id 키로 임시 저장한다.

    ⚠️ 엔드포인트 경로 추후 변경 예정 (TBD).
    TODO: 수신 데이터를 ScriptPersonalizerAgent에서 읽어 개인화 로직에 반영 예정.
    """
    _personalization_context_store[session_id] = {
        "session_id": request.session_id,
        "keywords": request.keywords,
        "title": request.title,
        "description": request.description,
    }
    return {"success": True}

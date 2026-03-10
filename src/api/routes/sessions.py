"""
세션 관리 라우터.

사용자의 상담/팟캐스트 대화 세션을 생성하고 종료한다.
종료 시 Learning Agent를 비동기로 트리거하여 세션 피드백을 학습한다.
"""

import uuid
from typing import Literal
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.external_schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionCloseRequest,
    ErrorResponse
)
# from src.agents.shared.learning import trigger_learning_agent (비동기 트리거용)

router = APIRouter()


@router.post(
    "",
    response_model=SessionCreateResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"}
    }
)
async def create_session(request: SessionCreateRequest) -> SessionCreateResponse:
    """
    세션 생성.
    
    프론트엔드가 대화나 팟캐스트 모드 진입 시 호출한다.
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
        500: {"model": ErrorResponse, "description": "서버 에러"}
    }
)
async def close_session(session_id: str, request: SessionCloseRequest) -> dict:
    """
    세션 종료.
    
    대화가 끝났을 때 프론트가 호출.
    비동기로 백그라운드 태스크나 Learning Agent를 트리거하여 세션 로그를 정리/학습할 수 있다.
    """
    
    # TODO: 피드백(request.feedback) 등을 바탕으로 Learning Agent 비동기 트리거 구현
    # asyncio.create_task(trigger_learning_agent(session_id, request.user_id, request.feedback))
    
    return {"success": True, "message": f"Session {session_id} closed successfully"}

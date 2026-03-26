"""
백엔드 API 요청/응답 스키마.

[Protected File] 수정 시 3인 합의 필수.

백엔드 서버와의 통신에 사용하는 데이터 스키마를 정의한다.
API 모델은 변경될 수 있으므로 유연하게 설계한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SaveRequest(BaseModel):
    """데이터 저장 요청 스키마."""

    user_id: str  # 사용자 고유 ID
    session_id: str  # 세션 고유 ID
    type: str  # 데이터 유형 (conversation, emotion_log, memory, visualization, learning 등)
    data: dict[str, Any]  # 저장할 데이터
    timestamp: datetime  # 데이터 생성 시각


class SaveResponse(BaseModel):
    """데이터 저장 응답 스키마."""

    success: bool  # 성공 여부
    id: str | None = None  # 생성된 리소스 ID
    message: str | None = None  # 응답 메시지


class LoadResponse(BaseModel):
    """데이터 조회 응답 스키마."""

    success: bool  # 성공 여부
    data: list[dict[str, Any]] = Field(default_factory=list)  # 조회 결과
    total: int = 0  # 전체 결과 수
    page: int = 1  # 현재 페이지


class ErrorDetail(BaseModel):
    """에러 상세 정보.

    DEPRECATED: main.py 등 API 계층에서는 external_schemas.py의
    ErrorDetail/ErrorResponse를 사용합니다 (trace_id, field 등 확장 필드 포함).
    이 클래스는 하위 호환을 위해 유지하나, 신규 코드에서는 external_schemas 버전을 사용하세요.
    """

    code: str  # 에러 코드 (NOT_FOUND, VALIDATION_ERROR, SERVER_ERROR 등)
    message: str  # 상세 에러 메시지


class ErrorResponse(BaseModel):
    """에러 응답 스키마.

    DEPRECATED: external_schemas.py의 ErrorResponse를 사용하세요.
    """

    success: Literal[False] = False  # 항상 False
    error: ErrorDetail  # 에러 상세

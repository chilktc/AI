"""
에이전트 간 메시지 프로토콜 v2.0.

[Protected File] 수정 시 3인 합의 필수.

통합 메시지 엔벨로프를 Pydantic v2 모델로 정의한다.
모든 에이전트 간 통신은 이 엔벨로프 형식을 따라야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Priority(IntEnum):
    """메시지 우선순위 레벨."""

    CRITICAL = 0  # Safety CRISIS — 즉시 처리
    HIGH = 1  # 일반 파이프라인 메시지
    NORMAL = 2  # 비동기 처리
    LOW = 3  # 학습/텔레메트리 (지연 허용)


class MessageType(str, Enum):
    """에이전트 간 메시지 유형."""

    REQUEST = "request"  # 작업 요청
    RESPONSE = "response"  # 결과 전달
    EVENT = "event"  # 비동기 이벤트 알림
    CANCEL = "cancel"  # CRISIS 시 작업 취소 신호
    ERROR = "error"  # 실패 알림


def _generate_msg_id() -> str:
    """메시지 고유 ID 생성."""
    return f"msg_{uuid.uuid4().hex[:12]}"


def _generate_req_id() -> str:
    """요청 고유 ID 생성."""
    return f"req_{uuid.uuid4().hex[:12]}"


def _generate_corr_id() -> str:
    """상관관계 ID 생성 — 하나의 사용자 입력에서 파생된 전체 메시지 체인을 그룹핑."""
    return f"corr_{uuid.uuid4().hex[:12]}"


def _generate_trace_id() -> str:
    """추적 ID 생성 — 분산 추적용 (디버깅 시 전체 흐름 추적)."""
    return f"trace_{uuid.uuid4().hex[:12]}"


def _now_utc() -> datetime:
    """현재 UTC 시각 반환."""
    return datetime.now(timezone.utc)


class MessageMetadata(BaseModel):
    """메시지 메타데이터 — 세션, 추적, 실행 컨텍스트 정보."""

    session_id: str  # 세션 고유 ID
    correlation_id: str = Field(default_factory=_generate_corr_id)  # 메시지 체인 그룹 ID
    trace_id: str = Field(default_factory=_generate_trace_id)  # 분산 추적 ID
    mode: Literal["podcast"] = "podcast"  # 실행 모드
    interaction_unit: Literal["episode"] = "episode"  # 상호작용 단위
    tier: Optional[int] = None  # TIER 레벨 (0-4, 독립 에이전트는 None)
    priority: Priority = Priority.HIGH  # 메시지 우선순위
    retry_count: int = 0  # 재시도 횟수


class MessageAudit(BaseModel):
    """메시지 감사 정보 — 에이전트 실행 메트릭."""

    agent_version: str = "1.0.0"  # 에이전트 버전
    processing_time_ms: int = 0  # 처리 소요 시간 (밀리초)
    llm_calls: int = 0  # LLM API 호출 횟수
    status: Literal["ok", "error", "partial"] = "ok"  # 처리 상태


class MessageError(BaseModel):
    """에러 정보 — 실패 시 상세 내용."""

    code: str  # 에러 코드 (예: AGENT_TIMEOUT, INVALID_INPUT)
    message: str  # 사람이 읽을 수 있는 에러 메시지
    details: dict[str, Any] = Field(default_factory=dict)  # 추가 에러 상세


class MessageEnvelope(BaseModel):
    """
    통합 메시지 엔벨로프 v2.0.

    모든 에이전트 간 통신의 표준 형식.
    StateGraph 내부에서는 AgentState를 통해 상태를 공유하고,
    독립 에이전트(Memory, Knowledge 등) 호출 시 이 엔벨로프를 사용한다.
    """

    schema_version: str = "agents.protocol.v2"  # 프로토콜 버전
    message_id: str = Field(default_factory=_generate_msg_id)  # 메시지 고유 ID
    request_id: str = Field(default_factory=_generate_req_id)  # 요청 고유 ID
    timestamp: datetime = Field(default_factory=_now_utc)  # 메시지 생성 시각

    sender: str  # 발신 에이전트 이름
    receiver: str  # 수신 에이전트 이름
    message_type: MessageType  # 메시지 유형

    payload: dict[str, Any] = Field(default_factory=dict)  # 요청/응답 데이터
    metadata: MessageMetadata  # 세션/추적 메타데이터
    audit: MessageAudit = Field(default_factory=MessageAudit)  # 실행 메트릭
    errors: list[MessageError] = Field(default_factory=list)  # 에러 목록

# agents/common/protocols.py
"""
에이전트 간 메시지 프로토콜 (agents.protocol.v2)
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid


class MessageMetadata(BaseModel):
    """메시지 메타데이터"""
    session_id: str = Field(..., description="세션 ID")
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="상관관계 ID")
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="추적 ID")
    mode: str = Field(default="conversation", description="모드 (conversation/podcast)")
    interaction_unit: str = Field(default="turn", description="상호작용 단위")
    tier: Optional[int] = Field(default=None, description="처리 계층")
    priority: int = Field(default=1, description="우선순위")
    retry_count: int = Field(default=0, description="재시도 횟수")


class MessageAudit(BaseModel):
    """메시지 감사 정보"""
    agent_version: str = Field(default="1.0.0", description="에이전트 버전")
    processing_time_ms: int = Field(default=0, description="처리 시간(ms)")
    llm_calls: int = Field(default=0, description="LLM 호출 횟수")
    status: str = Field(default="ok", description="상태")


class AgentMessage(BaseModel):
    """에이전트 간 표준 메시지 형식 (agents.protocol.v2)"""
    schema_version: str = Field(default="agents.protocol.v2", description="스키마 버전")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}", description="메시지 ID")
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}", description="요청 ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="타임스탬프")
    sender: str = Field(..., description="발신 에이전트")
    receiver: str = Field(..., description="수신 에이전트")
    message_type: str = Field(default="request", description="메시지 타입 (request/response/event)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="페이로드")
    metadata: MessageMetadata = Field(default_factory=MessageMetadata)
    audit: MessageAudit = Field(default_factory=MessageAudit)
    errors: List[str] = Field(default_factory=list, description="에러 목록")


def create_message(
    sender: str,
    receiver: str,
    payload: Dict[str, Any],
    session_id: str,
    message_type: str = "request",
    mode: str = "conversation",
    tier: Optional[int] = None,
) -> AgentMessage:
    """에이전트 메시지 생성 헬퍼 함수"""
    return AgentMessage(
        sender=sender,
        receiver=receiver,
        message_type=message_type,
        payload=payload,
        metadata=MessageMetadata(
            session_id=session_id,
            mode=mode,
            tier=tier,
        )
    )
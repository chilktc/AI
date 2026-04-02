"""MessageEnvelope 프로토콜 v2.0 단위 테스트."""

from src.models.message import (
    MessageAudit,
    MessageEnvelope,
    MessageError,
    MessageMetadata,
    MessageType,
    Priority,
)


class TestPriority:
    def test_critical_is_zero(self):
        assert Priority.CRITICAL == 0

    def test_ordering(self):
        assert Priority.CRITICAL < Priority.HIGH < Priority.NORMAL < Priority.LOW


class TestMessageType:
    def test_all_types_exist(self):
        assert MessageType.REQUEST == "request"
        assert MessageType.RESPONSE == "response"
        assert MessageType.EVENT == "event"
        assert MessageType.CANCEL == "cancel"
        assert MessageType.ERROR == "error"


class TestMessageMetadata:
    def test_defaults(self):
        meta = MessageMetadata(session_id="sess_123")
        assert meta.session_id == "sess_123"
        assert meta.mode == "podcast"
        assert meta.interaction_unit == "episode"
        assert meta.tier is None
        assert meta.priority == Priority.HIGH
        assert meta.retry_count == 0

    def test_correlation_id_auto_generated(self):
        m1 = MessageMetadata(session_id="s1")
        m2 = MessageMetadata(session_id="s1")
        assert m1.correlation_id != m2.correlation_id
        assert m1.correlation_id.startswith("corr_")

    def test_trace_id_auto_generated(self):
        meta = MessageMetadata(session_id="s1")
        assert meta.trace_id.startswith("trace_")


class TestMessageAudit:
    def test_defaults(self):
        audit = MessageAudit()
        assert audit.agent_version == "1.0.0"
        assert audit.processing_time_ms == 0
        assert audit.llm_calls == 0
        assert audit.status == "ok"


class TestMessageError:
    def test_basic_error(self):
        err = MessageError(code="AGENT_TIMEOUT", message="Timed out")
        assert err.code == "AGENT_TIMEOUT"
        assert err.details == {}


class TestMessageEnvelope:
    def test_creation(self):
        meta = MessageMetadata(session_id="sess_001")
        env = MessageEnvelope(
            sender="safety",
            receiver="emotion",
            message_type=MessageType.REQUEST,
            payload={"user_input": "test"},
            metadata=meta,
        )
        assert env.schema_version == "agents.protocol.v2"
        assert env.sender == "safety"
        assert env.receiver == "emotion"
        assert env.message_type == MessageType.REQUEST
        assert env.payload == {"user_input": "test"}

    def test_auto_generated_ids(self):
        meta = MessageMetadata(session_id="s1")
        env = MessageEnvelope(
            sender="a",
            receiver="b",
            message_type=MessageType.RESPONSE,
            metadata=meta,
        )
        assert env.message_id.startswith("msg_")
        assert env.request_id.startswith("req_")

    def test_unique_ids(self):
        meta = MessageMetadata(session_id="s1")
        e1 = MessageEnvelope(
            sender="a", receiver="b", message_type=MessageType.REQUEST, metadata=meta
        )
        e2 = MessageEnvelope(
            sender="a", receiver="b", message_type=MessageType.REQUEST, metadata=meta
        )
        assert e1.message_id != e2.message_id

    def test_serialization_roundtrip(self):
        meta = MessageMetadata(session_id="sess_001", tier=1)
        env = MessageEnvelope(
            sender="safety",
            receiver="workflow",
            message_type=MessageType.CANCEL,
            payload={"reason": "crisis"},
            metadata=meta,
        )
        json_str = env.model_dump_json()
        restored = MessageEnvelope.model_validate_json(json_str)
        assert restored.sender == "safety"
        assert restored.message_type == MessageType.CANCEL
        assert restored.metadata.tier == 1

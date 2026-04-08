import typing

from src.models.agent_state import AgentState


def test_agent_state_has_memory_write_fields():
    """AgentState에 memory_write 관련 3개 필드가 존재한다."""
    hints = typing.get_type_hints(AgentState)
    assert "memory_write" in hints, "memory_write 필드 없음"
    assert "memory_text" in hints, "memory_text 필드 없음"
    assert "memory_metadata" in hints, "memory_metadata 필드 없음"


def test_agent_state_memory_write_types():
    """memory_write는 bool, memory_text는 str."""
    hints = typing.get_type_hints(AgentState)
    assert hints["memory_write"] is bool
    assert hints["memory_text"] is str

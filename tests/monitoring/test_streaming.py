"""스트리밍 이벤트 및 체크포인팅 통합 테스트."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import (
    _get_writer,
    compile_graph,
    tier1_podcast_fan_out,
)
from src.models.agent_state import AgentState

# === _get_writer 헬퍼 테스트 ===


def test_get_writer_returns_callable_outside_langgraph() -> None:
    """LangGraph 컨텍스트 밖에서 no-op 함수를 반환한다."""
    writer = _get_writer()
    assert callable(writer)
    writer({"event": "test"})  # no-op이므로 에러 없음


# === 스트리밍 이벤트 테스트 ===


def _make_podcast_fan_out_patches():
    """팟캐스트 Fan-out 테스트용 patch 컨텍스트를 생성한다."""
    emitted: list[dict] = []

    def mock_writer(event: Any) -> None:
        emitted.append(event)

    patches = [
        patch("src.graph.workflow._get_writer", return_value=mock_writer),
        patch(
            "src.graph.workflow.safety_node",
            new_callable=AsyncMock,
            return_value={"safety_flags": {"status": "safe"}, "risk_level": 0},
        ),
        patch(
            "src.graph.workflow.emotion_node",
            new_callable=AsyncMock,
            return_value={"emotion_vectors": {}},
        ),
        patch(
            "src.graph.workflow.content_analyzer_node",
            new_callable=AsyncMock,
            return_value={"content_analysis": {}},
        ),
        patch(
            "src.graph.workflow.podcast_reasoning_node",
            new_callable=AsyncMock,
            return_value={"reasoning_result": {}},
        ),
    ]
    return emitted, patches


@pytest.mark.asyncio
async def test_fan_out_emits_all_events() -> None:
    """팟캐스트 fan-out이 tier_start, agent_complete(4), tier_end를 발행한다."""
    emitted, patches = _make_podcast_fan_out_patches()
    state = AgentState(user_input="팟캐스트", user_id="u1", session_id="s1", mode="podcast")
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        await tier1_podcast_fan_out(state)

    tier_starts = [e for e in emitted if e.get("event") == "tier_start"]
    assert len(tier_starts) == 1
    assert tier_starts[0]["tier"] == 1
    assert tier_starts[0]["mode"] == "podcast"

    agent_completes = [e for e in emitted if e.get("event") == "agent_complete"]
    assert len(agent_completes) == 4
    completed_agents = {e["agent"] for e in agent_completes}
    assert completed_agents == {"safety", "emotion", "content_analyzer", "podcast_reasoning"}

    tier_ends = [e for e in emitted if e.get("event") == "tier_end"]
    assert len(tier_ends) == 1
    assert tier_ends[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_podcast_crisis_emits_crisis_event() -> None:
    """CRISIS 시 crisis_detected + tier_end(status=crisis) 이벤트가 발행된다."""
    emitted: list[dict] = []

    def mock_writer(event: Any) -> None:
        emitted.append(event)

    state = AgentState(user_input="위기", user_id="u1", session_id="s1", mode="podcast")

    with (
        patch("src.graph.workflow._get_writer", return_value=mock_writer),
        patch(
            "src.graph.workflow.safety_node",
            new_callable=AsyncMock,
            return_value={
                "safety_flags": {"status": "crisis"},
                "risk_level": 4,
                "risk_score": 0.95,
                "crisis_response": "위기 응답",
            },
        ),
        patch("src.graph.workflow.emotion_node", new_callable=AsyncMock, return_value={}),
        patch("src.graph.workflow.content_analyzer_node", new_callable=AsyncMock, return_value={}),
        patch("src.graph.workflow.podcast_reasoning_node", new_callable=AsyncMock, return_value={}),
    ):
        result = await tier1_podcast_fan_out(state)

    crisis_events = [e for e in emitted if e.get("event") == "crisis_detected"]
    assert len(crisis_events) == 1
    assert crisis_events[0]["risk_level"] == 4

    tier_ends = [e for e in emitted if e.get("event") == "tier_end"]
    assert tier_ends[0]["status"] == "crisis"
    assert result["next_step"] == "crisis_response"


# === compile_graph 헬퍼 테스트 ===


@pytest.mark.parametrize(
    "builder",
    ["unified", "podcast"],
    ids=["unified", "podcast"],
)
def test_compile_graph(builder: str) -> None:
    """compile_graph가 올바르게 컴파일된다."""
    compiled = compile_graph(builder)
    assert compiled is not None


def test_compile_invalid_raises_error() -> None:
    """잘못된 builder로 ValueError가 발생한다."""
    with pytest.raises(ValueError, match="Unknown graph builder"):
        compile_graph("invalid")


def test_compile_conversation_raises_error() -> None:
    """conversation 빌더가 제거되었는지 확인한다."""
    with pytest.raises(ValueError, match="Unknown graph builder"):
        compile_graph("conversation")


def test_compile_with_checkpointer() -> None:
    """InMemorySaver 체크포인터로 컴파일된다."""
    from langgraph.checkpoint.memory import InMemorySaver
    compiled = compile_graph("unified", checkpointer=InMemorySaver())
    assert compiled is not None

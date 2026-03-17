"""스트리밍 이벤트 및 체크포인팅 통합 테스트."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import (
    _get_writer,
    compile_graph,
    tier1_conversation_fan_out,
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


def _make_fan_out_patches(mode: str = "conversation"):
    """Fan-out 테스트용 공통 patch 컨텍스트를 생성한다."""
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
    ]
    if mode == "conversation":
        patches += [
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={"context": {}},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={"reasoning_result": {}},
            ),
        ]
    else:
        patches += [
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


def _assert_fan_out_events(emitted: list[dict], mode: str, expected_agents: set[str]) -> None:
    """Fan-out 이벤트 공통 검증 헬퍼."""
    tier_starts = [e for e in emitted if e.get("event") == "tier_start"]
    assert len(tier_starts) == 1
    assert tier_starts[0]["tier"] == 1
    assert tier_starts[0]["mode"] == mode

    agent_completes = [e for e in emitted if e.get("event") == "agent_complete"]
    assert len(agent_completes) == 4
    completed_agents = {e["agent"] for e in agent_completes}
    assert completed_agents == expected_agents

    progress_values = [e["progress"] for e in agent_completes]
    assert "1/4" in progress_values
    assert "4/4" in progress_values

    tier_ends = [e for e in emitted if e.get("event") == "tier_end"]
    assert len(tier_ends) == 1
    assert tier_ends[0]["status"] == "ok"
    assert tier_ends[0]["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_fan_out_emits_all_events_both_modes() -> None:
    """대화 + 팟캐스트 fan-out이 tier_start, agent_complete(4), tier_end를 발행한다."""
    # 대화모드
    emitted_c, patches_c = _make_fan_out_patches("conversation")
    state_c = AgentState(user_input="테스트", user_id="u1", session_id="s1", mode="conversation")
    with patches_c[0], patches_c[1], patches_c[2], patches_c[3], patches_c[4]:
        await tier1_conversation_fan_out(state_c)
    _assert_fan_out_events(emitted_c, "conversation", {"safety", "emotion", "context", "reasoning"})

    # 팟캐스트모드
    emitted_p, patches_p = _make_fan_out_patches("podcast")
    state_p = AgentState(user_input="팟캐스트", user_id="u1", session_id="s1", mode="podcast")
    with patches_p[0], patches_p[1], patches_p[2], patches_p[3], patches_p[4]:
        await tier1_podcast_fan_out(state_p)
    _assert_fan_out_events(emitted_p, "podcast", {"safety", "emotion", "content_analyzer", "podcast_reasoning"})


@pytest.mark.asyncio
async def test_conversation_crisis_emits_crisis_event() -> None:
    """CRISIS 시 crisis_detected + tier_end(status=crisis) 이벤트가 발행된다."""
    emitted: list[dict] = []

    def mock_writer(event: Any) -> None:
        emitted.append(event)

    state = AgentState(user_input="위기", user_id="u1", session_id="s1", mode="conversation")

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
        patch("src.graph.workflow.context_node", new_callable=AsyncMock, return_value={}),
        patch("src.graph.workflow.reasoning_node", new_callable=AsyncMock, return_value={}),
    ):
        result = await tier1_conversation_fan_out(state)

    crisis_events = [e for e in emitted if e.get("event") == "crisis_detected"]
    assert len(crisis_events) == 1
    assert crisis_events[0]["risk_level"] == 4

    tier_ends = [e for e in emitted if e.get("event") == "tier_end"]
    assert tier_ends[0]["status"] == "crisis"
    assert result["next_step"] == "crisis_response"


# === compile_graph 헬퍼 테스트 ===


@pytest.mark.parametrize(
    "builder",
    ["unified", "conversation", "podcast"],
    ids=["unified", "conversation", "podcast"],
)
def test_compile_graph(builder: str) -> None:
    """compile_graph가 올바르게 컴파일된다."""
    compiled = compile_graph(builder)
    assert compiled is not None


def test_compile_invalid_raises_error() -> None:
    """잘못된 builder로 ValueError가 발생한다."""
    with pytest.raises(ValueError, match="Unknown graph builder"):
        compile_graph("invalid")


def test_compile_with_checkpointer() -> None:
    """InMemorySaver 체크포인터로 컴파일된다."""
    from langgraph.checkpoint.memory import InMemorySaver
    compiled = compile_graph("unified", checkpointer=InMemorySaver())
    assert compiled is not None

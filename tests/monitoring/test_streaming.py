"""스트리밍 이벤트 및 체크포인팅 통합 테스트."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import (
    _get_writer,
    build_conversation_graph,
    build_podcast_graph,
    build_unified_graph,
    compile_graph,
    tier1_conversation_fan_out,
    tier1_podcast_fan_out,
)
from src.models.agent_state import AgentState


# ===================================================================
# _get_writer 헬퍼 테스트
# ===================================================================
class TestGetWriter:
    """_get_writer 안전 폴백 테스트."""

    def test_returns_callable_outside_langgraph_context(self) -> None:
        """LangGraph 컨텍스트 밖에서 no-op 함수를 반환한다."""
        writer = _get_writer()
        assert callable(writer)
        # no-op이므로 호출해도 에러 없음
        writer({"event": "test"})


# ===================================================================
# 스트리밍 이벤트 테스트
# ===================================================================
class TestStreamingEvents:
    """Fan-out 함수의 스트리밍 이벤트 발행 테스트."""

    @pytest.mark.asyncio
    async def test_conversation_fan_out_emits_tier_start(
        self,
    ) -> None:
        """대화모드 fan-out이 tier_start 이벤트를 발행한다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="테스트",
            user_id="u1",
            session_id="s1",
            mode="conversation",
        )

        with (
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
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={"context": {}},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={"reasoning_result": {}},
            ),
        ):
            await tier1_conversation_fan_out(state)

        # tier_start 이벤트 확인
        tier_starts = [e for e in emitted_events if e.get("event") == "tier_start"]
        assert len(tier_starts) == 1
        assert tier_starts[0]["tier"] == 1
        assert tier_starts[0]["mode"] == "conversation"
        assert len(tier_starts[0]["agents"]) == 4

    @pytest.mark.asyncio
    async def test_conversation_fan_out_emits_agent_complete(
        self,
    ) -> None:
        """정상 흐름에서 4개의 agent_complete 이벤트가 발행된다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="테스트",
            user_id="u1",
            session_id="s1",
            mode="conversation",
        )

        with (
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
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={"context": {}},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={"reasoning_result": {}},
            ),
        ):
            await tier1_conversation_fan_out(state)

        agent_completes = [e for e in emitted_events if e.get("event") == "agent_complete"]
        assert len(agent_completes) == 4

        completed_agents = {e["agent"] for e in agent_completes}
        assert completed_agents == {"safety", "emotion", "context", "reasoning"}

    @pytest.mark.asyncio
    async def test_conversation_fan_out_emits_tier_end(
        self,
    ) -> None:
        """정상 흐름에서 tier_end(status=ok) 이벤트가 발행된다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="테스트",
            user_id="u1",
            session_id="s1",
            mode="conversation",
        )

        with (
            patch("src.graph.workflow._get_writer", return_value=mock_writer),
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value={"safety_flags": {"status": "safe"}, "risk_level": 0},
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await tier1_conversation_fan_out(state)

        tier_ends = [e for e in emitted_events if e.get("event") == "tier_end"]
        assert len(tier_ends) == 1
        assert tier_ends[0]["status"] == "ok"
        assert tier_ends[0]["elapsed_ms"] >= 0

    @pytest.mark.asyncio
    async def test_conversation_crisis_emits_crisis_event(
        self,
    ) -> None:
        """CRISIS 시 crisis_detected + tier_end(status=crisis) 이벤트가 발행된다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="위기 상황",
            user_id="u1",
            session_id="s1",
            mode="conversation",
        )

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
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = await tier1_conversation_fan_out(state)

        # crisis_detected 이벤트
        crisis_events = [e for e in emitted_events if e.get("event") == "crisis_detected"]
        assert len(crisis_events) == 1
        assert crisis_events[0]["risk_level"] == 4

        # tier_end with crisis status
        tier_ends = [e for e in emitted_events if e.get("event") == "tier_end"]
        assert len(tier_ends) == 1
        assert tier_ends[0]["status"] == "crisis"

        # result에 crisis_response 포함
        assert result["next_step"] == "crisis_response"

    @pytest.mark.asyncio
    async def test_podcast_fan_out_emits_events(
        self,
    ) -> None:
        """팟캐스트모드 fan-out도 동일한 이벤트를 발행한다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="팟캐스트 테스트",
            user_id="u1",
            session_id="s1",
            mode="podcast",
        )

        with (
            patch("src.graph.workflow._get_writer", return_value=mock_writer),
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value={"safety_flags": {"status": "safe"}, "risk_level": 0},
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value={},
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
        ):
            await tier1_podcast_fan_out(state)

        tier_starts = [e for e in emitted_events if e.get("event") == "tier_start"]
        assert len(tier_starts) == 1
        assert tier_starts[0]["mode"] == "podcast"
        assert "content_analyzer" in tier_starts[0]["agents"]

        agent_completes = [e for e in emitted_events if e.get("event") == "agent_complete"]
        assert len(agent_completes) == 4

    @pytest.mark.asyncio
    async def test_agent_complete_has_progress(self) -> None:
        """agent_complete 이벤트에 progress 필드가 포함된다."""
        emitted_events: list[dict] = []

        def mock_writer(event: Any) -> None:
            emitted_events.append(event)

        state = AgentState(
            user_input="테스트",
            user_id="u1",
            session_id="s1",
            mode="conversation",
        )

        with (
            patch("src.graph.workflow._get_writer", return_value=mock_writer),
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value={"safety_flags": {"status": "safe"}},
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            await tier1_conversation_fan_out(state)

        agent_completes = [e for e in emitted_events if e.get("event") == "agent_complete"]
        progress_values = [e["progress"] for e in agent_completes]

        # 진행률이 순차적으로 증가
        assert "1/4" in progress_values
        assert "4/4" in progress_values


# ===================================================================
# compile_graph 헬퍼 테스트
# ===================================================================
class TestCompileGraph:
    """compile_graph 헬퍼 함수 테스트."""

    def test_compile_unified(self) -> None:
        compiled = compile_graph("unified")
        assert compiled is not None

    def test_compile_conversation(self) -> None:
        compiled = compile_graph("conversation")
        assert compiled is not None

    def test_compile_podcast(self) -> None:
        compiled = compile_graph("podcast")
        assert compiled is not None

    def test_compile_default_is_unified(self) -> None:
        compiled = compile_graph()
        assert compiled is not None

    def test_compile_invalid_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown graph builder"):
            compile_graph("invalid")

    def test_compile_with_checkpointer(self) -> None:
        """InMemorySaver 체크포인터로 컴파일된다."""
        from langgraph.checkpoint.memory import InMemorySaver

        checkpointer = InMemorySaver()
        compiled = compile_graph("unified", checkpointer=checkpointer)
        assert compiled is not None

    def test_compile_without_checkpointer(self) -> None:
        """체크포인터 없이도 정상 컴파일된다."""
        compiled = compile_graph("unified", checkpointer=None)
        assert compiled is not None

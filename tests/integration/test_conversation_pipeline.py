"""
대화모드 파이프라인 통합 테스트.

TIER 0 → TIER 1(병렬) → TIER 2 → TIER 3 → TIER 4 전체 흐름을 검증한다.
모든 에이전트는 stub/mock 상태이므로, 파이프라인 구조와 상태 전달을 테스트한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import (
    build_conversation_graph,
    build_unified_graph,
    tier1_conversation_fan_out,
)
from src.models.agent_state import AgentState


class TestConversationPipelineFlow:
    """대화모드 정상 흐름 테스트."""

    @pytest.mark.asyncio
    async def test_tier1_fan_out_returns_merged_results(
        self,
        conversation_state: AgentState,
        mock_safety_safe_result: dict[str, Any],
        mock_emotion_result: dict[str, Any],
        mock_context_result: dict[str, Any],
        mock_reasoning_result: dict[str, Any],
    ) -> None:
        """TIER 1 fan-out 후 4개 결과가 모두 병합되는지 확인."""
        with (
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value=mock_safety_safe_result,
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value=mock_emotion_result,
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value=mock_context_result,
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value=mock_reasoning_result,
            ),
        ):
            result = await tier1_conversation_fan_out(conversation_state)

        # 4개 에이전트 결과가 모두 존재하는지 확인
        assert "safety_flags" in result
        assert "emotion_vectors" in result
        assert "context" in result
        assert "reasoning_result" in result

        # CRISIS가 아닌 정상 흐름
        assert result.get("next_step") != "crisis_response"

    @pytest.mark.asyncio
    async def test_tier1_safe_status_passes_all_results(
        self,
        conversation_state: AgentState,
        mock_safety_safe_result: dict[str, Any],
    ) -> None:
        """Safety safe 판정 시 모든 TIER 1 결과가 정상 전달되는지 확인."""
        with (
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value=mock_safety_safe_result,
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value={"emotion_vectors": {"primary": "neutral"}},
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value={"context": {"current_topic": "test"}},
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value={"reasoning_result": {"confidence": 0.7}},
            ),
        ):
            result = await tier1_conversation_fan_out(conversation_state)

        assert result["safety_flags"]["status"] == "safe"
        assert result["risk_level"] == 0

    @pytest.mark.asyncio
    async def test_conversation_graph_builds_without_error(self) -> None:
        """대화모드 그래프가 오류 없이 빌드되는지 확인."""
        graph = build_conversation_graph()
        assert graph is not None

    @pytest.mark.asyncio
    async def test_unified_graph_builds_without_error(self) -> None:
        """통합 그래프가 오류 없이 빌드되는지 확인."""
        graph = build_unified_graph()
        assert graph is not None


class TestConversationPipelineStateTransfer:
    """대화모드 상태 전달 검증."""

    @pytest.mark.asyncio
    async def test_tier1_results_contain_expected_keys(
        self,
        conversation_state: AgentState,
        mock_safety_safe_result: dict[str, Any],
        mock_emotion_result: dict[str, Any],
        mock_context_result: dict[str, Any],
        mock_reasoning_result: dict[str, Any],
    ) -> None:
        """TIER 1 결과에 각 에이전트의 필드가 포함되는지 확인."""
        with (
            patch(
                "src.graph.workflow.safety_node",
                new_callable=AsyncMock,
                return_value=mock_safety_safe_result,
            ),
            patch(
                "src.graph.workflow.emotion_node",
                new_callable=AsyncMock,
                return_value=mock_emotion_result,
            ),
            patch(
                "src.graph.workflow.context_node",
                new_callable=AsyncMock,
                return_value=mock_context_result,
            ),
            patch(
                "src.graph.workflow.reasoning_node",
                new_callable=AsyncMock,
                return_value=mock_reasoning_result,
            ),
        ):
            result = await tier1_conversation_fan_out(conversation_state)

        # Safety 필드
        assert "safety_flags" in result
        assert "risk_level" in result
        assert "risk_score" in result

        # Emotion 필드
        assert "emotion_vectors" in result

        # Context 필드
        assert "context" in result

        # Reasoning 필드
        assert "reasoning_result" in result
        assert "synthesis_guidance" in result["reasoning_result"]

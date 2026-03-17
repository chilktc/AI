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
    tier1_conversation_fan_out,
)
from src.models.agent_state import AgentState


@pytest.mark.asyncio
async def test_tier1_fan_out_merged_results_and_keys(
    conversation_state: AgentState,
    mock_safety_safe_result: dict[str, Any],
    mock_emotion_result: dict[str, Any],
    mock_context_result: dict[str, Any],
    mock_reasoning_result: dict[str, Any],
) -> None:
    """TIER 1 fan-out 후 4개 결과 병합, 상태 키, safe 판정을 한 번에 검증."""
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

    # 4개 에이전트 결과가 모두 존재
    assert "safety_flags" in result
    assert "emotion_vectors" in result
    assert "context" in result
    assert "reasoning_result" in result

    # 정상 흐름 (CRISIS 아님)
    assert result.get("next_step") != "crisis_response"

    # Safety 상세 필드
    assert "risk_level" in result
    assert "risk_score" in result
    assert result["safety_flags"]["status"] == "safe"
    assert result["risk_level"] == 0

    # Reasoning 상세 필드
    assert "synthesis_guidance" in result["reasoning_result"]



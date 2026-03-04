"""
팟캐스트모드 파이프라인 통합 테스트.

TIER 0 → TIER 1(병렬) → TIER 2 → TIER 3 → TIER 4 전체 흐름을 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import (
    build_podcast_graph,
    tier1_podcast_fan_out,
)
from src.models.agent_state import AgentState


@pytest.mark.asyncio
async def test_tier1_podcast_fan_out_all_fields(
    podcast_state: AgentState,
    mock_safety_safe_result: dict[str, Any],
    mock_emotion_result: dict[str, Any],
    mock_content_analysis_result: dict[str, Any],
    mock_podcast_reasoning_result: dict[str, Any],
) -> None:
    """팟캐스트 TIER 1 fan-out 후 4개 결과 병합 및 팟캐스트 전용 필드를 검증."""
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
            "src.graph.workflow.content_analyzer_node",
            new_callable=AsyncMock,
            return_value=mock_content_analysis_result,
        ),
        patch(
            "src.graph.workflow.podcast_reasoning_node",
            new_callable=AsyncMock,
            return_value=mock_podcast_reasoning_result,
        ),
    ):
        result = await tier1_podcast_fan_out(podcast_state)

    # 4개 에이전트 결과가 모두 존재
    assert "safety_flags" in result
    assert "emotion_vectors" in result
    assert "content_analysis" in result
    assert "reasoning_result" in result

    # 정상 흐름 (CRISIS 아님)
    assert result.get("next_step") != "crisis_response"

    # content_analysis 팟캐스트 전용 필드
    assert result["content_analysis"]["main_theme"] == "감정 일기와 자기 돌봄"
    assert "main_theme" in result["content_analysis"]
    assert "emotional_journey" in result["content_analysis"]


@pytest.mark.asyncio
async def test_podcast_graph_builds_without_error() -> None:
    """팟캐스트모드 그래프가 오류 없이 빌드되는지 확인."""
    graph = build_podcast_graph()
    assert graph is not None

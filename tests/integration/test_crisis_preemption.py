"""
Safety CRISIS 선점 메커니즘 통합 테스트.

Safety Agent가 CRISIS 판정 시:
1. 나머지 TIER 1 태스크가 취소되는지
2. 즉시 위기 응답이 생성되는지
3. TIER 2~4를 건너뛰는지
검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.graph.workflow import tier1_podcast_fan_out
from src.models.agent_state import AgentState


@pytest.mark.asyncio
async def test_podcast_crisis_all_assertions(
    podcast_crisis_state: AgentState,
    mock_safety_crisis_result: dict[str, Any],
) -> None:
    """팟캐스트모드 CRISIS: 즉시 응답 + Content Analyzer 취소를 한 번에 검증."""
    with (
        patch(
            "src.graph.workflow.safety_node",
            new_callable=AsyncMock,
            return_value=mock_safety_crisis_result,
        ),
        patch(
            "src.graph.workflow.emotion_node",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "src.graph.workflow.content_analyzer_node",
            new_callable=AsyncMock,
            return_value={"content_analysis": {"should_not": "appear"}},
        ),
        patch(
            "src.graph.workflow.podcast_reasoning_node",
            new_callable=AsyncMock,
            return_value={},
        ),
    ):
        result = await tier1_podcast_fan_out(podcast_crisis_state)

    assert result.get("next_step") == "crisis_response"
    assert "final_output" in result
    # Content Analyzer 결과가 포함되지 않아야 함
    assert "content_analysis" not in result

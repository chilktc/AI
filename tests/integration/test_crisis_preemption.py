"""
Safety CRISIS 전 구간 유지 통합 테스트.

Safety Agent가 CRISIS 판정 시 (신규 아키텍처, 2026-04-15):
1. TIER 1 병렬 에이전트는 모두 정상 완료 (취소 없음)
2. next_step="tier2"로 라우팅하여 TIER 2~4 계속 진행
3. TIER 2~4는 safety_flags.status="crisis"를 감지해 LLM 미호출 폴백으로 처리

emotion_log/content_analyses/mind-frequencies가 정상 저장되도록
cancel_event를 발행하지 않고 전 구간을 유지하는 방식으로 전환되었다.
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
    """팟캐스트모드 CRISIS: TIER 1 병렬 에이전트 전원 완료 + next_step=tier2 라우팅."""
    with (
        patch(
            "src.graph.workflow.safety_node",
            new_callable=AsyncMock,
            return_value=mock_safety_crisis_result,
        ),
        patch(
            "src.graph.workflow.emotion_node",
            new_callable=AsyncMock,
            return_value={"emotion_vectors": {"primary_emotion": "crisis"}},
        ),
        patch(
            "src.graph.workflow.content_analyzer_node",
            new_callable=AsyncMock,
            return_value={"content_analysis": {"main_theme": "crisis"}},
        ),
        patch(
            "src.graph.workflow.podcast_reasoning_node",
            new_callable=AsyncMock,
            return_value={"reasoning_result": {"reasoning_depth": "standard"}},
        ),
    ):
        result = await tier1_podcast_fan_out(podcast_crisis_state)

    # 새 아키텍처: TIER 2 진입
    assert result.get("next_step") == "tier2"
    # CRISIS 플래그 보존
    assert result.get("safety_flags", {}).get("status") == "crisis"
    # TIER 1 모든 에이전트 결과가 포함되어야 함 (취소 안 함)
    assert "content_analysis" in result
    assert "emotion_vectors" in result
    assert "reasoning_result" in result

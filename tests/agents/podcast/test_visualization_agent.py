"""
Visualization Agent 단위 테스트.

시각화 프롬프트 생성, 감정 → 색상 매핑, 안전 경고 추가를 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.visualization import (
    EMOTION_COLOR_MAP,
    VisualizationAgent,
    _choose_palette,
)
from src.models.agent_state import AgentState


@pytest.fixture
def agent() -> VisualizationAgent:
    return VisualizationAgent()


@pytest.mark.asyncio
async def test_process_returns_visualization_result(agent: VisualizationAgent) -> None:
    """LLM 정상 응답 시 visualization_result 구조가 올바르다."""
    llm_response = {
        "image_prompt": "Soft gradient in blue tones",
        "interpretation": "오늘의 마음 상태를 파란 빛으로 표현했어요.",
        "style_tags": ["calm", "blue"],
    }
    state = AgentState(
        user_input="테스트", user_id="u", session_id="s1", mode="podcast",
        emotion_vectors={
            "primary_emotion": "sadness", "intensity": 0.6,
            "valence": -0.3, "arousal": 0.4,
        },
        safety_flags={"status": "safe", "required_in_script": []},
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    vr = result["visualization_result"]
    assert vr["mode"] == "podcast"
    assert "s1" in vr["image_url"]
    assert len(vr["interpretation_text"]) > 0
    assert vr["style_info"]["palette"] == "blue"
    assert vr["style_info"]["primary_emotion"] == "sadness"


@pytest.mark.parametrize(
    "input_name, expected_key",
    [
        ("우울", "sadness"),
        ("불안", "anxiety"),
        ("기쁨", "joy"),
        ("neutral", "neutral"),
        ("unknown_emotion", "neutral"),
        ("", "neutral"),
    ],
    ids=["korean_alias", "korean_anxiety", "korean_joy", "english", "unknown", "empty"],
)
def test_color_map_lookup(input_name: str, expected_key: str) -> None:
    """감정명 → 색상 매핑이 올바르게 동작한다."""
    palette = _choose_palette(input_name)
    expected = EMOTION_COLOR_MAP[expected_key]
    assert palette["palette"] == expected["palette"]


@pytest.mark.asyncio
async def test_safety_addendum_on_warning(agent: VisualizationAgent) -> None:
    """safety_flags가 warning일 때 interpretation에 안전 경고가 추가된다."""
    llm_response = {
        "image_prompt": "Abstract gradient",
        "interpretation": "오늘의 감정을 표현했어요",
        "style_tags": [],
    }
    state = AgentState(
        user_input="우울해요", user_id="u", session_id="s2", mode="podcast",
        emotion_vectors={"primary_emotion": "sadness", "intensity": 0.7},
        safety_flags={
            "status": "warning",
            "required_in_script": ["전문가 상담을 권합니다."],
        },
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    interpretation = result["visualization_result"]["interpretation_text"]
    assert "전문가 상담을 권합니다." in interpretation

"""
Visualization Agent 단위 테스트.

LLM 기반 이미지 프롬프트 기획 + 이미지 생성 API 호출 결과를 검증한다.
(PR #10 리팩토링 이후: 하드코딩 색상 매핑 제거, visual_data 출력)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.visualization import VisualizationAgent
from src.models.agent_state import AgentState


@pytest.fixture
def agent() -> VisualizationAgent:
    return VisualizationAgent()


@pytest.mark.asyncio
async def test_process_returns_visual_data(agent: VisualizationAgent) -> None:
    """정상 호출 시 visual_data 구조가 올바르다."""
    llm_response = {
        "image_prompt": "Soft gradient in blue tones with organic shapes",
        "style_type": "organic",
        "interpretation": "오늘의 마음 상태를 파란 빛으로 표현했어요.",
    }
    image_gen_response = {
        "url": "https://cdn.example.com/images/abc123.png",
    }
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s1",
        mode="podcast",
        emotion_vectors={
            "primary_emotion": "sadness",
            "intensity": 0.6,
            "valence": -0.3,
            "arousal": 0.4,
        },
        content_analysis={"main_theme": "스트레스 관리"},
    )

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(agent, "call_image_gen", create=True, new_callable=AsyncMock, return_value=image_gen_response),
    ):
        result = await agent.process(state)

    vd = result["visual_data"]
    assert vd["image_url"] == "https://cdn.example.com/images/abc123.png"
    assert vd["style_type"] == "organic"
    assert vd["interpretation"] == "오늘의 마음 상태를 파란 빛으로 표현했어요."
    assert vd["original_prompt"] == "Soft gradient in blue tones with organic shapes"
    assert vd["resolution"] == "1024x1024"
    assert vd["status"] == "completed"


@pytest.mark.asyncio
async def test_llm_context_includes_emotion_and_content(agent: VisualizationAgent) -> None:
    """LLM에 전달되는 컨텍스트에 감정 벡터와 콘텐츠 분석이 포함된다."""
    llm_response = {
        "image_prompt": "test prompt",
        "style_type": "geometric",
        "interpretation": "테스트",
    }
    image_gen_response = {"url": "https://example.com/img.png"}
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={"primary_emotion": "불안", "intensity": 0.8},
        content_analysis={"main_theme": "직장 스트레스"},
    )

    llm_mock = AsyncMock(return_value=llm_response)
    with (
        patch.object(agent, "call_llm_json", llm_mock),
        patch.object(agent, "call_image_gen", create=True, new_callable=AsyncMock, return_value=image_gen_response),
    ):
        await agent.process(state)

    call_args = llm_mock.call_args
    user_message = call_args.kwargs.get(
        "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
    )
    assert "불안" in user_message
    assert "직장 스트레스" in user_message


@pytest.mark.asyncio
async def test_image_gen_called_with_llm_prompt(agent: VisualizationAgent) -> None:
    """call_image_gen에 LLM이 생성한 프롬프트가 전달된다."""
    llm_response = {
        "image_prompt": "Abstract flowing colors representing anxiety",
        "style_type": "organic",
        "interpretation": "불안한 감정",
    }
    image_gen_response = {"url": "https://example.com/img.png"}
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )

    img_mock = AsyncMock(return_value=image_gen_response)
    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(agent, "call_image_gen", create=True, new=img_mock),
    ):
        await agent.process(state)

    img_mock.assert_called_once_with(
        prompt="Abstract flowing colors representing anxiety",
        model="dall-e-3",
        size="1024x1024",
        quality="standard",
    )

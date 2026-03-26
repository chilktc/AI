"""
Visualization Agent 단위 테스트.

LLM 기반 이미지 프롬프트 기획 + 이미지 생성 API 호출 결과를 검증한다.
settings.yaml 기반 설정 + Bedrock 이미지 모델 + S3 업로드 구조.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        "image_binary": b"\x89PNG\r\n\x1a\n",  # Bedrock 반환 포맷
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

    mock_s3 = MagicMock()
    agent.s3_client = mock_s3

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response),
    ):
        result = await agent.process(state)

    vd = result["visual_data"]
    assert vd["image_url"] is not None
    assert vd["style_type"] == "organic"
    assert vd["interpretation"] == "오늘의 마음 상태를 파란 빛으로 표현했어요."
    assert vd["original_prompt"] == "Soft gradient in blue tones with organic shapes"
    assert vd["status"] == "completed"
    mock_s3.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_llm_context_includes_emotion_and_content(agent: VisualizationAgent) -> None:
    """LLM에 전달되는 컨텍스트에 감정 벡터와 콘텐츠 분석이 포함된다."""
    llm_response = {
        "image_prompt": "test prompt",
        "style_type": "geometric",
        "interpretation": "테스트",
    }
    image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n"}
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={"primary_emotion": "불안", "intensity": 0.8},
        content_analysis={"main_theme": "직장 스트레스"},
    )

    llm_mock = AsyncMock(return_value=llm_response)
    agent.s3_client = MagicMock()

    with (
        patch.object(agent, "call_llm_json", llm_mock),
        patch.object(agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response),
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
    """call_image_gen에 LLM이 생성한 프롬프트와 settings 기반 모델이 전달된다."""
    llm_response = {
        "image_prompt": "Abstract flowing colors representing anxiety",
        "style_type": "organic",
        "interpretation": "불안한 감정",
    }
    image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n"}
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )

    img_mock = AsyncMock(return_value=image_gen_response)
    agent.s3_client = MagicMock()

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(agent, "call_image_gen", new=img_mock),
    ):
        await agent.process(state)

    img_mock.assert_called_once()
    call_kwargs = img_mock.call_args
    assert call_kwargs.kwargs["prompt"] == "Abstract flowing colors representing anxiety"
    assert call_kwargs.kwargs["model"] == "amazon.titan-image-generator-v2:0"


@pytest.mark.asyncio
async def test_skip_visualization_env(agent: VisualizationAgent) -> None:
    """SKIP_VISUALIZATION=true 환경변수로 이미지 생성을 건너뛴다."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )

    with patch.dict("os.environ", {"SKIP_VISUALIZATION": "true"}):
        result = await agent.process(state)

    assert result["visual_data"]["status"] == "skipped"

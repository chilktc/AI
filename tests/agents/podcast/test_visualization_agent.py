"""
Visualization Agent 단위 테스트.

LLM 기반 이미지 프롬프트 기획 + 이미지 생성 API 호출 결과를 검증한다.
settings.yaml 기반 설정 + Bedrock 이미지 모델 + S3 업로드 구조.
"""

from __future__ import annotations

from typing import Any
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
        patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ),
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
        patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ),
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


@pytest.mark.asyncio
async def test_visualization_llm_failure_returns_failed_status(agent: VisualizationAgent) -> None:
    """call_llm_json() 실패 시 status='failed' visual_data를 반환한다."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )
    mock = AsyncMock(side_effect=Exception("LLM error"))
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    vd = result["visual_data"]
    assert vd["status"] == "failed"
    assert vd["error"] == "llm_call_failed"
    assert vd["image_url"] is None


@pytest.mark.asyncio
async def test_visual_data_style_type_is_str_not_none(agent: VisualizationAgent) -> None:
    """LLM이 style_type=None 반환 시 빈 문자열 기본값 적용 (VI-1)."""
    llm_response = {"image_prompt": "test", "style_type": None, "interpretation": None}
    image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n"}
    state = AgentState(
        user_input="오늘 하루",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={"primary_emotion": "calm"},
    )

    agent.s3_client = MagicMock()

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ),
    ):
        result = await agent.process(state)

    vd = result.get("visual_data", {})
    assert isinstance(vd.get("style_type"), str), f"style_type 타입 오류: {vd.get('style_type')!r}"
    assert vd["style_type"] == "abstract"
    assert isinstance(vd.get("interpretation"), str)


@pytest.mark.asyncio
async def test_error_path_visual_data_has_same_keys_as_normal_path(
    agent: VisualizationAgent,
) -> None:
    """에러 반환도 정상 반환과 동일한 키 구조를 가진다 (VI-2)."""
    state = AgentState(
        user_input="오늘 하루",
        user_id="u",
        session_id="s",
        mode="podcast",
    )

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    vd = result.get("visual_data", {})
    for key in ["image_url", "style_type", "interpretation"]:
        assert key in vd, f"에러 경로 visual_data에 '{key}' 키 없음"


# === 콘텐츠 정책 방어 테스트 ===


class TestImagePromptSanitization:
    """_sanitize_image_prompt()가 금지 키워드를 제거하는지 검증한다."""

    def test_removes_english_blocked_keywords(self) -> None:
        from src.agents.podcast.visualization import _sanitize_image_prompt

        result = _sanitize_image_prompt("Abstract forms with human face showing violence")
        assert "human" not in result
        assert "face" not in result
        assert "violence" not in result
        assert "Abstract" in result

    def test_removes_korean_blocked_keywords(self) -> None:
        from src.agents.podcast.visualization import _sanitize_image_prompt

        result = _sanitize_image_prompt("추상적 형태 사람 얼굴 폭력 표현")
        assert "사람" not in result
        assert "얼굴" not in result
        assert "폭력" not in result

    def test_returns_safe_fallback_when_all_removed(self) -> None:
        from src.agents.podcast.visualization import SAFE_FALLBACK_PROMPT, _sanitize_image_prompt

        result = _sanitize_image_prompt("human face violence blood")
        assert result == SAFE_FALLBACK_PROMPT

    def test_preserves_safe_prompt(self) -> None:
        from src.agents.podcast.visualization import _sanitize_image_prompt

        safe = "Soft gradient with warm beige tones and blurred edges"
        result = _sanitize_image_prompt(safe)
        assert result == safe


@pytest.mark.asyncio
async def test_content_blocked_uses_safe_fallback(agent: VisualizationAgent) -> None:
    """ContentBlockedError 발생 시 SAFE_FALLBACK_PROMPT로 재시도한다."""
    from src.agents.shared.base_agent import ContentBlockedError

    llm_response = {
        "image_prompt": "test prompt",
        "style_type": "soft_blurred",
        "interpretation": "테스트",
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

    call_count = 0

    async def mock_image_gen(**kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ContentBlockedError("content blocked")
        return image_gen_response

    agent.s3_client = MagicMock()

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(agent, "call_image_gen", side_effect=mock_image_gen),
    ):
        result = await agent.process(state)

    assert result["visual_data"]["status"] == "completed"
    assert call_count == 2


@pytest.mark.asyncio
async def test_content_blocked_after_max_retries_returns_failed(
    agent: VisualizationAgent,
) -> None:
    """재시도 후에도 차단되면 status='failed', error='content_blocked'를 반환한다."""
    from src.agents.shared.base_agent import ContentBlockedError

    llm_response = {
        "image_prompt": "test prompt",
        "style_type": "soft_blurred",
        "interpretation": "테스트",
    }
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={},
        content_analysis={},
    )

    agent.s3_client = MagicMock()

    with (
        patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
        patch.object(
            agent,
            "call_image_gen",
            new_callable=AsyncMock,
            side_effect=ContentBlockedError("blocked"),
        ),
    ):
        result = await agent.process(state)

    vd = result["visual_data"]
    assert vd["status"] == "failed"
    assert vd["error"] == "content_blocked"


# === LLM 실제 호출 테스트 ===


@pytest.mark.live
class TestVisualizationWithLLM:
    """VisualizationAgent LLM 실제 호출 테스트 (이미지 생성 mock, S3 mock)."""

    @pytest.fixture
    def agent(self, llm_client) -> VisualizationAgent:
        if llm_client is None:
            pytest.skip("LLM client not available")
        ag = VisualizationAgent()
        ag.llm_client = llm_client
        ag.s3_client = MagicMock()
        return ag

    @pytest.mark.asyncio
    async def test_llm_visual_data_structure(self, agent: VisualizationAgent) -> None:
        """실제 LLM이 이미지 프롬프트를 생성하고 visual_data 구조가 올바르다."""
        import time

        state = AgentState(
            user_input="오늘 많이 지쳤어요",
            user_id="u",
            session_id="s",
            mode="podcast",
            emotion_vectors={
                "primary_emotion": "fatigue",
                "intensity": 0.7,
                "valence": -0.4,
                "arousal": 0.3,
            },
            content_analysis={"main_theme": "번아웃 회복"},
        )
        image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n" + b"\x00" * 100}

        with patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ):
            start = time.time()
            result = await agent.process(state)
            elapsed = time.time() - start

        vd = result["visual_data"]
        print(f"\n[Visualization] ⏱️ {elapsed:.2f}초")
        print(f"  status={vd.get('status')}, style_type={vd.get('style_type')!r}")
        print(f"  prompt={str(vd.get('original_prompt', ''))[:60]}...")

        assert vd["status"] == "completed"
        assert isinstance(vd.get("style_type"), str)  # VI-1: None 아닌 str
        assert isinstance(vd.get("interpretation"), str)
        assert vd.get("original_prompt") is not None
        assert vd.get("image_url") is not None

    @pytest.mark.asyncio
    async def test_llm_prompt_contains_emotion_info(self, agent: VisualizationAgent) -> None:
        """LLM 호출 시 감정 정보가 user_message에 포함된다."""
        import time

        state = AgentState(
            user_input="불안한 하루였어요",
            user_id="u",
            session_id="s",
            mode="podcast",
            emotion_vectors={"primary_emotion": "anxiety", "intensity": 0.8},
            content_analysis={"main_theme": "불안 관리"},
        )
        image_gen_response = {"image_binary": b"\x89PNG\r\n\x1a\n" + b"\x00" * 100}
        llm_mock = AsyncMock(wraps=agent.call_llm_json)

        with patch.object(
            agent, "call_image_gen", new_callable=AsyncMock, return_value=image_gen_response
        ):
            with patch.object(agent, "call_llm_json", llm_mock):
                start = time.time()
                await agent.process(state)
                elapsed = time.time() - start

        print(f"\n[Visualization prompt check] ⏱️ {elapsed:.2f}초")
        call_args = llm_mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "anxiety" in user_message or "불안" in str(state.get("emotion_vectors", {}))

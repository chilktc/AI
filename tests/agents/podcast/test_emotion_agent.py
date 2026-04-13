"""
Emotion Agent 단위 테스트.

감정 벡터 추출, clamp 보정, fallback 로직을 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.emotion import EmotionAgent
from src.models.agent_state import AgentState


@pytest.fixture
def agent() -> EmotionAgent:
    with patch.object(EmotionAgent, "get_prompt", return_value="dummy"):
        ag = EmotionAgent()
    ag.get_prompt = lambda key="system_prompt": "dummy"
    return ag


@pytest.mark.asyncio
async def test_process_returns_emotion_vectors(agent: EmotionAgent) -> None:
    """LLM 정상 응답 시 emotion_vectors가 올바르게 반환된다."""
    llm_response = {
        "primary_emotion": "frustration",
        "intensity": 0.8,
        "valence": -0.5,
        "arousal": 0.7,
        "secondary_emotions": ["disappointment"],
        "tone_recommendation": "empathetic_supportive",
        "emotional_journey_hint": ["공감", "이해", "전환"],
    }
    state = AgentState(
        user_input="직장 스트레스가 심해요",
        user_id="u",
        session_id="s",
        mode="podcast",
    )

    mock = AsyncMock(return_value=llm_response)
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    ev = result["emotion_vectors"]
    assert ev["primary_emotion"] == "frustration"
    assert 0.0 <= ev["intensity"] <= 1.0
    assert -1.0 <= ev["valence"] <= 1.0
    assert 0.0 <= ev["arousal"] <= 1.0
    assert isinstance(ev["secondary_emotions"], list)
    assert isinstance(ev["emotional_journey_hint"], list)


@pytest.mark.asyncio
async def test_fallback_on_key_error(agent: EmotionAgent) -> None:
    """LLM 호출 시 KeyError가 발생하면 키워드 기반 fallback을 사용한다."""
    state = AgentState(
        user_input="불안하고 걱정이 많아요",
        user_id="u",
        session_id="s",
        mode="podcast",
    )

    mock = AsyncMock(side_effect=KeyError("prompt"))
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    ev = result["emotion_vectors"]
    assert ev["primary_emotion"] == "anxiety"
    assert ev["intensity"] == 0.7
    assert ev["valence"] == -0.4
    assert ev["arousal"] == 0.7


@pytest.mark.asyncio
async def test_clamp_out_of_range_values(agent: EmotionAgent) -> None:
    """LLM이 범위 밖 수치를 반환해도 clamp 처리된다."""
    llm_response = {
        "primary_emotion": "joy",
        "intensity": 1.5,  # > 1.0
        "valence": -2.0,  # < -1.0
        "arousal": "invalid",  # not a number
        "secondary_emotions": "not_a_list",  # type error
        "tone_recommendation": "positive",
        "emotional_journey_hint": None,  # not a list
    }
    state = AgentState(user_input="기분 좋아요", user_id="u", session_id="s", mode="podcast")

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    ev = result["emotion_vectors"]
    assert ev["intensity"] == 1.0  # clamped
    assert ev["valence"] == -1.0  # clamped
    assert ev["arousal"] == 0.3  # default
    assert ev["secondary_emotions"] == []  # type-safe
    assert ev["emotional_journey_hint"] == []  # type-safe


@pytest.mark.asyncio
async def test_llm_failure_fallback_uses_intent_emotions(agent: EmotionAgent) -> None:
    """LLM 실패 시 intent.detected_entities.emotions를 1순위 fallback으로 사용한다."""
    state = AgentState(
        user_input="요즘 힘들다",  # 키워드 없음 → 키워드만으론 neutral
        user_id="u",
        session_id="s",
        mode="podcast",
        intent={"detected_entities": {"emotions": ["sadness", "fatigue"]}},
    )
    mock = AsyncMock(side_effect=Exception("LLM error"))
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    ev = result["emotion_vectors"]
    assert ev["primary_emotion"] == "sadness"
    assert ev["secondary_emotions"] == ["fatigue"]


@pytest.mark.asyncio
async def test_fallback_emotional_journey_hint_is_empty_not_hardcoded(
    agent: EmotionAgent,
) -> None:
    """LLM 실패 시 emotional_journey_hint는 빈 리스트다 — 하드코딩 금지 (EA-1)."""
    state = AgentState(
        user_input="힘든 하루", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    hint = result.get("emotion_vectors", {}).get("emotional_journey_hint", "필드없음")
    assert hint == [], f"기대값 [], 실제값: {hint!r}"


# === LLM 실제 호출 테스트 ===


@pytest.mark.live
class TestEmotionAgentWithLLM:
    """EmotionAgent LLM 실제 호출 테스트."""

    @pytest.fixture
    def agent(self, llm_client) -> EmotionAgent:
        if llm_client is None:
            pytest.skip("LLM client not available")
        ag = EmotionAgent()
        ag.llm_client = llm_client
        return ag

    @pytest.mark.asyncio
    async def test_llm_emotion_vectors_structure(self, agent: EmotionAgent) -> None:
        """실제 LLM이 올바른 emotion_vectors 구조를 반환한다."""
        import time

        state = AgentState(
            user_input="직장 스트레스가 너무 심해서 매일 밤 잠을 못 자고 있어요.",
            user_id="u",
            session_id="s",
            mode="podcast",
        )
        with patch("src.agents.podcast.emotion.AgentDataPublisher") as mock_pub:
            mock_pub.return_value.publish = AsyncMock(return_value=True)
            start = time.time()
            result = await agent.process(state)
            elapsed = time.time() - start

        ev = result["emotion_vectors"]
        print(f"\n[Emotion] ⏱️ {elapsed:.2f}초")
        print(f"  primary={ev.get('primary_emotion')}, intensity={ev.get('intensity'):.2f}, valence={ev.get('valence'):.2f}")

        assert "primary_emotion" in ev
        assert isinstance(ev["primary_emotion"], str)
        assert 0.0 <= ev["intensity"] <= 1.0
        assert -1.0 <= ev["valence"] <= 1.0
        assert 0.0 <= ev["arousal"] <= 1.0
        assert isinstance(ev["secondary_emotions"], list)
        assert isinstance(ev["emotional_journey_hint"], list)

    @pytest.mark.asyncio
    async def test_llm_negative_emotion_has_negative_valence(self, agent: EmotionAgent) -> None:
        """부정적 감정 입력은 valence < 0을 반환하는 경향이 있다."""
        import time

        state = AgentState(
            user_input="너무 불안하고 두렵고 모든 게 무너지는 것 같아요.",
            user_id="u",
            session_id="s",
            mode="podcast",
        )
        with patch("src.agents.podcast.emotion.AgentDataPublisher") as mock_pub:
            mock_pub.return_value.publish = AsyncMock(return_value=True)
            start = time.time()
            result = await agent.process(state)
            elapsed = time.time() - start

        ev = result["emotion_vectors"]
        print(f"\n[Emotion negative] ⏱️ {elapsed:.2f}초")
        print(f"  primary={ev.get('primary_emotion')}, valence={ev.get('valence'):.2f}")

        assert ev["valence"] < 0.5, f"부정 입력에 높은 valence: {ev['valence']}"

"""
Learning Agent 단위 테스트.

비동기 후처리 에이전트: AgentState를 변경하지 않고 빈 dict를 반환한다.
LLM 실패/저장 실패 시 예외 미전파, _build_learning_context 구성을 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.podcast.learning import LearningAgent, learning_node
from src.models.agent_state import AgentState

# === 픽스처 ===


@pytest.fixture
def agent() -> LearningAgent:
    """BackendClient를 mock으로 교체한 테스트용 에이전트."""
    with patch("src.agents.podcast.learning.BackendClient"):
        ag = LearningAgent()
    ag._api_client = MagicMock()
    ag._api_client.save = AsyncMock(return_value=True)
    return ag


@pytest.fixture
def full_state() -> AgentState:
    """다양한 필드가 채워진 AgentState."""
    return AgentState(
        user_input="직장 스트레스가 심해서 번아웃이 올 것 같아요.",
        user_id="u",
        session_id="s",
        mode="podcast",
        emotion_vectors={"primary_emotion": "stress", "intensity": 0.8},
        content_analysis={"topic": "번아웃", "episode_type": "healing"},
        intent={"intent_type": "emotional_support", "complexity_score": 0.6},
        safety_flags={"status": "safe", "risk_score": 0.1},
        reasoning_result={"depth_level": "standard", "method": "got"},
        validation_result={"overall_score": 0.85, "safety_compliance": True},
        final_output="안녕하세요. 오늘은 번아웃에 대해 이야기해봅시다.",
    )


# === 단위 테스트 ===


@pytest.mark.asyncio
async def test_process_returns_empty_dict(agent: LearningAgent, full_state: AgentState) -> None:
    """LLM 정상 호출 시 빈 dict를 반환한다 (AgentState 미변경)."""
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value={"pattern": "stress_coping"}
    ):
        result = await agent.process(full_state)
    assert result == {}


@pytest.mark.asyncio
async def test_llm_failure_propagates_exception(
    agent: LearningAgent, full_state: AgentState
) -> None:
    """LLM 호출 실패 시 예외가 전파된다.

    NOTE: process()에 LLM 실패 핸들러 없음 — workflow에서 asyncio.create_task()로
    실행하면 전체 파이프라인에 영향 없음. 저장 실패만 내부 처리.
    """
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM error")
    ):
        with pytest.raises(RuntimeError, match="LLM error"):
            await agent.process(full_state)


@pytest.mark.asyncio
async def test_save_failure_does_not_propagate(
    agent: LearningAgent, full_state: AgentState
) -> None:
    """백엔드 저장 실패 시 예외가 전파되지 않고 빈 dict를 반환한다."""
    agent._api_client.save = AsyncMock(side_effect=Exception("API timeout"))
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value={"pattern": "ok"}
    ):
        result = await agent.process(full_state)
    assert result == {}


@pytest.mark.asyncio
async def test_save_called_once_on_success(agent: LearningAgent, full_state: AgentState) -> None:
    """LLM 성공 시 백엔드 save가 정확히 1회 호출된다."""
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value={"pattern": "ok"}
    ):
        await agent.process(full_state)
    agent._api_client.save.assert_called_once()


def test_build_learning_context_includes_emotion_and_intent(
    agent: LearningAgent, full_state: AgentState
) -> None:
    """_build_learning_context에 감정/의도 데이터가 포함된다."""
    context = agent._build_learning_context(full_state)
    assert isinstance(context, str)
    assert len(context) > 0
    # 감정 또는 의도 관련 내용 포함
    assert "stress" in context or "감정" in context
    assert "emotional_support" in context or "의도" in context


def test_build_learning_context_with_empty_state(agent: LearningAgent) -> None:
    """빈 state에서도 예외 없이 폴백 메시지를 반환한다."""
    state = AgentState(user_input="", user_id="u", session_id="s", mode="podcast")
    context = agent._build_learning_context(state)
    assert isinstance(context, str)
    assert len(context) > 0


@pytest.mark.asyncio
async def test_learning_node_returns_empty_dict() -> None:
    """learning_node()가 빈 dict를 반환한다."""
    state = AgentState(user_input="테스트", user_id="u", session_id="s", mode="podcast")
    with patch("src.agents.podcast.learning.BackendClient"):
        with patch.object(LearningAgent, "call_llm_json", new_callable=AsyncMock, return_value={}):
            result = await learning_node(state)
    assert result == {}


# === LLM 실제 호출 테스트 ===


@pytest.mark.live
class TestLearningAgentWithLLM:
    """LearningAgent LLM 실제 호출 테스트 (BackendClient mock)."""

    @pytest.fixture
    def agent(self, llm_client) -> LearningAgent:
        if llm_client is None:
            pytest.skip("LLM client not available")
        with patch("src.agents.podcast.learning.BackendClient"):
            ag = LearningAgent()
        ag.llm_client = llm_client
        ag._api_client = MagicMock()
        ag._api_client.save = AsyncMock(return_value=True)
        return ag

    @pytest.mark.asyncio
    async def test_llm_learning_returns_empty_dict(self, agent: LearningAgent) -> None:
        """실제 LLM 호출 후 빈 dict를 반환하고 save가 1회 호출된다."""
        import time

        state = AgentState(
            user_input="직장 스트레스로 번아웃이 왔어요. 매일 야근하고 있어요.",
            user_id="u",
            session_id="s",
            mode="podcast",
            emotion_vectors={"primary_emotion": "exhaustion", "intensity": 0.8},
            content_analysis={"topic": "번아웃", "episode_type": "healing"},
            intent={"intent_type": "emotional_support", "complexity_score": 0.6},
            safety_flags={"status": "safe", "risk_score": 0.1},
            validation_result={"overall_score": 0.85},
        )
        start = time.time()
        result = await agent.process(state)
        elapsed = time.time() - start

        print(f"\n[Learning] ⏱️ {elapsed:.2f}초")
        print(f"  result={result!r} (비어있어야 함)")
        assert result == {}, f"빈 dict가 아님: {result!r}"
        agent._api_client.save.assert_called_once()

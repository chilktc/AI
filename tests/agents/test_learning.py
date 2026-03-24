"""
Learning Agent 테스트.

사용자 패턴 학습 분석, 백엔드 API 저장, 실패 시 안전한 처리를 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.shared.learning import LearningAgent
from src.models.agent_state import AgentState

# === 픽스처 ===


@pytest.fixture
def agent() -> LearningAgent:
    """테스트용 Learning Agent 인스턴스."""
    return LearningAgent()


@pytest.fixture
def full_state() -> AgentState:
    """학습 분석에 필요한 모든 필드가 포함된 AgentState."""
    return AgentState(
        user_input="오늘 직장에서 스트레스를 많이 받았어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        emotion_vectors={"primary_emotion": "stressed", "intensity": 0.7},
        content_analysis={"topic": "직장 스트레스", "episode_type": "reflection"},
        final_output="오늘의 에피소드는 직장에서의 스트레스 관리에 대해 다룹니다...",
    )


@pytest.fixture
def mock_learning_data() -> dict[str, Any]:
    """LLM이 반환할 모의 학습 분석 결과."""
    return {
        "preferred_topics": ["직장 스트레스", "자기돌봄"],
        "emotion_patterns": {
            "dominant_emotion": "stressed",
            "expression_style": "직접적 표현",
            "trend": "stable",
        },
        "content_preferences": {
            "preferred_type": "reflection",
            "preferred_depth": "moderate",
            "preferred_tone": "warm",
        },
        "session_summary": "직장 스트레스에 대한 반성 세션",
        "improvement_notes": ["이완 기법 추가 추천"],
    }


# === 핵심 로직 테스트 ===


@pytest.mark.asyncio
async def test_process_returns_empty_and_saves(
    agent: LearningAgent,
    full_state: AgentState,
    mock_learning_data: dict[str, Any],
) -> None:
    """process()가 빈 dict를 반환하고, LLM 호출 + API 저장이 수행된다."""
    mock_llm = AsyncMock(return_value=mock_learning_data)
    mock_save = AsyncMock()
    with (
        patch.object(agent, "call_llm_json", mock_llm),
        patch.object(agent._api_client, "save", mock_save),
    ):
        result = await agent.process(full_state)

    assert result == {}
    mock_llm.assert_called_once()
    mock_save.assert_called_once()

    # LLM 호출 시 사용자 입력이 컨텍스트에 포함
    call_args = mock_llm.call_args
    user_message = call_args.kwargs.get(
        "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
    )
    assert "스트레스" in user_message

    # API 저장 시 올바른 리소스와 필드 전달
    save_args = mock_save.call_args
    assert save_args.args[0] == "learning"
    save_request = save_args.args[1]
    assert save_request.user_id == "test_user_001"
    assert save_request.type == "learning"
    assert save_request.data["mode"] == "podcast"


@pytest.mark.asyncio
async def test_process_with_conversation_mode(
    agent: LearningAgent,
    mock_learning_data: dict[str, Any],
) -> None:
    """mode='conversation'에서도 정상 동작한다."""
    state = AgentState(
        user_input="오늘 정말 힘든 하루였어요.",
        user_id="conv_user_001",
        session_id="sess_conv_001",
        mode="conversation",
        emotion_vectors={"primary_emotion": "tired", "intensity": 0.6},
        final_output="힘든 하루를 보내셨군요.",
    )
    mock_save = AsyncMock()
    with (
        patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_learning_data
        ),
        patch.object(agent._api_client, "save", mock_save),
    ):
        result = await agent.process(state)

    assert result == {}
    assert mock_save.call_args.args[1].data["mode"] == "conversation"


# === 컨텍스트 조합 테스트 ===


@pytest.mark.parametrize(
    "state_kwargs, expected_in, expected_not_in",
    [
        # 모든 필드가 있을 때
        (
            {
                "user_input": "스트레스 받아요",
                "emotion_vectors": {"primary_emotion": "stressed"},
                "content_analysis": {"topic": "직장"},
                "final_output": "에피소드 내용입니다.",
            },
            ["[사용자 입력]", "스트레스", "[감정 분석]", "[콘텐츠 분석]", "[최종 출력 (요약)]"],
            [],
        ),
        # user_input만 있을 때
        (
            {"user_input": "오늘 기분이 좋아요"},
            ["[사용자 입력]", "오늘 기분이 좋아요"],
            ["[감정 분석]", "[콘텐츠 분석]", "[최종 출력 (요약)]"],
        ),
        # 빈 emotion_vectors → 섹션 생략
        (
            {"user_input": "테스트", "emotion_vectors": {}},
            ["[사용자 입력]"],
            ["[감정 분석]"],
        ),
    ],
    ids=["full", "only_user_input", "empty_emotion_vectors"],
)
def test_build_context(
    agent: LearningAgent,
    state_kwargs: dict,
    expected_in: list[str],
    expected_not_in: list[str],
) -> None:
    """상태 필드 조합에 따라 학습 컨텍스트가 올바르게 생성된다."""
    state = AgentState(
        user_id="u", session_id="s", mode="podcast", **state_kwargs
    )
    context = agent._build_learning_context(state)

    for text in expected_in:
        assert text in context
    for text in expected_not_in:
        assert text not in context


@pytest.mark.parametrize(
    "state_kwargs, check",
    [
        (
            {"user_input": ""},
            lambda ctx: ctx == "세션 데이터가 부족합니다.",
        ),
        (
            {"user_input": "테스트", "final_output": "A" * 1000},
            lambda ctx: "..." in ctx and "A" * 500 in ctx,
        ),
    ],
    ids=["minimal_returns_default", "truncates_long_output"],
)
def test_build_context_edge_cases(
    agent: LearningAgent, state_kwargs: dict, check,
) -> None:
    """최소 필드 → 기본 메시지, 긴 출력 → truncation."""
    state = AgentState(user_id="u", session_id="s", mode="podcast", **state_kwargs)
    assert check(agent._build_learning_context(state))


# === 에러 처리 테스트 ===


@pytest.mark.parametrize(
    "error_cls",
    [Exception, TimeoutError, ConnectionError],
    ids=["generic", "timeout", "connection"],
)
@pytest.mark.asyncio
async def test_api_save_failure_does_not_raise(
    agent: LearningAgent,
    full_state: AgentState,
    mock_learning_data: dict[str, Any],
    error_cls: type,
) -> None:
    """API 저장 실패 시 예외가 전파되지 않는다 (비동기 후처리)."""
    with (
        patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_learning_data
        ),
        patch.object(
            agent._api_client, "save",
            new_callable=AsyncMock, side_effect=error_cls("저장 실패"),
        ),
    ):
        result = await agent.process(full_state)

    assert result == {}

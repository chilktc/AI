"""
Batch Validator 에이전트 테스트.

스크립트 품질 검증, 통과/실패 분기, 재시도 루프, 강제 통과 로직을 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.batch_validator import BatchValidatorAgent
from src.models.agent_state import AgentState

# === 픽스처 ===


@pytest.fixture
def agent() -> BatchValidatorAgent:
    """테스트용 Batch Validator 에이전트 인스턴스."""
    return BatchValidatorAgent()


@pytest.fixture
def passing_validation() -> dict[str, Any]:
    """검증 통과 LLM 응답 (action.decision 기반)."""
    return {
        "overall_score": 0.85,
        "action": {"decision": "approve", "feedback": "양호"},
        "criteria": {
            "structure_completeness": {"passed": True, "score": 0.9, "feedback": "완전"},
            "safety_compliance": {"passed": True, "score": 0.9, "feedback": "양호"},
            "tone_consistency": {"passed": True, "score": 0.8, "feedback": "일관성 유지"},
            "timing_appropriateness": {"passed": True, "score": 0.85, "feedback": "적절"},
            "content_safety": {"passed": True, "score": 0.9, "feedback": "안전"},
        },
        "critical_issues": [],
    }


@pytest.fixture
def failing_validation() -> dict[str, Any]:
    """검증 실패 LLM 응답 (action.decision 기반)."""
    return {
        "overall_score": 0.45,
        "action": {"decision": "revise", "feedback": "개선 필요"},
        "criteria": {
            "structure_completeness": {"passed": False, "score": 0.4, "feedback": "아웃트로 누락"},
            "safety_compliance": {"passed": True, "score": 0.8, "feedback": "양호"},
            "tone_consistency": {"passed": False, "score": 0.5, "feedback": "톤 불일치"},
            "timing_appropriateness": {"passed": True, "score": 0.7, "feedback": "적절"},
            "content_safety": {"passed": True, "score": 0.9, "feedback": "안전"},
        },
        "critical_issues": ["아웃트로가 누락됨", "본문 톤 불일치"],
    }


@pytest.fixture
def base_state() -> AgentState:
    """검증 대상이 포함된 기본 AgentState."""
    return AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        script_draft={
            "intro": {"title": "오프닝", "content": "안녕하세요"},
            "body": [{"title": "본문 1", "content": "내용"}],
            "outro": {"title": "마무리", "content": "감사합니다"},
        },
        content_analysis={"topic": "스트레스 관리", "episode_type": "reflection"},
        reasoning_result={"narrative_flow": "공감 → 탐색 → 마무리", "key_points": ["스트레스"]},
        safety_flags={"status": "safe"},
        emotion_vectors={"primary_emotion": "불안", "intensity": 0.7},
        iteration_count=0,
    )


# === 검증 통과/실패/강제통과 테스트 ===


@pytest.mark.asyncio
async def test_pass_routes_to_script_personalizer(
    agent: BatchValidatorAgent,
    base_state: AgentState,
    passing_validation: dict[str, Any],
) -> None:
    """검증 통과 시 verdict='PASS', 점수 보존, 카운터 미변경."""
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=passing_validation
    ):
        result = await agent.process(base_state)

    assert result["validation_result"]["verdict"] == "PASS"
    assert result["validation_result"]["overall_score"] == 0.85
    assert "iteration_count" not in result
    # 5가지 기준 키 보존 확인
    expected_keys = {
        "structure_completeness",
        "safety_compliance",
        "tone_consistency",
        "timing_appropriateness",
        "content_safety",
    }
    assert set(result["validation_result"]["criteria"].keys()) == expected_keys


@pytest.mark.parametrize(
    "initial_count",
    [0, 1],
    ids=["first_retry", "second_retry"],
)
@pytest.mark.asyncio
async def test_fail_routes_to_retry_without_incrementing(
    agent: BatchValidatorAgent,
    failing_validation: dict[str, Any],
    initial_count: int,
) -> None:
    """검증 실패 시 retry_script 라우팅, iteration_count는 반환하지 않음 (workflow가 전담)."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=initial_count,
    )
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
    ):
        result = await agent.process(state)

    assert result["validation_result"]["verdict"] == "FAIL"
    assert "iteration_count" not in result


@pytest.mark.parametrize("iteration_count", [2, 5], ids=["exact_max", "above_max"])
@pytest.mark.asyncio
async def test_max_retries_forces_pass(
    agent: BatchValidatorAgent,
    failing_validation: dict[str, Any],
    iteration_count: int,
) -> None:
    """최대 재시도 초과 시 강제 통과 + 원본 검증 결과 보존."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=iteration_count,
    )
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
    ):
        result = await agent.process(state)

    assert result["validation_result"]["forced_pass"] is True
    assert result["validation_result"]["verdict"] == "FAIL"
    assert result["validation_result"]["overall_score"] == 0.45


# === 검증 컨텍스트 조합 테스트 ===


@pytest.mark.parametrize("iteration_count", [0, 1, 2], ids=["zero", "one", "max"])
@pytest.mark.asyncio
async def test_empty_script_early_return_skips_llm(
    agent: BatchValidatorAgent,
    iteration_count: int,
) -> None:
    """빈 스크립트는 iteration_count에 무관하게 LLM 호출 없이 FAIL verdict로 조기 반환."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=iteration_count,
    )
    mock = AsyncMock()
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    mock.assert_not_called()
    assert result["validation_result"]["verdict"] == "FAIL"
    assert result["validation_result"]["overall_score"] == 0.0
    assert "iteration_count" not in result


@pytest.mark.asyncio
async def test_emotion_and_safety_in_context(
    agent: BatchValidatorAgent,
    passing_validation: dict[str, Any],
) -> None:
    """emotion_vectors와 safety warning이 컨텍스트에 포함되는지 확인."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        content_analysis={},
        reasoning_result={},
        safety_flags={"status": "warning"},
        emotion_vectors={"primary_emotion": "우울", "intensity": 0.8},
        iteration_count=0,
    )
    mock = AsyncMock(return_value=passing_validation)
    with patch.object(agent, "call_llm_json", mock):
        await agent.process(state)

    call_args = mock.call_args
    user_message = call_args.kwargs.get(
        "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
    )
    assert "감정 상태" in user_message
    assert "우울" in user_message
    assert "안전 경고 문구" in user_message


# === 엣지 케이스 테스트 ===


@pytest.mark.asyncio
async def test_missing_optional_fields(
    agent: BatchValidatorAgent,
    passing_validation: dict[str, Any],
) -> None:
    """선택 필드(content_analysis 등)가 없어도 LLM 경로가 정상 동작해야 한다."""
    state = AgentState(
        user_input="최소 입력",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        iteration_count=0,
    )
    mock = AsyncMock(return_value=passing_validation)
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    mock.assert_called_once()
    assert "validation_result" in result


@pytest.mark.parametrize(
    "llm_response, expected_verdict",
    [
        ({}, "FAIL"),
        ({"action": {"decision": "approve"}}, "PASS"),
    ],
    ids=["empty_dict_retries", "minimal_approve_passes"],
)
@pytest.mark.asyncio
async def test_llm_edge_case_responses(
    agent: BatchValidatorAgent,
    llm_response: dict[str, Any],
    expected_verdict: str,
) -> None:
    """LLM 응답 엣지 케이스: 빈 dict → FAIL verdict, 최소 approve → PASS verdict."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=0,
    )
    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    assert result["validation_result"]["verdict"] == expected_verdict


@pytest.mark.asyncio
async def test_escalate_sets_critical_fail_verdict(
    agent: BatchValidatorAgent,
) -> None:
    """decision='escalate' 시 CRITICAL_FAIL verdict 설정 (라우팅은 workflow가 전담)."""
    state = AgentState(
        user_input="테스트",
        user_id="u",
        session_id="s",
        mode="podcast",
        script_draft={"intro": {"content": "test"}},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=0,
    )
    escalate_response = {
        "overall_score": 0.1,
        "action": {"decision": "escalate", "feedback": "위험 콘텐츠"},
        "critical_issues": ["유해 콘텐츠 감지"],
    }
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=escalate_response
    ):
        result = await agent.process(state)

    assert "next_step" not in result  # 라우팅은 route_after_tier3_podcast()가 전담
    assert result["validation_result"]["verdict"] == "CRITICAL_FAIL"

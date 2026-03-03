"""
Batch Validator 에이전트 테스트.

스크립트 품질 검증, 통과/실패 분기, 재시도 루프, 강제 통과 로직을 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.batch_validator import (
    BatchValidatorAgent,
    batch_validator_agent,
    batch_validator_node,
)
from src.models.agent_state import AgentState

# === 픽스처 ===


@pytest.fixture
def agent() -> BatchValidatorAgent:
    """테스트용 Batch Validator 에이전트 인스턴스."""
    return BatchValidatorAgent()


@pytest.fixture
def passing_validation() -> dict[str, Any]:
    """검증 통과 LLM 응답."""
    return {
        "passed": True,
        "overall_score": 0.85,
        "criteria": {
            "structure_completeness": {"passed": True, "score": 0.9, "feedback": "완전"},
            "safety_compliance": {"passed": True, "score": 0.9, "feedback": "양호"},
            "tone_consistency": {"passed": True, "score": 0.8, "feedback": "일관성 유지"},
            "timing_appropriateness": {"passed": True, "score": 0.85, "feedback": "적절"},
            "content_safety": {"passed": True, "score": 0.9, "feedback": "안전"},
        },
        "issues": [],
        "suggestions": ["약간의 전환 문구 추가 권장"],
    }


@pytest.fixture
def failing_validation() -> dict[str, Any]:
    """검증 실패 LLM 응답."""
    return {
        "passed": False,
        "overall_score": 0.45,
        "criteria": {
            "structure_completeness": {"passed": False, "score": 0.4, "feedback": "아웃트로 누락"},
            "safety_compliance": {"passed": True, "score": 0.8, "feedback": "양호"},
            "tone_consistency": {"passed": False, "score": 0.5, "feedback": "톤 불일치"},
            "timing_appropriateness": {"passed": True, "score": 0.7, "feedback": "적절"},
            "content_safety": {"passed": True, "score": 0.9, "feedback": "안전"},
        },
        "issues": ["아웃트로가 누락됨", "본문 톤 불일치"],
        "suggestions": ["아웃트로 추가", "톤 통일"],
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


@pytest.fixture
def retried_state() -> AgentState:
    """이미 2번 재시도한 상태의 AgentState."""
    return AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        script_draft={"intro": {}, "body": [], "outro": {}},
        content_analysis={},
        reasoning_result={},
        safety_flags={},
        emotion_vectors={},
        iteration_count=2,
    )


# === 단위 테스트 ===


class TestBatchValidatorPass:
    """검증 통과 시나리오."""

    @pytest.mark.asyncio
    async def test_pass_routes_to_script_personalizer(
        self,
        agent: BatchValidatorAgent,
        base_state: AgentState,
        passing_validation: dict[str, Any],
    ) -> None:
        """검증 통과 시 next_step이 'script_personalizer'인지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=passing_validation
        ):
            result = await agent.process(base_state)

        assert result["next_step"] == "script_personalizer"
        assert result["validation_result"]["passed"] is True
        assert "iteration_count" not in result  # 통과 시 카운터 변경 없음

    @pytest.mark.asyncio
    async def test_pass_preserves_validation_score(
        self,
        agent: BatchValidatorAgent,
        base_state: AgentState,
        passing_validation: dict[str, Any],
    ) -> None:
        """통과 시 overall_score가 정확히 전달되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=passing_validation
        ):
            result = await agent.process(base_state)

        assert result["validation_result"]["overall_score"] == 0.85


class TestBatchValidatorFail:
    """검증 실패 + 재시도 시나리오."""

    @pytest.mark.asyncio
    async def test_fail_routes_to_retry_script(
        self,
        agent: BatchValidatorAgent,
        base_state: AgentState,
        failing_validation: dict[str, Any],
    ) -> None:
        """검증 실패 시 (재시도 가능) next_step이 'retry_script'인지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(base_state)

        assert result["next_step"] == "retry_script"
        assert result["iteration_count"] == 1  # 0 → 1

    @pytest.mark.asyncio
    async def test_fail_increments_iteration_count(
        self,
        agent: BatchValidatorAgent,
        failing_validation: dict[str, Any],
    ) -> None:
        """재시도 시 iteration_count가 올바르게 증가하는지 확인."""
        # iteration_count = 1 상태에서 실패
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
            iteration_count=1,
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(state)

        assert result["iteration_count"] == 2
        assert result["next_step"] == "retry_script"


class TestBatchValidatorForcePass:
    """최대 재시도 초과 → 강제 통과 시나리오."""

    @pytest.mark.asyncio
    async def test_max_retries_forces_pass(
        self,
        agent: BatchValidatorAgent,
        retried_state: AgentState,
        failing_validation: dict[str, Any],
    ) -> None:
        """최대 재시도(2회) 초과 시 강제 통과되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(retried_state)

        # 강제 통과 → script_personalizer로 진행
        assert result["next_step"] == "script_personalizer"
        assert result["validation_result"]["forced_pass"] is True

    @pytest.mark.asyncio
    async def test_forced_pass_preserves_original_validation(
        self,
        agent: BatchValidatorAgent,
        retried_state: AgentState,
        failing_validation: dict[str, Any],
    ) -> None:
        """강제 통과 시에도 원본 검증 결과가 보존되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(retried_state)

        # 원본 검증 데이터가 보존되어야 한다
        assert result["validation_result"]["overall_score"] == 0.45
        assert result["validation_result"]["passed"] is False


class TestBatchValidatorContext:
    """검증 컨텍스트 조합 테스트."""

    @pytest.mark.asyncio
    async def test_empty_script_includes_failure_note(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """스크립트가 비어있으면 실패 노트가 컨텍스트에 포함되는지 확인."""
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
            iteration_count=0,
        )
        mock = AsyncMock(return_value=passing_validation)
        with patch.object(agent, "call_llm_json", mock):
            await agent.process(state)

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "비어있음" in user_message

    @pytest.mark.asyncio
    async def test_emotion_vectors_included_in_context(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """emotion_vectors가 있을 때 감정 상태가 컨텍스트에 포함되는지 확인."""
        state = AgentState(
            user_input="테스트",
            user_id="u",
            session_id="s",
            mode="podcast",
            script_draft={"intro": {"content": "test"}},
            content_analysis={},
            reasoning_result={},
            safety_flags={},
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
        # 감정 상태 섹션이 포함되어야 한다
        assert "감정 상태" in user_message
        assert "우울" in user_message
        assert "0.8" in user_message

    @pytest.mark.asyncio
    async def test_safety_warning_included_in_context(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """safety_flags가 warning일 때 경고 문구가 컨텍스트에 포함되는지 확인."""
        state = AgentState(
            user_input="테스트",
            user_id="u",
            session_id="s",
            mode="podcast",
            script_draft={"intro": {"content": "test"}},
            content_analysis={},
            reasoning_result={},
            safety_flags={"status": "warning"},
            emotion_vectors={},
            iteration_count=0,
        )
        mock = AsyncMock(return_value=passing_validation)
        with patch.object(agent, "call_llm_json", mock):
            await agent.process(state)

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "안전 경고 문구" in user_message

    def test_agent_attributes(self, agent: BatchValidatorAgent) -> None:
        """에이전트 기본 속성이 올바르게 설정되는지 확인."""
        assert agent.name == "batch_validator"
        assert agent.tier == 3
        assert agent.MAX_RETRIES == 2


class TestBatchValidatorNode:
    """LangGraph 노드 함수 테스트."""

    @pytest.mark.asyncio
    async def test_node_function_calls_agent(
        self,
        base_state: AgentState,
        passing_validation: dict[str, Any],
    ) -> None:
        """batch_validator_node가 에이전트를 올바르게 호출하는지 확인."""
        with patch.object(
            batch_validator_agent,
            "process",
            new_callable=AsyncMock,
            return_value={
                "validation_result": passing_validation,
                "next_step": "script_personalizer",
            },
        ):
            result = await batch_validator_node(base_state)

        assert "validation_result" in result
        assert result["next_step"] == "script_personalizer"


class TestBatchValidatorEdgeCases:
    """경계 조건 및 누락된 상태 필드에 대한 엣지 케이스 테스트."""

    @pytest.mark.asyncio
    async def test_iteration_count_boundary_at_max(
        self,
        agent: BatchValidatorAgent,
        failing_validation: dict[str, Any],
    ) -> None:
        """iteration_count가 정확히 MAX_RETRIES(2)일 때 실패하면 강제 통과해야 한다."""
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
            iteration_count=2,  # == MAX_RETRIES 정확한 경계값
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(state)

        # 경계값에서 재시도가 아닌 강제 통과되어야 한다
        assert result["next_step"] == "script_personalizer"
        assert result["validation_result"]["forced_pass"] is True
        # iteration_count를 증가시키지 않아야 한다
        assert "iteration_count" not in result

    @pytest.mark.asyncio
    async def test_iteration_count_above_max(
        self,
        agent: BatchValidatorAgent,
        failing_validation: dict[str, Any],
    ) -> None:
        """iteration_count가 MAX_RETRIES를 크게 초과해도 강제 통과해야 한다."""
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
            iteration_count=5,  # MAX_RETRIES(2)를 크게 초과
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=failing_validation
        ):
            result = await agent.process(state)

        assert result["next_step"] == "script_personalizer"
        assert result["validation_result"]["forced_pass"] is True

    @pytest.mark.asyncio
    async def test_missing_script_draft_in_state(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """script_draft 키가 없는 상태에서도 기본값({})으로 정상 동작해야 한다."""
        # script_draft 필드를 의도적으로 생략
        state = AgentState(
            user_input="테스트",
            user_id="u",
            session_id="s",
            mode="podcast",
            content_analysis={},
            reasoning_result={},
            safety_flags={},
            emotion_vectors={},
            iteration_count=0,
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=passing_validation
        ):
            result = await agent.process(state)

        assert result["next_step"] == "script_personalizer"

    @pytest.mark.asyncio
    async def test_missing_emotion_vectors_in_state(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """emotion_vectors가 없으면 컨텍스트에 감정 상태 섹션이 포함되지 않아야 한다."""
        # emotion_vectors 필드를 의도적으로 생략
        state = AgentState(
            user_input="테스트",
            user_id="u",
            session_id="s",
            mode="podcast",
            script_draft={"intro": {"content": "test"}},
            content_analysis={},
            reasoning_result={},
            safety_flags={},
            iteration_count=0,
        )
        mock = AsyncMock(return_value=passing_validation)
        with patch.object(agent, "call_llm_json", mock):
            await agent.process(state)

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        # 감정 상태 섹션이 포함되지 않아야 한다
        assert "감정 상태" not in user_message

    @pytest.mark.asyncio
    async def test_missing_all_optional_fields(
        self,
        agent: BatchValidatorAgent,
        passing_validation: dict[str, Any],
    ) -> None:
        """필수 입력만 있고 선택 필드가 모두 없어도 LLM 호출 후 결과를 반환해야 한다."""
        state = AgentState(
            user_input="최소 입력",
            user_id="u",
            session_id="s",
            mode="podcast",
            iteration_count=0,
        )
        mock = AsyncMock(return_value=passing_validation)
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(state)

        # LLM이 호출되었는지 확인
        mock.assert_called_once()
        # 결과가 정상적으로 반환되어야 한다
        assert "validation_result" in result
        assert "next_step" in result

    @pytest.mark.asyncio
    async def test_llm_returns_empty_dict(
        self,
        agent: BatchValidatorAgent,
    ) -> None:
        """LLM이 빈 dict를 반환하면 passed가 False로 처리되어 재시도해야 한다."""
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
        # LLM이 빈 dict를 반환하는 경우
        with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value={}):
            result = await agent.process(state)

        # passed 기본값이 False이므로 재시도 경로로 가야 한다
        assert result["next_step"] == "retry_script"
        assert result["iteration_count"] == 1

    @pytest.mark.asyncio
    async def test_llm_returns_passed_true_with_no_score(
        self,
        agent: BatchValidatorAgent,
    ) -> None:
        """LLM이 passed=True만 반환하고 score가 없어도 통과 경로로 라우팅해야 한다."""
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
        # passed=True만 있는 최소 응답
        minimal_response: dict[str, Any] = {"passed": True}
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=minimal_response
        ):
            result = await agent.process(state)

        assert result["next_step"] == "script_personalizer"
        assert result["validation_result"]["passed"] is True

    @pytest.mark.asyncio
    async def test_validation_result_preserves_all_criteria(
        self,
        agent: BatchValidatorAgent,
        base_state: AgentState,
        passing_validation: dict[str, Any],
    ) -> None:
        """검증 결과에 5가지 기준 키가 모두 보존되는지 확인한다."""
        expected_criteria_keys = {
            "structure_completeness",
            "safety_compliance",
            "tone_consistency",
            "timing_appropriateness",
            "content_safety",
        }
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=passing_validation
        ):
            result = await agent.process(base_state)

        criteria = result["validation_result"]["criteria"]
        assert set(criteria.keys()) == expected_criteria_keys



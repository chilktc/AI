"""
TIER 3 → TIER 2 재시도 루프 통합 테스트.

Validator 실패 시:
1. TIER 2 재실행이 발생하는지
2. iteration_count가 증가하는지
3. 최대 2회 재시도 후 강제 통과하는지
검증한다.
"""

from __future__ import annotations

import pytest

from src.graph.workflow import (
    increment_iteration_node,
    route_after_tier3_conversation,
    route_after_tier3_podcast,
)
from src.models.agent_state import AgentState


class TestRetryLoopConversation:
    """대화모드 재시도 루프 테스트."""

    def test_approve_routes_to_tier4(self) -> None:
        """검증 통과 시 TIER 4로 라우팅되는지 확인."""
        state = AgentState(
            validation_result={
                "action": {"decision": "approve"},
            },
            iteration_count=0,
        )
        assert route_after_tier3_conversation(state) == "tier4"

    def test_revise_routes_to_tier2_when_retries_available(self) -> None:
        """검증 실패 + 재시도 가능 시 TIER 2로 라우팅되는지 확인."""
        state = AgentState(
            validation_result={
                "action": {"decision": "revise"},
            },
            iteration_count=0,
        )
        assert route_after_tier3_conversation(state) == "tier2_conversation"

    def test_revise_routes_to_tier2_on_second_attempt(self) -> None:
        """2차 시도에서도 재시도 라우팅되는지 확인."""
        state = AgentState(
            validation_result={
                "action": {"decision": "revise"},
            },
            iteration_count=1,
        )
        assert route_after_tier3_conversation(state) == "tier2_conversation"

    def test_force_pass_when_max_retries_exceeded(self) -> None:
        """최대 재시도(2회) 초과 시 강제 통과(TIER 4)하는지 확인."""
        state = AgentState(
            validation_result={
                "action": {"decision": "revise"},
            },
            iteration_count=2,  # max_retries = 2, 이미 2회 시도
        )
        assert route_after_tier3_conversation(state) == "tier4"

    def test_escalate_with_retries_available_force_passes(self) -> None:
        """escalate 판정 + 재시도 소진 시 강제 통과하는지 확인."""
        state = AgentState(
            validation_result={
                "action": {"decision": "escalate"},
            },
            iteration_count=2,
        )
        assert route_after_tier3_conversation(state) == "tier4"

    def test_crisis_next_step_routes_to_crisis(self) -> None:
        """next_step이 crisis_response일 때 CRISIS 라우팅되는지 확인."""
        state = AgentState(
            next_step="crisis_response",
            validation_result={},
        )
        assert route_after_tier3_conversation(state) == "crisis_response"


class TestRetryLoopPodcast:
    """팟캐스트모드 재시도 루프 테스트."""

    def test_pass_verdict_routes_to_tier4(self) -> None:
        """PASS 판정 시 TIER 4로 라우팅되는지 확인."""
        state = AgentState(
            validation_result={"verdict": "PASS"},
            iteration_count=0,
        )
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_fail_verdict_routes_to_tier2_when_retries_available(self) -> None:
        """FAIL 판정 + 재시도 가능 시 TIER 2로 라우팅되는지 확인."""
        state = AgentState(
            validation_result={"verdict": "FAIL"},
            iteration_count=0,
        )
        assert route_after_tier3_podcast(state) == "tier2_podcast"

    def test_fail_verdict_force_pass_when_max_retries_exceeded(self) -> None:
        """FAIL + 최대 재시도 초과 시 강제 통과하는지 확인."""
        state = AgentState(
            validation_result={"verdict": "FAIL"},
            iteration_count=2,
        )
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_critical_fail_routes_to_crisis(self) -> None:
        """CRITICAL_FAIL 시 즉시 위기 응답으로 라우팅되는지 확인."""
        state = AgentState(
            validation_result={"verdict": "CRITICAL_FAIL"},
            iteration_count=0,
        )
        assert route_after_tier3_podcast(state) == "crisis_response"

    def test_podcast_crisis_next_step_routes_to_crisis(self) -> None:
        """next_step이 crisis_response일 때 CRISIS 라우팅되는지 확인."""
        state = AgentState(
            next_step="crisis_response",
            validation_result={},
        )
        assert route_after_tier3_podcast(state) == "crisis_response"


class TestIterationCounter:
    """iteration_count 증가 테스트."""

    @pytest.mark.asyncio
    async def test_increment_from_zero(self) -> None:
        """iteration_count가 0에서 1로 증가하는지 확인."""
        state = AgentState(iteration_count=0)
        result = await increment_iteration_node(state)
        assert result["iteration_count"] == 1

    @pytest.mark.asyncio
    async def test_increment_from_one(self) -> None:
        """iteration_count가 1에서 2로 증가하는지 확인."""
        state = AgentState(iteration_count=1)
        result = await increment_iteration_node(state)
        assert result["iteration_count"] == 2

    @pytest.mark.asyncio
    async def test_increment_default_when_missing(self) -> None:
        """iteration_count 필드가 없을 때 0→1로 증가하는지 확인."""
        state = AgentState()
        result = await increment_iteration_node(state)
        assert result["iteration_count"] == 1


class TestRouterEdgeCases:
    """라우터 엣지 케이스 테스트."""

    def test_empty_validation_result_defaults_to_approve(self) -> None:
        """validation_result가 비어있을 때 기본 approve 처리되는지 확인."""
        state = AgentState(
            validation_result={},
            iteration_count=0,
        )
        assert route_after_tier3_conversation(state) == "tier4"

    def test_missing_validation_result_defaults_to_approve(self) -> None:
        """validation_result 필드 자체가 없을 때 기본 approve 처리되는지 확인."""
        state = AgentState(iteration_count=0)
        assert route_after_tier3_conversation(state) == "tier4"

    def test_missing_verdict_defaults_to_pass(self) -> None:
        """팟캐스트 verdict가 없을 때 기본 PASS 처리되는지 확인."""
        state = AgentState(
            validation_result={},
            iteration_count=0,
        )
        assert route_after_tier3_podcast(state) == "tier4_podcast"

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

# === 대화모드 라우팅 테스트 ===


@pytest.mark.parametrize(
    "decision, iteration_count, expected_route",
    [
        ("approve", 0, "tier4"),
        ("revise", 0, "tier2_conversation"),
        ("revise", 1, "tier2_conversation"),
        ("revise", 2, "tier4"),  # 최대 재시도 초과 → 강제 통과
        ("escalate", 2, "tier4"),  # escalate + 재시도 소진 → 강제 통과
    ],
    ids=["approve", "revise_first", "revise_second", "force_pass", "escalate_force_pass"],
)
def test_conversation_routing(
    decision: str, iteration_count: int, expected_route: str
) -> None:
    """대화모드 TIER 3 판정에 따른 라우팅을 검증한다."""
    state = AgentState(
        validation_result={"action": {"decision": decision}},
        iteration_count=iteration_count,
    )
    assert route_after_tier3_conversation(state) == expected_route


def test_conversation_crisis_next_step() -> None:
    """next_step이 crisis_response일 때 CRISIS 라우팅된다."""
    state = AgentState(next_step="crisis_response", validation_result={})
    assert route_after_tier3_conversation(state) == "crisis_response"


# === 팟캐스트모드 라우팅 테스트 ===


@pytest.mark.parametrize(
    "verdict, iteration_count, expected_route",
    [
        ("PASS", 0, "tier4_podcast"),
        ("FAIL", 0, "tier2_podcast"),
        ("FAIL", 2, "tier4_podcast"),  # 최대 재시도 초과 → 강제 통과
        ("CRITICAL_FAIL", 0, "crisis_response"),
    ],
    ids=["pass", "fail_retry", "fail_force_pass", "critical_fail"],
)
def test_podcast_routing(
    verdict: str, iteration_count: int, expected_route: str
) -> None:
    """팟캐스트모드 TIER 3 verdict에 따른 라우팅을 검증한다."""
    state = AgentState(
        validation_result={"verdict": verdict},
        iteration_count=iteration_count,
    )
    assert route_after_tier3_podcast(state) == expected_route


def test_podcast_crisis_next_step() -> None:
    """next_step이 crisis_response일 때 CRISIS 라우팅된다."""
    state = AgentState(next_step="crisis_response", validation_result={})
    assert route_after_tier3_podcast(state) == "crisis_response"


# === iteration_count 증가 테스트 ===


@pytest.mark.parametrize(
    "initial, expected",
    [(1, 2)],
    ids=["one_to_two"],
)
@pytest.mark.asyncio
async def test_increment_iteration(initial: int, expected: int) -> None:
    """iteration_count가 올바르게 증가한다."""
    state = AgentState(iteration_count=initial)
    result = await increment_iteration_node(state)
    assert result["iteration_count"] == expected


@pytest.mark.asyncio
async def test_increment_default_when_missing() -> None:
    """iteration_count 필드가 없거나 0일 때 0→1로 증가한다."""
    # 필드 없음 → 0→1
    state = AgentState()
    result = await increment_iteration_node(state)
    assert result["iteration_count"] == 1

    # 명시적 0 → 1
    state_zero = AgentState(iteration_count=0)
    result_zero = await increment_iteration_node(state_zero)
    assert result_zero["iteration_count"] == 1


# === 엣지 케이스 테스트 ===


@pytest.mark.parametrize(
    "router_func, expected_route",
    [
        (route_after_tier3_conversation, "tier4"),
        (route_after_tier3_podcast, "tier4_podcast"),
    ],
    ids=["conversation_empty", "podcast_empty"],
)
def test_empty_validation_result_defaults_to_pass(router_func, expected_route: str) -> None:
    """validation_result가 비어있을 때 기본 통과 처리된다."""
    state = AgentState(validation_result={}, iteration_count=0)
    assert router_func(state) == expected_route



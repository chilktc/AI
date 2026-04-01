"""텔레메트리 콜백 핸들러 단위 테스트."""

from __future__ import annotations

import uuid

import pytest

from src.monitoring.callbacks import (
    MindLogTelemetryCallback,
    _estimate_cost,
)
from src.monitoring.models import AgentMetric

# === 비용 추정 테스트 ===


@pytest.mark.parametrize(
    "model_id, input_tokens, output_tokens, expect_positive",
    [
        ("claude-opus-4-6", 1000, 500, True),
        ("claude-sonnet-4-5-20250929", 1000, 500, True),
        ("claude-haiku-4-5-20251001", 1000, 500, True),
        ("anthropic.claude-opus-4-6-bedrock", 1000, 500, True),
        ("gpt-4o", 1000, 500, False),
    ],
    ids=["opus", "sonnet", "haiku", "bedrock_partial_match", "unknown_zero"],
)
def test_estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    expect_positive: bool,
) -> None:
    """모델별 비용 추정이 올바르게 동작한다."""
    cost = _estimate_cost(model_id, input_tokens, output_tokens)
    if expect_positive:
        assert cost > 0
    else:
        assert cost == 0.0

    # Opus 정확 값 검증
    if model_id == "claude-opus-4-6":
        expected = 1000 * 15.0 / 1_000_000 + 500 * 75.0 / 1_000_000
        assert abs(cost - expected) < 1e-9


# === 콜백 초기화 테스트 ===


@pytest.mark.parametrize(
    "kwargs, expected_session, expected_mode",
    [
        ({}, "", ""),
        ({"session_id": "sess_001", "mode": "conversation"}, "sess_001", "conversation"),
    ],
    ids=["default", "with_params"],
)
def test_init(kwargs: dict, expected_session: str, expected_mode: str) -> None:
    """기본/파라미터 초기화가 올바르게 동작한다."""
    cb = MindLogTelemetryCallback(**kwargs)
    assert cb.metrics.run_id
    assert cb.metrics.session_id == expected_session
    assert cb.metrics.mode == expected_mode


# === on_chain_start 테스트 ===


def test_on_chain_start_records_time_and_metadata() -> None:
    """on_chain_start가 시간을 기록하고 메타데이터를 추출한다."""
    cb = MindLogTelemetryCallback()
    run_id = uuid.uuid4()
    cb.on_chain_start(
        {"name": "safety"},
        {},
        run_id=run_id,
        metadata={"session_id": "sess_from_meta", "mode": "podcast"},
    )
    assert str(run_id) in cb._node_start_times
    assert cb.metrics.session_id == "sess_from_meta"
    assert cb.metrics.mode == "podcast"


# === on_chain_end 테스트 ===


def test_on_chain_end_tier_duration_single_and_parallel() -> None:
    """단일 에이전트 + 병렬 에이전트 TIER 실행 시간 기록 (max 사용)."""
    cb = MindLogTelemetryCallback()

    run1 = uuid.uuid4()
    cb.on_chain_start({"name": "safety"}, {}, run_id=run1)
    cb._node_start_times[str(run1)] -= 0.1

    run2 = uuid.uuid4()
    cb.on_chain_start({"name": "emotion"}, {}, run_id=run2)
    cb._node_start_times[str(run2)] -= 0.2

    cb.on_chain_end(
        {"safety_flags": {"status": "safe"}},
        run_id=run1,
        tags=["safety"],
    )
    assert "tier1" in cb.metrics.tier_durations
    assert cb.metrics.tier_durations["tier1"] >= 100

    cb.on_chain_end({}, run_id=run2, tags=["emotion"])
    # 병렬 시 max 적용
    assert cb.metrics.tier_durations["tier1"] >= 200


def test_on_chain_end_no_start_is_ignored() -> None:
    """on_chain_start 없이 on_chain_end 호출 시 무시된다."""
    cb = MindLogTelemetryCallback()
    cb.on_chain_end({}, run_id=uuid.uuid4(), tags=["safety"])
    assert cb.metrics.tier_durations == {}


# === CRISIS / 이벤트 테스트 ===


@pytest.mark.parametrize(
    "safety_status, risk_level, expect_crisis",
    [
        ("crisis", 4, True),
        ("safe", 0, False),
    ],
    ids=["crisis", "safe"],
)
def test_crisis_detection(safety_status: str, risk_level: int, expect_crisis: bool) -> None:
    """Safety 판정에 따라 CRISIS 이벤트가 기록된다."""
    cb = MindLogTelemetryCallback(session_id="sess_test")
    run_id = uuid.uuid4()
    cb.on_chain_start({"name": "safety"}, {}, run_id=run_id)
    cb.on_chain_end(
        {"safety_flags": {"status": safety_status}, "risk_level": risk_level},
        run_id=run_id,
        tags=["safety"],
    )
    assert cb.metrics.crisis_detected is expect_crisis
    if expect_crisis:
        assert len(cb.events) == 1
        assert cb.events[0].event_type == "crisis"
    else:
        assert len(cb.events) == 0


def test_retry_count_tracking() -> None:
    """Validator가 iteration_count를 기록한다."""
    cb = MindLogTelemetryCallback()
    run_id = uuid.uuid4()
    cb.on_chain_start({"name": "validator"}, {}, run_id=run_id)
    cb.on_chain_end({"iteration_count": 2}, run_id=run_id, tags=["validator"])
    assert cb.metrics.retry_count == 2


def test_on_chain_error_records_event() -> None:
    """에러 발생 시 이벤트가 기록된다."""
    cb = MindLogTelemetryCallback(session_id="sess_err")
    run_id = uuid.uuid4()
    cb.on_chain_start({"name": "reasoning"}, {}, run_id=run_id)
    cb.on_chain_error(RuntimeError("LLM timeout"), run_id=run_id)

    assert len(cb.events) == 1
    assert cb.events[0].event_type == "agent_execution"
    assert cb.events[0].data["status"] == "error"
    assert cb.events[0].data["error_type"] == "RuntimeError"


# === 메트릭 / 요약 테스트 ===


def test_add_agent_metric_and_get_summary() -> None:
    """add_agent_metric → get_summary 전체 라이프사이클을 검증한다."""
    cb = MindLogTelemetryCallback(session_id="sess_001", mode="conversation")
    metric = AgentMetric(
        agent_name="safety",
        tier=1,
        duration_ms=100,
        llm_calls=1,
        input_tokens=1000,
        output_tokens=500,
        model_id="claude-sonnet-4-5-20250929",
    )
    cb.add_agent_metric(metric)

    # 비용 기록 확인
    assert cb.metrics.total_cost_usd > 0
    assert len(cb.metrics.agent_metrics) == 1

    # get_metrics 확인
    metrics = cb.get_metrics()
    assert metrics.completed_at is not None

    # get_summary 확인
    summary = cb.get_summary()
    assert summary["session_id"] == "sess_001"
    assert summary["mode"] == "conversation"
    assert summary["agent_count"] == 1
    assert summary["total_llm_calls"] == 1
    assert summary["estimated_cost_usd"] > 0
    assert summary["crisis_detected"] is False


def test_get_summary_with_error_agents() -> None:
    """에러 에이전트가 summary.errors에 기록된다."""
    cb = MindLogTelemetryCallback()
    cb.add_agent_metric(
        AgentMetric(
            "reasoning",
            1,
            500,
            2,
            model_id="claude-opus-4-6",
            status="error",
            error_message="timeout",
        )
    )
    summary = cb.get_summary()
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["agent"] == "reasoning"
    assert summary["errors"][0]["error"] == "timeout"

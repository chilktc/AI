"""텔레메트리 콜백 핸들러 단위 테스트."""

from __future__ import annotations

import uuid
from typing import Any

from src.monitoring.callbacks import (
    MindLogTelemetryCallback,
    _estimate_cost,
)
from src.monitoring.models import AgentMetric


class TestEstimateCost:
    """모델별 비용 추정 테스트."""

    def test_opus_cost(self) -> None:
        cost = _estimate_cost("claude-opus-4-6", 1000, 500)
        # input: 1000 * 15.0 / 1M = 0.015, output: 500 * 75.0 / 1M = 0.0375
        expected = 0.015 + 0.0375
        assert abs(cost - expected) < 1e-9

    def test_sonnet_cost(self) -> None:
        cost = _estimate_cost("claude-sonnet-4-5-20250929", 1000, 500)
        expected = 1000 * 3.0 / 1_000_000 + 500 * 15.0 / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_haiku_cost(self) -> None:
        cost = _estimate_cost("claude-haiku-4-5-20251001", 1000, 500)
        expected = 1000 * 0.80 / 1_000_000 + 500 * 4.0 / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_returns_zero(self) -> None:
        cost = _estimate_cost("gpt-4o", 1000, 500)
        assert cost == 0.0

    def test_partial_model_match(self) -> None:
        """모델 ID에 키가 포함되어 있으면 매칭된다."""
        cost = _estimate_cost("anthropic.claude-opus-4-6-bedrock", 1000, 500)
        assert cost > 0


class TestMindLogTelemetryCallback:
    """MindLogTelemetryCallback 테스트."""

    def test_init_default(self) -> None:
        cb = MindLogTelemetryCallback()
        assert cb.metrics.run_id
        assert cb.metrics.session_id == ""
        assert cb.metrics.mode == ""

    def test_init_with_params(self) -> None:
        cb = MindLogTelemetryCallback(session_id="sess_001", mode="conversation")
        assert cb.metrics.session_id == "sess_001"
        assert cb.metrics.mode == "conversation"

    def test_on_chain_start_records_time(self) -> None:
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()
        cb.on_chain_start(
            {"name": "safety"},
            {"user_input": "test"},
            run_id=run_id,
        )
        assert str(run_id) in cb._node_start_times

    def test_on_chain_start_extracts_metadata(self) -> None:
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()
        cb.on_chain_start(
            {"name": "safety"},
            {},
            run_id=run_id,
            metadata={"session_id": "sess_from_meta", "mode": "podcast"},
        )
        assert cb.metrics.session_id == "sess_from_meta"
        assert cb.metrics.mode == "podcast"

    def test_on_chain_end_records_tier_duration(self) -> None:
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()

        # 시작 기록
        cb.on_chain_start({"name": "safety"}, {}, run_id=run_id)

        # 시작 시간을 100ms 전으로 조정 (측정 가능한 duration 확보)
        cb._node_start_times[str(run_id)] -= 0.1

        # 완료 (safety → tier1)
        cb.on_chain_end(
            {"safety_flags": {"status": "safe"}},
            run_id=run_id,
            tags=["safety"],
        )

        assert "tier1" in cb.metrics.tier_durations
        assert cb.metrics.tier_durations["tier1"] >= 100

    def test_on_chain_end_no_start_is_ignored(self) -> None:
        """on_chain_start 없이 on_chain_end 호출 시 무시된다."""
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()
        cb.on_chain_end({}, run_id=run_id, tags=["safety"])

        assert cb.metrics.tier_durations == {}

    def test_crisis_detection(self) -> None:
        cb = MindLogTelemetryCallback(session_id="sess_crisis")
        run_id = uuid.uuid4()

        cb.on_chain_start({"name": "safety"}, {}, run_id=run_id)
        cb.on_chain_end(
            {
                "safety_flags": {"status": "crisis"},
                "risk_level": 4,
            },
            run_id=run_id,
            tags=["safety"],
        )

        assert cb.metrics.crisis_detected is True
        assert len(cb.events) == 1
        assert cb.events[0].event_type == "crisis"
        assert cb.events[0].data["agent"] == "safety"
        assert cb.events[0].data["risk_level"] == 4

    def test_no_crisis_when_safe(self) -> None:
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()

        cb.on_chain_start({"name": "safety"}, {}, run_id=run_id)
        cb.on_chain_end(
            {"safety_flags": {"status": "safe"}},
            run_id=run_id,
            tags=["safety"],
        )

        assert cb.metrics.crisis_detected is False
        assert len(cb.events) == 0

    def test_retry_count_tracking(self) -> None:
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()

        cb.on_chain_start({"name": "validator"}, {}, run_id=run_id)
        cb.on_chain_end(
            {"iteration_count": 2},
            run_id=run_id,
            tags=["validator"],
        )

        assert cb.metrics.retry_count == 2

    def test_on_chain_error_records_event(self) -> None:
        cb = MindLogTelemetryCallback(session_id="sess_err")
        run_id = uuid.uuid4()

        cb.on_chain_start({"name": "reasoning"}, {}, run_id=run_id)
        cb.on_chain_error(
            RuntimeError("LLM timeout"),
            run_id=run_id,
        )

        assert len(cb.events) == 1
        assert cb.events[0].event_type == "agent_execution"
        assert cb.events[0].data["status"] == "error"
        assert cb.events[0].data["error_type"] == "RuntimeError"

    def test_add_agent_metric_updates_cost(self) -> None:
        cb = MindLogTelemetryCallback()
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

        assert cb.metrics.total_cost_usd > 0
        assert len(cb.metrics.agent_metrics) == 1

    def test_get_metrics_finalizes(self) -> None:
        cb = MindLogTelemetryCallback()
        metrics = cb.get_metrics()
        assert metrics.completed_at is not None

    def test_get_summary_returns_dict(self) -> None:
        cb = MindLogTelemetryCallback(session_id="sess_001", mode="conversation")
        metric = AgentMetric(
            agent_name="safety",
            tier=1,
            duration_ms=100,
            llm_calls=1,
            input_tokens=500,
            output_tokens=200,
            model_id="claude-haiku-4-5-20251001",
        )
        cb.add_agent_metric(metric)

        summary = cb.get_summary()
        assert summary["session_id"] == "sess_001"
        assert summary["mode"] == "conversation"
        assert summary["agent_count"] == 1
        assert summary["total_llm_calls"] == 1
        assert summary["estimated_cost_usd"] > 0
        assert summary["crisis_detected"] is False

    def test_get_summary_with_error_agents(self) -> None:
        cb = MindLogTelemetryCallback()
        cb.add_agent_metric(
            AgentMetric(
                "reasoning", 1, 500, 2,
                model_id="claude-opus-4-6",
                status="error",
                error_message="timeout",
            )
        )

        summary = cb.get_summary()
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["agent"] == "reasoning"
        assert summary["errors"][0]["error"] == "timeout"

    def test_tier_duration_uses_max_for_parallel(self) -> None:
        """같은 TIER의 여러 에이전트 중 최대 실행 시간이 기록된다."""
        cb = MindLogTelemetryCallback()

        # safety: 100ms
        run1 = uuid.uuid4()
        cb.on_chain_start({"name": "safety"}, {}, run_id=run1)
        cb._node_start_times[str(run1)] -= 0.1  # 100ms 전
        cb.on_chain_end({}, run_id=run1, tags=["safety"])

        # emotion: 200ms
        run2 = uuid.uuid4()
        cb.on_chain_start({"name": "emotion"}, {}, run_id=run2)
        cb._node_start_times[str(run2)] -= 0.2  # 200ms 전
        cb.on_chain_end({}, run_id=run2, tags=["emotion"])

        # 병렬이므로 tier1 = max(100, 200) = 200
        assert cb.metrics.tier_durations["tier1"] >= 200

    def test_unknown_node_uses_async_tier(self) -> None:
        """TIER 매핑에 없는 노드는 async로 분류된다."""
        cb = MindLogTelemetryCallback()
        run_id = uuid.uuid4()
        cb.on_chain_start({"name": "custom"}, {}, run_id=run_id)
        cb.on_chain_end({}, run_id=run_id, tags=["unknown_node"])

        assert "async" in cb.metrics.tier_durations

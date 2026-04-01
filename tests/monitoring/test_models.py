"""텔레메트리 데이터 모델 단위 테스트."""

from __future__ import annotations

import pytest

from src.monitoring.models import (
    AgentMetric,
    MonitoringEvent,
    PipelineMetrics,
    PipelineRunSummary,
    TierSummary,
)


class TestAgentMetric:
    """AgentMetric 데이터클래스 테스트."""

    @pytest.mark.parametrize(
        "kwargs, expected_status, expected_error",
        [
            (
                {"agent_name": "safety", "tier": 1, "duration_ms": 150, "llm_calls": 1},
                "ok",
                None,
            ),
            (
                {
                    "agent_name": "reasoning",
                    "tier": 1,
                    "duration_ms": 500,
                    "llm_calls": 2,
                    "status": "error",
                    "error_message": "LLM timeout",
                },
                "error",
                "LLM timeout",
            ),
        ],
        ids=["default_values", "error_metric"],
    )
    def test_agent_metric(self, kwargs, expected_status, expected_error) -> None:
        metric = AgentMetric(**kwargs)
        assert metric.status == expected_status
        assert metric.error_message == expected_error
        if expected_status == "ok":
            assert metric.input_tokens == 0
            assert metric.output_tokens == 0
            assert metric.model_id == ""


class TestPipelineMetrics:
    """PipelineMetrics 테스트."""

    def test_add_agent_metrics(self) -> None:
        """단일 + 복수 메트릭 추가 시 total_tokens와 agent_metrics 검증."""
        metrics = PipelineMetrics(run_id="run_001")
        metrics.add_agent_metric(
            AgentMetric(
                agent_name="safety",
                tier=1,
                duration_ms=100,
                llm_calls=1,
                input_tokens=500,
                output_tokens=200,
            )
        )
        assert metrics.total_tokens == 700
        assert len(metrics.agent_metrics) == 1

        metrics.add_agent_metric(
            AgentMetric("emotion", 1, 120, 1, input_tokens=400, output_tokens=150)
        )
        assert metrics.total_tokens == 1250
        assert len(metrics.agent_metrics) == 2

    def test_get_tier_summary(self) -> None:
        """정상 TIER 그룹화 + tier=None은 -1로 그룹화."""
        metrics = PipelineMetrics(run_id="run_003")
        metrics.add_agent_metric(
            AgentMetric("safety", 1, 100, 1, input_tokens=300, output_tokens=100)
        )
        metrics.add_agent_metric(
            AgentMetric("emotion", 1, 150, 1, input_tokens=400, output_tokens=200)
        )
        metrics.add_agent_metric(
            AgentMetric("synthesis", 2, 500, 2, input_tokens=800, output_tokens=400)
        )
        metrics.add_agent_metric(AgentMetric("telemetry", None, 50, 0))

        summaries = metrics.get_tier_summary()

        assert 1 in summaries
        assert 2 in summaries
        assert summaries[1].agent_count == 2
        assert summaries[1].duration_ms == 150  # max of parallel agents
        assert summaries[1].total_llm_calls == 2
        assert summaries[2].agent_count == 1
        # tier=None → -1
        assert -1 in summaries
        assert summaries[-1].agent_count == 1

    def test_finalize_sets_completed_at(self) -> None:
        metrics = PipelineMetrics(run_id="run_005")
        assert metrics.completed_at is None

        metrics.finalize()

        assert metrics.completed_at is not None
        assert metrics.total_duration_ms >= 0


class TestMonitoringEvent:
    """MonitoringEvent 테스트."""

    def test_event_creation(self) -> None:
        event = MonitoringEvent(
            event_type="crisis",
            session_id="sess_001",
            run_id="run_001",
            data={"agent": "safety", "risk_level": 4},
        )
        assert event.event_type == "crisis"
        assert event.data["risk_level"] == 4
        assert event.timestamp is not None


class TestPipelineRunSummary:
    """PipelineRunSummary 테스트."""

    def test_default_values(self) -> None:
        summary = PipelineRunSummary(run_id="run_001")
        assert summary.crisis_detected is False
        assert summary.retry_count == 0
        assert summary.final_status == ""
        assert summary.total_llm_calls == 0


class TestTierSummary:
    """TierSummary 테스트."""

    def test_default_agent_names(self) -> None:
        ts = TierSummary(tier=1, duration_ms=200, agent_count=3)
        assert ts.agent_names == []
        assert ts.total_llm_calls == 0

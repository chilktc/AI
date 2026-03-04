"""텔레메트리 데이터 모델 단위 테스트."""

from __future__ import annotations

from src.monitoring.models import (
    AgentMetric,
    MonitoringEvent,
    PipelineMetrics,
    PipelineRunSummary,
    TierSummary,
)


class TestAgentMetric:
    """AgentMetric 데이터클래스 테스트."""

    def test_default_values(self) -> None:
        metric = AgentMetric(
            agent_name="safety",
            tier=1,
            duration_ms=150,
            llm_calls=1,
        )
        assert metric.input_tokens == 0
        assert metric.output_tokens == 0
        assert metric.model_id == ""
        assert metric.status == "ok"
        assert metric.error_message is None

    def test_error_metric(self) -> None:
        metric = AgentMetric(
            agent_name="reasoning",
            tier=1,
            duration_ms=500,
            llm_calls=2,
            status="error",
            error_message="LLM timeout",
        )
        assert metric.status == "error"
        assert metric.error_message == "LLM timeout"


class TestPipelineMetrics:
    """PipelineMetrics 테스트."""

    def test_add_agent_metric_updates_total_tokens(self) -> None:
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

    def test_add_multiple_metrics(self) -> None:
        metrics = PipelineMetrics(run_id="run_002")
        metrics.add_agent_metric(
            AgentMetric("safety", 1, 100, 1, input_tokens=300, output_tokens=100)
        )
        metrics.add_agent_metric(
            AgentMetric("emotion", 1, 120, 1, input_tokens=400, output_tokens=150)
        )
        assert metrics.total_tokens == 950
        assert len(metrics.agent_metrics) == 2

    def test_get_tier_summary(self) -> None:
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

        summaries = metrics.get_tier_summary()

        assert 1 in summaries
        assert 2 in summaries
        assert summaries[1].agent_count == 2
        assert summaries[1].duration_ms == 150  # max of parallel agents
        assert summaries[1].total_llm_calls == 2
        assert summaries[2].agent_count == 1

    def test_get_tier_summary_none_tier(self) -> None:
        """tier=None인 에이전트는 -1로 그룹화된다."""
        metrics = PipelineMetrics(run_id="run_004")
        metrics.add_agent_metric(
            AgentMetric("telemetry", None, 50, 0)
        )

        summaries = metrics.get_tier_summary()
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

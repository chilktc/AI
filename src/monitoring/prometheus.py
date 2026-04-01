"""
Prometheus 메트릭 엔드포인트.

파이프라인 실행 성능을 Prometheus 포맷으로 노출한다.
GET /metrics 엔드포인트를 제공하며, Grafana에서 대시보드를 구성할 수 있다.

lazy-init 패턴: 메트릭 객체를 첫 사용 시에만 생성하여
이중 임포트나 테스트 환경에서의 레지스트리 충돌을 방지한다.

Zone A 담당자 인수 사항:
  - main.py에서 app.include_router(get_metrics_router()) 호출
  - MindLogTelemetryCallback.get_metrics() → MetricsCollector.record_pipeline() 연동

사용법:
    from src.monitoring.prometheus import MetricsCollector, get_metrics_router
    MetricsCollector.record_pipeline(pipeline_metrics)
    router = get_metrics_router()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest

if TYPE_CHECKING:
    from src.monitoring.models import AgentMetric, PipelineMetrics


class MetricsCollector:
    """Prometheus 메트릭 수집기.

    lazy-init 패턴으로 첫 호출 시에만 레지스트리에 메트릭을 등록한다.
    모든 메서드는 classmethod로 전역 상태를 관리한다.
    """

    _initialized: bool = False
    _requests_total: Counter | None = None
    _crisis_events_total: Counter | None = None
    _pipeline_duration: Histogram | None = None
    _agent_duration: Histogram | None = None
    _llm_tokens: Gauge | None = None

    @classmethod
    def _ensure_metrics(cls) -> None:
        """첫 호출 시에만 레지스트리에 등록 — 이중 임포트 안전."""
        if cls._initialized:
            return

        cls._requests_total = Counter(
            "mindlog_requests_total",
            "Total pipeline requests",
            ["mode", "status"],
        )
        cls._crisis_events_total = Counter(
            "mindlog_crisis_events_total",
            "Total crisis events detected",
        )
        cls._pipeline_duration = Histogram(
            "mindlog_pipeline_duration_seconds",
            "Pipeline execution duration",
            ["mode"],
            buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 15.0, 30.0, 60.0],
        )
        cls._agent_duration = Histogram(
            "mindlog_agent_duration_seconds",
            "Individual agent execution duration",
            ["agent", "tier"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        cls._llm_tokens = Gauge(
            "mindlog_llm_tokens_total",
            "Total LLM tokens used",
            ["direction"],
        )

        cls._initialized = True

    @classmethod
    def record_pipeline(cls, metrics: PipelineMetrics) -> None:
        """파이프라인 실행 메트릭을 기록한다.

        Args:
            metrics: MindLogTelemetryCallback.get_metrics()로 얻은 PipelineMetrics
        """
        cls._ensure_metrics()
        assert cls._requests_total is not None
        assert cls._pipeline_duration is not None
        assert cls._crisis_events_total is not None
        assert cls._llm_tokens is not None

        status = "crisis" if metrics.crisis_detected else "ok"
        cls._requests_total.labels(mode=metrics.mode, status=status).inc()

        cls._pipeline_duration.labels(mode=metrics.mode).observe(metrics.total_duration_ms / 1000)

        if metrics.crisis_detected:
            cls._crisis_events_total.inc()

        # 토큰 집계
        total_input = sum(a.input_tokens for a in metrics.agent_metrics)
        total_output = sum(a.output_tokens for a in metrics.agent_metrics)
        cls._llm_tokens.labels(direction="input").set(total_input)
        cls._llm_tokens.labels(direction="output").set(total_output)

        # 에이전트별 메트릭
        for agent_metric in metrics.agent_metrics:
            cls.record_agent(agent_metric)

    @classmethod
    def record_agent(cls, metric: AgentMetric) -> None:
        """개별 에이전트 실행 메트릭을 기록한다.

        Args:
            metric: AgentMetric 인스턴스
        """
        cls._ensure_metrics()
        assert cls._agent_duration is not None

        tier_label = str(metric.tier) if metric.tier is not None else "async"
        cls._agent_duration.labels(
            agent=metric.agent_name,
            tier=tier_label,
        ).observe(metric.duration_ms / 1000)


def get_metrics_router() -> APIRouter:
    """Prometheus 메트릭 엔드포인트 라우터를 반환한다.

    Zone A 담당자가 main.py에서 등록:
        app.include_router(get_metrics_router())
    """
    router = APIRouter(tags=["monitoring"])

    @router.get("/metrics")
    async def metrics() -> Response:
        """Prometheus 포맷 메트릭을 반환한다."""
        return Response(
            content=generate_latest(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return router

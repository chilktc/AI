"""텔레메트리 데이터 모델.

모니터링과 I/O 추적의 데이터를 정의한다.
MindLogTelemetryCallback과 AgentIOTracker가 이 모델을 사용하여
수집된 메트릭을 구조화한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentMetric:
    """개별 에이전트의 실행 메트릭."""

    agent_name: str
    tier: int | None
    duration_ms: int
    llm_calls: int
    input_tokens: int = 0
    output_tokens: int = 0
    prompt_version: str | None = None
    ab_variant: str | None = None
    model_id: str = ""
    status: str = "ok"  # ok | error | cancelled
    error_message: str | None = None


@dataclass
class TierSummary:
    """TIER별 실행 요약."""

    tier: int
    duration_ms: int
    agent_count: int
    agent_names: list[str] = field(default_factory=list)
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class PipelineMetrics:
    """파이프라인 전체 실행 메트릭.

    MindLogTelemetryCallback이 그래프 실행 동안 수집한
    TIER별, 에이전트별 성능 데이터를 통합한다.
    """

    run_id: str
    session_id: str = ""
    mode: str = ""  # podcast
    total_duration_ms: int = 0
    tier_durations: dict[str, int] = field(default_factory=dict)
    agent_metrics: list[AgentMetric] = field(default_factory=list)
    crisis_detected: bool = False
    retry_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def add_agent_metric(self, metric: AgentMetric) -> None:
        """에이전트 메트릭을 추가하고 합산 토큰을 갱신한다."""
        self.agent_metrics.append(metric)
        self.total_tokens += metric.input_tokens + metric.output_tokens

    def get_tier_summary(self) -> dict[int, TierSummary]:
        """TIER별 요약을 생성한다."""
        summaries: dict[int, TierSummary] = {}
        for m in self.agent_metrics:
            tier = m.tier if m.tier is not None else -1
            if tier not in summaries:
                summaries[tier] = TierSummary(
                    tier=tier,
                    duration_ms=0,
                    agent_count=0,
                )
            s = summaries[tier]
            s.agent_count += 1
            s.agent_names.append(m.agent_name)
            s.duration_ms = max(s.duration_ms, m.duration_ms)  # 병렬 → max
            s.total_llm_calls += m.llm_calls
            s.total_input_tokens += m.input_tokens
            s.total_output_tokens += m.output_tokens
        return summaries

    def finalize(self) -> None:
        """실행 완료 시 최종 집계를 수행한다."""
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.total_duration_ms = int(delta.total_seconds() * 1000)


@dataclass
class MonitoringEvent:
    """통합 모니터링 이벤트.

    파이프라인 실행, 에이전트 실행, CRISIS 등
    다양한 이벤트를 단일 포맷으로 기록한다.
    """

    event_type: str  # pipeline_run | agent_execution | crisis
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str = ""
    run_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRunSummary:
    """파이프라인 실행 요약 (대시보드 렌더링용)."""

    run_id: str
    session_id: str = ""
    mode: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    total_duration_ms: int = 0

    # TIER별 요약
    tier_summaries: dict[int, TierSummary] = field(default_factory=dict)

    # 전체 요약
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    # 결과
    crisis_detected: bool = False
    retry_count: int = 0
    final_status: str = ""  # success | crisis_response | error

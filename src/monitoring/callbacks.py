"""LangGraph 텔레메트리 콜백 핸들러.

LangGraph StateGraph 실행 시 콜백으로 TIER별 성능 메트릭을 수집한다.
노드 진입/완료 시점을 자동 추적하여 파이프라인 병목 분석에 활용한다.

사용 예시:
    callback = MindLogTelemetryCallback()
    result = await compiled.ainvoke(
        state,
        config={"callbacks": [callback]}
    )
    metrics = callback.get_metrics()
    print(f"총 실행 시간: {metrics.total_duration_ms}ms")
    print(f"CRISIS 감지: {metrics.crisis_detected}")
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.monitoring.models import AgentMetric, MonitoringEvent, PipelineMetrics
from src.utils.logger import get_agent_logger

logger = get_agent_logger("callbacks")


# 에이전트별 TIER 매핑 — 노드 이름으로 TIER 판별
_NODE_TIER_MAP: dict[str, int] = {
    "intent_classifier": 0,
    "tier1_podcast": 1,
    "safety": 1,
    "emotion": 1,
    "context": 1,
    "reasoning": 1,
    "content_analyzer": 1,
    "podcast_reasoning": 1,
    "synthesis": 2,
    "script_generator": 2,
    "visualization": 2,
    "validator": 3,
    "batch_validator": 3,
    "personalization": 4,
    "script_personalizer": 4,
}

# 모델별 비용 (USD per 1M tokens) — 2026-02 기준 Anthropic 공식 가격.
# 가격 변경 시 이 dict를 갱신해야 정확한 비용 추정이 가능하다.
_MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """모델 ID와 토큰 수로 비용(USD)을 추정한다."""
    for model_key, costs in _MODEL_COSTS.items():
        if model_key in model_id:
            return (
                input_tokens * costs["input"] / 1_000_000
                + output_tokens * costs["output"] / 1_000_000
            )
    return 0.0


class MindLogTelemetryCallback(BaseCallbackHandler):
    """TIER별 실행 메트릭을 수집하는 LangGraph 콜백 핸들러.

    LangGraph 그래프 실행 시 config에 포함하면 자동으로
    노드별 실행 시간, CRISIS 이벤트, 재시도 횟수를 추적한다.

    Attributes:
        metrics: 수집된 파이프라인 메트릭
        events: 수집된 모니터링 이벤트 목록
    """

    def __init__(self, session_id: str = "", mode: str = "", request_id: str = "") -> None:
        super().__init__()
        self._run_id = str(uuid.uuid4())
        self._node_start_times: dict[str, float] = {}
        self._events: list[MonitoringEvent] = []
        self.metrics = PipelineMetrics(
            run_id=self._run_id,
            session_id=session_id,
            mode=mode,
            request_id=request_id,
        )

    @property
    def events(self) -> list[MonitoringEvent]:
        """수집된 모니터링 이벤트 목록."""
        return self._events

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: Any,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """노드 실행 시작을 기록한다."""
        serialized = serialized or {}
        node_name = serialized.get("name", str(run_id))
        self._node_start_times[str(run_id)] = time.monotonic()

        # 세션/모드 정보 자동 추출
        if metadata:
            if not self.metrics.session_id and "session_id" in metadata:
                self.metrics.session_id = str(metadata["session_id"])
            if not self.metrics.mode and "mode" in metadata:
                self.metrics.mode = str(metadata["mode"])

        logger.debug("[Telemetry] 노드 시작: %s (run_id=%s)", node_name, run_id)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: Any,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """노드 실행 완료를 기록하고 메트릭을 수집한다."""
        start = self._node_start_times.pop(str(run_id), None)
        if start is None:
            return

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # 태그에서 노드 정보 추출
        node_name = "unknown"
        tier: int | None = None
        if tags:
            for tag in tags:
                if tag in _NODE_TIER_MAP:
                    node_name = tag
                    tier = _NODE_TIER_MAP[tag]
                    break

        # TIER 타이밍 기록
        tier_key = f"tier{tier}" if tier is not None else "async"
        current = self.metrics.tier_durations.get(tier_key, 0)
        self.metrics.tier_durations[tier_key] = max(current, elapsed_ms)

        # CRISIS 감지 확인
        if isinstance(outputs, dict):
            safety_flags = outputs.get("safety_flags", {})
            if isinstance(safety_flags, dict) and safety_flags.get("status") == "crisis":
                self.metrics.crisis_detected = True
                self._events.append(
                    MonitoringEvent(
                        event_type="crisis",
                        session_id=self.metrics.session_id,
                        run_id=self._run_id,
                        data={
                            "agent": node_name,
                            "risk_level": outputs.get("risk_level", 0),
                            "elapsed_ms": elapsed_ms,
                        },
                    )
                )

            # 재시도 카운터 추적
            iteration = outputs.get("iteration_count")
            if iteration is not None and isinstance(iteration, int):
                self.metrics.retry_count = max(self.metrics.retry_count, iteration)

        logger.debug(
            "[Telemetry] 노드 완료: %s (%dms, tier=%s)",
            node_name,
            elapsed_ms,
            tier,
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> None:
        """노드 실행 실패를 기록한다."""
        start = self._node_start_times.pop(str(run_id), None)
        elapsed_ms = int((time.monotonic() - start) * 1000) if start else 0

        self._events.append(
            MonitoringEvent(
                event_type="agent_execution",
                session_id=self.metrics.session_id,
                run_id=self._run_id,
                data={
                    "status": "error",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:500],
                    "elapsed_ms": elapsed_ms,
                },
            )
        )
        logger.warning("[Telemetry] 노드 에러: %s — %s", type(error).__name__, str(error)[:200])

    def add_agent_metric(self, metric: AgentMetric) -> None:
        """외부에서 수집된 에이전트 메트릭을 추가한다.

        BaseAgent.get_execution_metrics()로 수집된 데이터를
        AgentMetric으로 변환하여 전달하면 파이프라인 메트릭에 통합된다.
        """
        self.metrics.add_agent_metric(metric)

        # 비용 추정
        cost = _estimate_cost(metric.model_id, metric.input_tokens, metric.output_tokens)
        self.metrics.total_cost_usd += cost

    def get_metrics(self) -> PipelineMetrics:
        """수집된 파이프라인 메트릭을 반환한다."""
        self.metrics.finalize()
        return self.metrics

    def get_summary(self) -> dict[str, Any]:
        """사람이 읽을 수 있는 요약 dict를 반환한다."""
        m = self.get_metrics()
        return {
            "run_id": m.run_id,
            "request_id": m.request_id,
            "session_id": m.session_id,
            "mode": m.mode,
            "total_duration_ms": m.total_duration_ms,
            "tier_durations": m.tier_durations,
            "agent_count": len(m.agent_metrics),
            "total_llm_calls": sum(a.llm_calls for a in m.agent_metrics),
            "total_tokens": m.total_tokens,
            "estimated_cost_usd": round(m.total_cost_usd, 6),
            "crisis_detected": m.crisis_detected,
            "retry_count": m.retry_count,
            "errors": [
                {"agent": a.agent_name, "error": a.error_message}
                for a in m.agent_metrics
                if a.status == "error"
            ],
        }

"""에이전트 I/O 트래커.

각 에이전트의 입출력을 체계적으로 캡처하여
파이프라인 데이터 흐름을 추적한다.

멘탈케어 데이터 특성상 사용자 원문은 해시/마스킹 처리하며,
스냅샷 크기는 설정의 io_snapshot_max_chars로 제한한다.

사용 예시:
    tracker = AgentIOTracker(session_id="sess_123")
    snap_id = tracker.capture_input("safety", state, run_id="run_456")
    # ... agent 실행 ...
    tracker.capture_output("safety", result, snap_id, duration_ms=120)
    trace = tracker.get_pipeline_trace()
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class IOSnapshot:
    """에이전트 실행의 입출력 스냅샷."""

    snapshot_id: str
    agent_name: str
    tier: int | None
    run_id: str
    session_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 입력 (읽은 AgentState 필드들)
    input_fields: dict[str, Any] = field(default_factory=dict)

    # 출력 (변경한 AgentState 필드들)
    output_fields: dict[str, Any] = field(default_factory=dict)

    # 메타데이터
    duration_ms: int = 0
    llm_calls: int = 0
    token_usage: dict[str, int] | None = None
    prompt_version: str | None = None
    ab_variant: str | None = None
    status: str = "ok"  # ok | error | cancelled


@dataclass
class PipelineTrace:
    """파이프라인 전체의 에이전트 간 데이터 흐름."""

    session_id: str
    snapshots: list[IOSnapshot] = field(default_factory=list)

    @property
    def agent_names(self) -> list[str]:
        """실행된 에이전트 이름 목록 (순서대로)."""
        return [s.agent_name for s in self.snapshots]

    @property
    def total_duration_ms(self) -> int:
        """전체 실행 시간 (첫 입력 ~ 마지막 출력)."""
        return sum(s.duration_ms for s in self.snapshots)

    def get_data_flow(self) -> list[dict[str, Any]]:
        """에이전트 간 데이터 흐름을 시각화용 dict로 반환한다."""
        flow = []
        for snap in self.snapshots:
            flow.append({
                "agent": snap.agent_name,
                "tier": snap.tier,
                "input_keys": list(snap.input_fields.keys()),
                "output_keys": list(snap.output_fields.keys()),
                "duration_ms": snap.duration_ms,
                "status": snap.status,
            })
        return flow


class AgentIOTracker:
    """에이전트별 입출력 캡처 및 분석.

    파이프라인 실행 전에 인스턴스를 생성하고,
    각 에이전트 실행 전후에 capture_input/capture_output을 호출한다.

    Args:
        session_id: 세션 ID
        max_chars: 문자열 값의 최대 길이 (민감정보 보호)
    """

    def __init__(self, session_id: str, max_chars: int = 2000) -> None:
        self._session_id = session_id
        self._max_chars = max_chars
        self._snapshots: list[IOSnapshot] = []
        self._pending: dict[str, IOSnapshot] = {}  # snapshot_id → 미완성 스냅샷

    def capture_input(
        self,
        agent_name: str,
        state: dict[str, Any],
        run_id: str,
        tier: int | None = None,
    ) -> str:
        """에이전트 실행 전 입력 상태를 스냅샷한다.

        Args:
            agent_name: 에이전트 이름
            state: 현재 AgentState (dict)
            run_id: 파이프라인 실행 ID
            tier: TIER 레벨

        Returns:
            snapshot_id (capture_output에서 매칭용)
        """
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        snapshot = IOSnapshot(
            snapshot_id=snapshot_id,
            agent_name=agent_name,
            tier=tier,
            run_id=run_id,
            session_id=self._session_id,
            input_fields=self._sanitize(state),
        )
        self._pending[snapshot_id] = snapshot
        return snapshot_id

    def capture_output(
        self,
        agent_name: str,
        result: dict[str, Any],
        snapshot_id: str,
        duration_ms: int,
        llm_calls: int = 0,
        token_usage: dict[str, int] | None = None,
        prompt_version: str | None = None,
        ab_variant: str | None = None,
        status: str = "ok",
    ) -> None:
        """에이전트 실행 후 출력 결과를 스냅샷에 기록한다.

        Args:
            agent_name: 에이전트 이름
            result: process()가 반환한 dict
            snapshot_id: capture_input에서 반환된 ID
            duration_ms: 실행 시간 (ms)
            llm_calls: LLM 호출 횟수
            token_usage: 토큰 사용량 dict
            prompt_version: 프롬프트 버전
            ab_variant: A/B variant
            status: 실행 상태 (ok | error | cancelled)
        """
        snapshot = self._pending.pop(snapshot_id, None)
        if snapshot is None:
            # capture_input 없이 호출된 경우 새 스냅샷 생성
            snapshot = IOSnapshot(
                snapshot_id=snapshot_id,
                agent_name=agent_name,
                tier=None,
                run_id="",
                session_id=self._session_id,
            )

        snapshot.output_fields = self._sanitize(result)
        snapshot.duration_ms = duration_ms
        snapshot.llm_calls = llm_calls
        snapshot.token_usage = token_usage
        snapshot.prompt_version = prompt_version
        snapshot.ab_variant = ab_variant
        snapshot.status = status

        self._snapshots.append(snapshot)

    def get_agent_io_history(self, agent_name: str) -> list[IOSnapshot]:
        """특정 에이전트의 I/O 이력을 반환한다."""
        return [s for s in self._snapshots if s.agent_name == agent_name]

    def get_pipeline_trace(self) -> PipelineTrace:
        """전체 파이프라인의 데이터 흐름 추적을 반환한다."""
        return PipelineTrace(
            session_id=self._session_id,
            snapshots=list(self._snapshots),
        )

    def get_all_snapshots(self) -> list[IOSnapshot]:
        """수집된 모든 스냅샷을 반환한다."""
        return list(self._snapshots)

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        """민감정보를 마스킹하고 크기를 제한한다."""
        sanitized: dict[str, Any] = {}
        for key, value in data.items():
            if key == "user_input":
                # 사용자 원문은 해시로 대체 (민감정보 보호)
                text = str(value)
                sanitized[key] = {
                    "_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                    "_len": len(text),
                }
            elif isinstance(value, str) and len(value) > self._max_chars:
                sanitized[key] = value[: self._max_chars] + "...<truncated>"
            elif isinstance(value, dict):
                sanitized[key] = {
                    "_keys": list(value.keys()),
                    "_size": len(value),
                }
            else:
                sanitized[key] = value
        return sanitized

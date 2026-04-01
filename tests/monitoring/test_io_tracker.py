"""에이전트 I/O 트래커 단위 테스트."""

from __future__ import annotations

import pytest

from src.monitoring.io_tracker import AgentIOTracker, IOSnapshot, PipelineTrace


class TestIOSnapshot:
    """IOSnapshot 데이터클래스 테스트."""

    def test_default_values(self) -> None:
        snap = IOSnapshot(
            snapshot_id="snap_001",
            agent_name="safety",
            tier=1,
            run_id="run_001",
            session_id="sess_001",
        )
        assert snap.input_fields == {}
        assert snap.output_fields == {}
        assert snap.duration_ms == 0
        assert snap.status == "ok"
        assert snap.token_usage is None


class TestPipelineTrace:
    """PipelineTrace 테스트."""

    def test_agent_names(self) -> None:
        trace = PipelineTrace(
            session_id="sess_001",
            snapshots=[
                IOSnapshot("s1", "safety", 1, "r1", "sess_001"),
                IOSnapshot("s2", "emotion", 1, "r1", "sess_001"),
                IOSnapshot("s3", "synthesis", 2, "r1", "sess_001"),
            ],
        )
        assert trace.agent_names == ["safety", "emotion", "synthesis"]

    def test_total_duration_ms(self) -> None:
        s1 = IOSnapshot("s1", "safety", 1, "r1", "sess_001")
        s1.duration_ms = 100
        s2 = IOSnapshot("s2", "emotion", 1, "r1", "sess_001")
        s2.duration_ms = 150

        trace = PipelineTrace(session_id="sess_001", snapshots=[s1, s2])
        assert trace.total_duration_ms == 250

    def test_get_data_flow(self) -> None:
        s1 = IOSnapshot("s1", "safety", 1, "r1", "sess_001")
        s1.input_fields = {"user_input": "...", "mode": "conversation"}
        s1.output_fields = {"safety_flags": {}, "risk_level": 0}
        s1.duration_ms = 100

        trace = PipelineTrace(session_id="sess_001", snapshots=[s1])
        flow = trace.get_data_flow()

        assert len(flow) == 1
        assert flow[0]["agent"] == "safety"
        assert flow[0]["tier"] == 1
        assert flow[0]["input_keys"] == ["user_input", "mode"]
        assert flow[0]["output_keys"] == ["safety_flags", "risk_level"]
        assert flow[0]["duration_ms"] == 100
        assert flow[0]["status"] == "ok"


class TestAgentIOTracker:
    """AgentIOTracker 테스트."""

    def test_capture_input_returns_snapshot_id(self) -> None:
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input(
            "safety", {"user_input": "테스트", "mode": "conversation"}, run_id="run_001"
        )
        assert snap_id.startswith("snap_")

    def test_capture_output_completes_snapshot(self) -> None:
        """capture_output이 스냅샷을 완료하고 메타데이터를 저장한다.

        메타데이터: token_usage, prompt_version 등.
        """
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input(
            "safety",
            {"user_input": "테스트"},
            run_id="run_001",
            tier=1,
        )
        tracker.capture_output(
            "safety",
            {"safety_flags": {"status": "safe"}, "risk_level": 0},
            snap_id,
            duration_ms=120,
            llm_calls=1,
            status="ok",
            token_usage={"input_tokens": 500, "output_tokens": 200},
            prompt_version="v3.2",
            ab_variant="variant_b",
        )

        snapshots = tracker.get_all_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].agent_name == "safety"
        assert snapshots[0].tier == 1
        assert snapshots[0].duration_ms == 120
        assert "safety_flags" in snapshots[0].output_fields
        # 메타데이터 검증
        assert snapshots[0].token_usage == {"input_tokens": 500, "output_tokens": 200}
        assert snapshots[0].prompt_version == "v3.2"
        assert snapshots[0].ab_variant == "variant_b"

    def test_capture_output_without_input_creates_new_snapshot(self) -> None:
        """capture_input 없이 capture_output 호출 시 새 스냅샷 생성."""
        tracker = AgentIOTracker(session_id="sess_001")
        tracker.capture_output(
            "telemetry",
            {"metrics": {}},
            "snap_orphan",
            duration_ms=50,
        )

        snapshots = tracker.get_all_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].agent_name == "telemetry"

    def test_get_agent_io_history(self) -> None:
        tracker = AgentIOTracker(session_id="sess_001")

        # safety 에이전트
        s1 = tracker.capture_input("safety", {"user_input": "a"}, run_id="r1")
        tracker.capture_output("safety", {"risk_level": 0}, s1, duration_ms=100)

        # emotion 에이전트
        s2 = tracker.capture_input("emotion", {"user_input": "a"}, run_id="r1")
        tracker.capture_output("emotion", {"emotion_vectors": {}}, s2, duration_ms=80)

        safety_history = tracker.get_agent_io_history("safety")
        assert len(safety_history) == 1
        assert safety_history[0].agent_name == "safety"

        emotion_history = tracker.get_agent_io_history("emotion")
        assert len(emotion_history) == 1

    def test_get_pipeline_trace(self) -> None:
        tracker = AgentIOTracker(session_id="sess_001")

        s1 = tracker.capture_input("safety", {}, run_id="r1")
        tracker.capture_output("safety", {"risk_level": 0}, s1, duration_ms=100)
        s2 = tracker.capture_input("emotion", {}, run_id="r1")
        tracker.capture_output("emotion", {"emotion_vectors": {}}, s2, duration_ms=80)

        trace = tracker.get_pipeline_trace()
        assert isinstance(trace, PipelineTrace)
        assert trace.session_id == "sess_001"
        assert len(trace.snapshots) == 2
        assert trace.total_duration_ms == 180

    @pytest.mark.parametrize(
        "agent, input_fields, max_chars, field_key, check",
        [
            (
                "safety",
                {"user_input": "민감한 사용자 입력", "mode": "conversation"},
                500,
                "user_input",
                lambda v: isinstance(v, dict) and "_hash" in v and "_len" in v,
            ),
            (
                "context",
                {"context": "x" * 200},
                100,
                "context",
                lambda v: isinstance(v, str) and v.endswith("...<truncated>"),
            ),
            (
                "reasoning",
                {"reasoning_result": {"key1": "v1", "key2": "v2", "key3": "v3"}},
                500,
                "reasoning_result",
                lambda v: isinstance(v, dict) and "_keys" in v and v["_size"] == 3,
            ),
        ],
        ids=["user_input_hashed", "long_string_truncated", "dict_summarized"],
    )
    def test_sanitize_input_fields(
        self,
        agent: str,
        input_fields: dict,
        max_chars: int,
        field_key: str,
        check,
    ) -> None:
        """입력 필드 유형별 정제(해시/truncation/요약)를 검증."""
        tracker = AgentIOTracker(session_id="sess_001", max_chars=max_chars)
        snap_id = tracker.capture_input(agent, input_fields, run_id="r1")
        tracker.capture_output(agent, {}, snap_id, duration_ms=50)

        snap = tracker.get_all_snapshots()[0]
        assert check(snap.input_fields[field_key])

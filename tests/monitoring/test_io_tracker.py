"""에이전트 I/O 트래커 단위 테스트."""

from __future__ import annotations

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
        )

        snapshots = tracker.get_all_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].agent_name == "safety"
        assert snapshots[0].tier == 1
        assert snapshots[0].duration_ms == 120
        assert "safety_flags" in snapshots[0].output_fields

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

    def test_sanitize_user_input_is_hashed(self) -> None:
        """user_input 필드는 해시로 대체된다."""
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input(
            "safety",
            {"user_input": "민감한 사용자 입력", "mode": "conversation"},
            run_id="r1",
        )
        tracker.capture_output("safety", {}, snap_id, duration_ms=50)

        snap = tracker.get_all_snapshots()[0]
        assert isinstance(snap.input_fields["user_input"], dict)
        assert "_hash" in snap.input_fields["user_input"]
        assert "_len" in snap.input_fields["user_input"]

    def test_sanitize_long_string_truncated(self) -> None:
        """긴 문자열은 truncation된다."""
        tracker = AgentIOTracker(session_id="sess_001", max_chars=100)
        long_text = "x" * 200
        snap_id = tracker.capture_input(
            "context", {"context": long_text}, run_id="r1"
        )
        tracker.capture_output("context", {}, snap_id, duration_ms=50)

        snap = tracker.get_all_snapshots()[0]
        assert snap.input_fields["context"].endswith("...<truncated>")
        assert len(snap.input_fields["context"]) == 100 + len("...<truncated>")

    def test_sanitize_dict_value_summarized(self) -> None:
        """dict 값은 키 목록과 크기로 요약된다."""
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input(
            "reasoning",
            {"reasoning_result": {"key1": "v1", "key2": "v2", "key3": "v3"}},
            run_id="r1",
        )
        tracker.capture_output("reasoning", {}, snap_id, duration_ms=50)

        snap = tracker.get_all_snapshots()[0]
        summarized = snap.input_fields["reasoning_result"]
        assert "_keys" in summarized
        assert "_size" in summarized
        assert summarized["_size"] == 3

    def test_token_usage_stored(self) -> None:
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input("safety", {}, run_id="r1")
        tracker.capture_output(
            "safety",
            {},
            snap_id,
            duration_ms=100,
            token_usage={"input_tokens": 500, "output_tokens": 200},
        )

        snap = tracker.get_all_snapshots()[0]
        assert snap.token_usage == {"input_tokens": 500, "output_tokens": 200}

    def test_prompt_version_and_ab_variant(self) -> None:
        tracker = AgentIOTracker(session_id="sess_001")
        snap_id = tracker.capture_input("safety", {}, run_id="r1")
        tracker.capture_output(
            "safety",
            {},
            snap_id,
            duration_ms=100,
            prompt_version="v3.2",
            ab_variant="variant_b",
        )

        snap = tracker.get_all_snapshots()[0]
        assert snap.prompt_version == "v3.2"
        assert snap.ab_variant == "variant_b"

"""
SSE 스트리밍 엔드포인트 테스트.

POST /api/v1/podcasts/episodes/stream — SSE 실시간 스트리밍 검증.
compiled_graph.astream()을 mock하여 파이프라인 없이 SSE 이벤트 시퀀스를 테스트.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _valid_request(**overrides: Any) -> dict[str, Any]:
    """유효한 PodcastRequest body 생성."""
    base = {
        "user_id": "test_user_001",
        "session_id": "sess_sse_test",
        "situation": "직장에서 스트레스를 받고 있어",
        "thought": "어떻게 해결해야 할지 모르겠어",
        "action": "참고 있는 중이야",
    }
    base.update(overrides)
    return base


def _make_pipeline_state() -> dict[str, Any]:
    """astream updates 모드로 전달할 파이프라인 최종 상태."""
    return {
        "final_output": json.dumps(
            {
                "episode_id": "ep_sse_001",
                "episode_title": "SSE 테스트 에피소드",
                "total_duration": 3,
                "segments": [
                    {
                        "segment_id": "seg_01",
                        "segment_type": "intro",
                        "duration_minutes": 1,
                        "script_text": "안녕하세요, SSE 테스트입니다.",
                        "word_count": 8,
                        "emotional_tone": "warm",
                        "tts_markers": [],
                    }
                ],
                "key_insights": ["테스트"],
                "themes": ["테스트"],
            }
        ),
        "emotion_vectors": {
            "primary_emotion": "calm",
            "intensity": 0.5,
            "valence": 0.3,
        },
        "safety_flags": {"status": "safe"},
        "visual_data": None,
        "intent": {"intent_type": "topic_exploration", "complexity_score": 0.5},
        "reasoning_result": {"depth_level": "standard"},
        "iteration_count": 0,
    }


async def _fake_astream(initial_state, config=None, stream_mode=None):
    """compiled_graph.astream() mock — updates + custom 이벤트를 yield."""
    # custom 이벤트: tier_start
    yield ("custom", {"event": "tier_start", "tier": 0, "tier_name": "Intent Classification"})

    # custom 이벤트: agent_complete
    yield ("custom", {"event": "agent_complete", "agent": "intent_classifier", "tier": 0})

    # updates 이벤트: 파이프라인 결과
    state = _make_pipeline_state()
    yield ("updates", {"script_personalizer": state})

    # custom 이벤트: tier_end
    yield ("custom", {"event": "tier_end", "tier": 4})


async def _fake_astream_empty(initial_state, config=None, stream_mode=None):
    """아무 이벤트 없이 종료하는 astream mock."""
    state = _make_pipeline_state()
    yield ("updates", {"final_node": state})


async def _fake_astream_error(initial_state, config=None, stream_mode=None):
    """스트리밍 중 예외를 발생시키는 astream mock."""
    yield ("custom", {"event": "tier_start", "tier": 0})
    raise RuntimeError("파이프라인 실행 중 오류")


def _parse_sse_events(response_text: str) -> list[dict]:
    """SSE 응답 텍스트에서 data: 줄을 파싱하여 이벤트 리스트를 반환한다."""
    events = []
    for line in response_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_compiled_graph_sse():
    """astream이 포함된 compiled_graph mock."""
    mock = MagicMock()
    mock.astream = MagicMock(side_effect=_fake_astream)
    mock.ainvoke = AsyncMock(return_value={})
    return mock


@pytest.fixture
def sse_test_client(mock_compiled_graph_sse):
    """SSE 테스트용 FastAPI TestClient."""
    mock_backend = AsyncMock()
    mock_backend.close = AsyncMock()
    mock_backend._base_url = "http://mock-backend:8080/api/v1"

    with (
        patch("src.api.main.compiled_graph", mock_compiled_graph_sse),
        patch("src.api.main.backend_client", mock_backend),
        patch("src.api.routes.health.compiled_graph", mock_compiled_graph_sse, create=True),
        patch("src.api.routes.health.backend_client", mock_backend, create=True),
        patch("src.api.routes.podcasts._save_core_data", new_callable=AsyncMock),
    ):
        from fastapi.testclient import TestClient

        from src.api.main import app

        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


class TestSSEStreamEndpoint:
    """POST /api/v1/podcasts/episodes/stream SSE 스트리밍 테스트."""

    def test_sse_response_content_type(self, sse_test_client) -> None:
        """SSE 응답의 Content-Type이 text/event-stream이다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_sse_response_cache_headers(self, sse_test_client) -> None:
        """SSE 응답에 캐시 비활성화 헤더가 포함된다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        assert response.headers.get("cache-control") == "no-cache"

    def test_sse_event_sequence_starts_with_connected(self, sse_test_client) -> None:
        """첫 번째 이벤트는 항상 connected이다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        assert len(events) >= 1
        assert events[0]["event"] == "connected"
        assert events[0]["session_id"] == "sess_sse_test"

    def test_sse_event_sequence_ends_with_done(self, sse_test_client) -> None:
        """마지막 이벤트는 항상 done이다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        assert len(events) >= 2
        assert events[-1]["event"] == "done"

    def test_sse_contains_custom_tier_events(self, sse_test_client) -> None:
        """custom 모드 이벤트(tier_start, agent_complete, tier_end)가 전달된다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        assert "tier_start" in event_types
        assert "agent_complete" in event_types
        assert "tier_end" in event_types

    def test_sse_contains_result_event(self, sse_test_client) -> None:
        """result 이벤트에 episode_id와 session_id가 포함된다."""
        response = sse_test_client.post(
            "/api/v1/postcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        result_events = [e for e in events if e.get("event") == "result"]

        # 경로 오타 시 404이므로 올바른 경로로 재테스트
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        result_events = [e for e in events if e.get("event") == "result"]

        assert len(result_events) == 1
        result_data = result_events[0]["data"]
        assert "episode_id" in result_data
        assert result_data["session_id"] == "sess_sse_test"

    def test_sse_custom_events_have_timestamp(self, sse_test_client) -> None:
        """custom 이벤트에는 timestamp가 추가된다."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        tier_events = [e for e in events if e.get("event") == "tier_start"]

        assert len(tier_events) >= 1
        assert "timestamp" in tier_events[0]

    def test_sse_full_event_order(self, sse_test_client) -> None:
        """이벤트 순서: connected → (custom 이벤트들) → result → done."""
        response = sse_test_client.post(
            "/api/v1/podcasts/episodes/stream",
            json=_valid_request(),
        )
        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        # connected가 첫 번째
        assert event_types[0] == "connected"
        # done이 마지막
        assert event_types[-1] == "done"
        # result가 done 직전
        assert event_types[-2] == "result"


class TestSSEStreamError:
    """SSE 스트리밍 에러 핸들링 테스트."""

    def test_sse_pipeline_error_returns_error_event(self, mock_compiled_graph_sse) -> None:
        """파이프라인 오류 시 error 이벤트를 전송하고 done으로 종료한다."""
        mock_compiled_graph_sse.astream = MagicMock(side_effect=_fake_astream_error)

        mock_backend = AsyncMock()
        mock_backend.close = AsyncMock()
        mock_backend._base_url = "http://mock-backend:8080/api/v1"

        with (
            patch("src.api.main.compiled_graph", mock_compiled_graph_sse),
            patch("src.api.main.backend_client", mock_backend),
            patch("src.api.routes.health.compiled_graph", mock_compiled_graph_sse, create=True),
            patch("src.api.routes.health.backend_client", mock_backend, create=True),
            patch("src.api.routes.podcasts._save_core_data", new_callable=AsyncMock),
        ):
            from fastapi.testclient import TestClient

            from src.api.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/podcasts/episodes/stream",
                json=_valid_request(),
            )

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        assert "error" in event_types
        assert event_types[-1] == "done"

    def test_sse_graph_none_returns_error_event(self) -> None:
        """compiled_graph=None 시 error 이벤트가 전송된다."""
        mock_backend = AsyncMock()
        mock_backend.close = AsyncMock()
        mock_backend._base_url = "http://mock-backend:8080/api/v1"

        with (
            patch("src.api.main.compiled_graph", None),
            patch("src.api.main.backend_client", mock_backend),
            patch("src.api.routes.health.compiled_graph", None, create=True),
            patch("src.api.routes.health.backend_client", mock_backend, create=True),
        ):
            from fastapi.testclient import TestClient

            from src.api.main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post(
                "/api/v1/podcasts/episodes/stream",
                json=_valid_request(),
            )

        events = _parse_sse_events(response.text)
        event_types = [e["event"] for e in events]

        assert "connected" in event_types
        assert "error" in event_types
        assert event_types[-1] == "done"

    def test_sse_invalid_request_returns_422(self) -> None:
        """필수 필드 누락 시 422 Validation Error를 반환한다."""
        mock_graph = MagicMock()
        mock_backend = AsyncMock()
        mock_backend.close = AsyncMock()
        mock_backend._base_url = "http://mock-backend:8080/api/v1"

        with (
            patch("src.api.main.compiled_graph", mock_graph),
            patch("src.api.main.backend_client", mock_backend),
            patch("src.api.routes.health.compiled_graph", mock_graph, create=True),
            patch("src.api.routes.health.backend_client", mock_backend, create=True),
        ):
            from fastapi.testclient import TestClient

            from src.api.main import app

            client = TestClient(app, raise_server_exceptions=False)
            # situation 필드 누락
            response = client.post(
                "/api/v1/podcasts/episodes/stream",
                json={"user_id": "u1", "session_id": "s1"},
            )

        assert response.status_code == 422

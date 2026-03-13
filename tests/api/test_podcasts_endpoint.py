"""
Podcasts 엔드포인트 테스트.

POST /api/v1/podcasts/episodes (팟캐스트 에피소드 생성) 검증.
compiled_graph를 mock하여 파이프라인 없이 엔드포인트 매핑 로직을 테스트.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.api.conftest import make_pipeline_result


class TestCreatePodcastEpisode:
    """POST /api/v1/podcasts/episodes 엔드포인트 테스트."""

    def _valid_request(self, **overrides: Any) -> dict[str, Any]:
        """유효한 PodcastRequest 생성 헬퍼."""
        base = {
            "user_id": "test_user_001",
            "session_id": "sess_test123",
            "topic": "스트레스 관리법",
        }
        base.update(overrides)
        return base

    def test_create_episode_success(self, test_client, mock_compiled_graph) -> None:
        """유효한 요청으로 에피소드 생성 시 200 반환."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "episode" in data
        assert "metadata" in data

    def test_create_episode_response_structure(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """응답 구조가 PodcastEpisodeResponse 스키마에 맞는지 확인."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        # 필수 최상위 필드
        assert "episode" in data
        assert "emotion" in data
        assert "metadata" in data
        assert "tracing" in data

        # episode 내부
        episode = data["episode"]
        assert "episode_id" in episode
        assert "episode_title" in episode
        assert "segments" in episode

    def test_create_episode_state_mapping(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """topic + description → user_input, mode=podcast 매핑 확인."""
        test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(description="상세 설명입니다"),
        )

        # ainvoke 호출 인자 확인
        call_args = mock_compiled_graph.ainvoke.call_args
        state = call_args[0][0]  # 첫 번째 위치 인자

        assert state["user_input"] == "스트레스 관리법 - 상세 설명입니다"
        assert state["mode"] == "podcast"
        assert state["user_id"] == "test_user_001"
        assert state["session_id"] == "sess_test123"

    def test_create_episode_graph_invoked_with_config(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """compiled_graph.ainvoke가 올바른 config로 호출되었는지 확인."""
        test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        call_args = mock_compiled_graph.ainvoke.call_args
        config = call_args[1].get("config") or call_args[0][1]

        assert config["configurable"]["thread_id"] == "sess_test123"
        # C-2: TelemetryCallback이 callbacks에 포함되었는지 확인
        assert "callbacks" in config
        assert len(config["callbacks"]) >= 1

    def test_create_episode_emotion_extraction(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """emotion_vectors 데이터가 EmotionSummary로 올바르게 변환."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        emotion = data["emotion"]
        assert emotion is not None
        assert emotion["primary_emotion"] == "calm"
        assert emotion["intensity"] == 0.6

    def test_create_episode_emotion_none_when_missing(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """emotion_vectors가 없으면 emotion=None."""
        mock_compiled_graph.ainvoke = AsyncMock(
            return_value=make_pipeline_result(emotion_vectors=None),
        )

        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        assert data["emotion"] is None

    def test_create_episode_safety_alert_crisis(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """safety_flags.status=crisis → show_emergency_button=true."""
        mock_compiled_graph.ainvoke = AsyncMock(
            return_value=make_pipeline_result(
                safety_flags={
                    "status": "crisis",
                    "message": "위기 상황이 감지되었습니다.",
                    "helpline_info": [
                        {
                            "name": "자살예방상담전화",
                            "phone": "1393",
                            "description": "24시간 운영",
                        },
                    ],
                },
            ),
        )

        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        assert data["safety_alert"] is not None
        assert data["safety_alert"]["status"] == "crisis"
        assert data["safety_alert"]["show_emergency_button"] is True

    def test_create_episode_safety_alert_safe(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """safety_flags.status=safe → safety_alert=None."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        assert data["safety_alert"] is None

    def test_create_episode_validation_error_missing_topic(
        self, test_client,
    ) -> None:
        """topic 필드 누락 시 422."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json={
                "user_id": "test_user_001",
                "session_id": "sess_test123",
                # topic 누락
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_episode_pipeline_error(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """compiled_graph.ainvoke가 예외 발생 시 500."""
        mock_compiled_graph.ainvoke = AsyncMock(
            side_effect=RuntimeError("파이프라인 실행 실패"),
        )

        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "SERVER_ERROR"

    def test_create_episode_metadata(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """metadata에 pipeline_duration_ms, total_words 등이 포함."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        meta = data["metadata"]
        assert "pipeline_duration_ms" in meta
        assert meta["pipeline_duration_ms"] >= 0
        assert "total_words" in meta
        assert meta["total_words"] == 10  # conftest mock의 word_count=10
        assert "intent_type" in meta

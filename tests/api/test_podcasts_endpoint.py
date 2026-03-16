"""
Podcasts 엔드포인트 테스트.

POST /api/v1/podcasts/episodes (팟캐스트 에피소드 생성) 검증.
compiled_graph를 mock하여 파이프라인 없이 엔드포인트 매핑 로직을 테스트.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from tests.api.conftest import make_pipeline_result


class TestCreatePodcastEpisode:
    """POST /api/v1/podcasts/episodes 엔드포인트 테스트."""

    def _valid_request(self, **overrides: Any) -> dict[str, Any]:
        """유효한 PodcastRequest 생성 헬퍼."""
        base = {
            "user_id": "test_user_001",
            "session_id": "sess_test123",
            "situation": "직장에서 스트레스를 많이 받고 있어",
            "thought": "이 상황을 어떻게 해결해야 할지 모르겠어",
            "action": "일단 참고 있는데 점점 힘들어지고 있어",
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
        assert data["success"] is True
        assert "episode_id" in data
        assert "session_id" in data

    def test_create_episode_response_structure(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """응답 구조가 PodcastEpisodeResponse 스키마에 맞는지 확인."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        # SlimPodcastResponse 필수 필드
        assert data["success"] is True
        assert isinstance(data["episode_id"], str)
        assert isinstance(data["session_id"], str)
        assert "safety_alert" in data
        assert "tracing" in data
        assert isinstance(data["tracing"]["trace_id"], str)
        # 제거된 필드가 없는지 확인
        assert "episode" not in data
        assert "emotion" not in data
        assert "metadata" not in data
        assert "cover_image" not in data

    def test_create_episode_state_mapping(
        self, test_client, mock_compiled_graph,
    ) -> None:
        """situation/thought/action/colleagueReaction → user_input, mode=podcast 매핑 확인."""
        test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(colleagueReaction="동료는 아무 말도 안 해"),
        )

        # ainvoke 호출 인자 확인
        call_args = mock_compiled_graph.ainvoke.call_args
        state = call_args[0][0]  # 첫 번째 위치 인자

        expected = (
            "- 상황: 직장에서 스트레스를 많이 받고 있어\n"
            "- 자신의 생각: 이 상황을 어떻게 해결해야 할지 모르겠어\n"
            "- 자신의 행동 및 반응: 일단 참고 있는데 점점 힘들어지고 있어\n"
            "- 동료의 반응: 동료는 아무 말도 안 해"
        )
        assert state["user_input"] == expected
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

    def test_create_episode_validation_error_missing_situation(
        self, test_client,
    ) -> None:
        """situation 필드 누락 시 422."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json={
                "user_id": "test_user_001",
                "session_id": "sess_test123",
                # situation 누락
                "thought": "생각",
                "action": "행동",
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


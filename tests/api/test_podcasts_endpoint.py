"""
Podcasts 엔드포인트 테스트.

POST /api/v1/podcasts/episodes (팟캐스트 에피소드 생성) 검증.
compiled_graph를 mock하여 파이프라인 없이 엔드포인트 매핑 로직을 테스트.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

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

    def test_create_episode_success_and_response_structure(
        self,
        test_client,
        mock_compiled_graph,
    ) -> None:
        """유효한 요청으로 에피소드 생성 시 200 + 응답 구조 + 상태 매핑 + config 검증."""
        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(colleagueReaction="동료는 아무 말도 안 해"),
        )

        assert response.status_code == 200
        data = response.json()
        # 필수 필드
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

        # 상태 매핑 검증
        call_args = mock_compiled_graph.ainvoke.call_args
        state = call_args[0][0]
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

        # config 검증
        config = call_args[1].get("config") or call_args[0][1]
        assert config["configurable"]["thread_id"] == "sess_test123"
        assert "callbacks" in config
        assert len(config["callbacks"]) >= 1

    @pytest.mark.parametrize(
        "safety_flags, expected_status, expected_button",
        [
            (
                {
                    "status": "crisis",
                    "message": "위기 상황이 감지되었습니다.",
                    "helpline_info": [
                        {"name": "자살예방상담전화", "phone": "1393", "description": "24시간 운영"},
                    ],
                },
                "crisis",
                True,
            ),
            (
                {"status": "safe"},
                None,
                None,
            ),
        ],
        ids=["crisis_alert", "safe_no_alert"],
    )
    def test_create_episode_safety_alert(
        self,
        test_client,
        mock_compiled_graph,
        safety_flags,
        expected_status,
        expected_button,
    ) -> None:
        """safety_flags.status별 safety_alert 응답 검증."""
        mock_compiled_graph.ainvoke = AsyncMock(
            return_value=make_pipeline_result(safety_flags=safety_flags),
        )

        response = test_client.post(
            "/api/v1/podcasts/episodes",
            json=self._valid_request(),
        )

        data = response.json()
        if expected_status is None:
            assert data["safety_alert"] is None
        else:
            assert data["safety_alert"]["status"] == expected_status
            assert data["safety_alert"]["show_emergency_button"] is expected_button

    @pytest.mark.parametrize(
        "request_body, mock_side_effect, expected_status, expected_code",
        [
            (
                {
                    "user_id": "test_user_001",
                    "session_id": "sess_test123",
                    "thought": "생각",
                    "action": "행동",
                },
                None,
                422,
                "VALIDATION_ERROR",
            ),
            (
                None,  # valid request (filled in test)
                RuntimeError("파이프라인 실행 실패"),
                500,
                "SERVER_ERROR",
            ),
        ],
        ids=["validation_error_missing_situation", "pipeline_error"],
    )
    def test_create_episode_error(
        self,
        test_client,
        mock_compiled_graph,
        request_body,
        mock_side_effect,
        expected_status,
        expected_code,
    ) -> None:
        """검증 에러(422) + 파이프라인 에러(500) 통합 검증."""
        if mock_side_effect is not None:
            mock_compiled_graph.ainvoke = AsyncMock(side_effect=mock_side_effect)

        body = request_body if request_body is not None else self._valid_request()
        response = test_client.post("/api/v1/podcasts/episodes", json=body)

        assert response.status_code == expected_status
        data = response.json()
        assert data["error"]["code"] == expected_code

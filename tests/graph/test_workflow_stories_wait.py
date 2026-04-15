"""wait_for_stories_node 및 route_after_wait_stories 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from src.graph.workflow import route_after_wait_stories


class TestRouteAfterWaitStories:
    def test_stories_timeout_routes_to_error(self) -> None:
        """next_step이 stories_timeout이면 stories_error 반환."""
        state = {"next_step": "stories_timeout", "session_id": "sess_001"}
        assert route_after_wait_stories(state) == "stories_error"

    def test_success_routes_to_script_personalizer(self) -> None:
        """next_step이 빈 문자열이면 script_personalizer 반환."""
        state = {
            "stories_context": {"keywords": [], "title": "T", "description": "D"},
            "next_step": "",
        }
        assert route_after_wait_stories(state) == "script_personalizer"

    def test_no_next_step_routes_to_script_personalizer(self) -> None:
        """next_step 키가 없으면 script_personalizer 반환."""
        state: dict = {"session_id": "sess_002"}
        assert route_after_wait_stories(state) == "script_personalizer"


class TestWaitForStoriesNode:
    async def test_returns_stories_context_on_success(self) -> None:
        """데이터 수신 성공 시 stories_context를 반환한다."""
        from src.graph.workflow import wait_for_stories_node

        mock_data = {"keywords": ["직장"], "title": "T", "description": "D"}
        state: dict = {"session_id": "sess_wait_001"}

        with (
            patch(
                "src.graph.workflow.stories_store.wait_for_stories",
                new=AsyncMock(return_value=mock_data),
            ),
            patch("src.graph.workflow.stories_store.delete_session"),
        ):
            result = await wait_for_stories_node(state)

        assert result["stories_context"] == mock_data
        assert result.get("next_step") != "stories_timeout"

    async def test_returns_stories_timeout_on_timeout(self) -> None:
        """타임아웃 시 next_step: stories_timeout을 반환한다."""
        from src.graph.workflow import wait_for_stories_node

        state: dict = {"session_id": "sess_wait_002"}

        with (
            patch(
                "src.graph.workflow.stories_store.wait_for_stories",
                new=AsyncMock(return_value=None),
            ),
            patch("src.graph.workflow.stories_store.delete_session"),
        ):
            result = await wait_for_stories_node(state)

        assert result["next_step"] == "stories_timeout"
        assert result.get("stories_context") is None

    async def test_crisis_bypasses_stories_wait(self) -> None:
        """CRISIS 상태에서는 stories 대기를 생략하고 즉시 TIER 4로 진행한다.

        프론트가 CRISIS 사용자에 대해 Stories 데이터를 발행하지 않으므로,
        대기하면 _STORIES_WAIT_TIMEOUT(최대 300초)가 소진된 후 stories_error
        노드가 final_output을 덮어쓴다. CRISIS 시 즉시 통과시켜야 한다.
        """
        from src.graph.workflow import wait_for_stories_node

        state: dict = {
            "session_id": "sess_crisis_wait",
            "safety_flags": {"status": "crisis"},
        }

        # wait_for_stories는 절대 호출되지 않아야 한다 (대기 방지).
        mock_wait = AsyncMock()
        with (
            patch("src.graph.workflow.stories_store.wait_for_stories", new=mock_wait),
            patch("src.graph.workflow.stories_store.delete_session") as mock_del,
        ):
            result = await wait_for_stories_node(state)

        mock_wait.assert_not_called()
        # CRISIS 경로에서도 세션은 정리되어야 한다.
        mock_del.assert_called_once_with("sess_crisis_wait")

        assert result.get("next_step") != "stories_timeout"
        assert result.get("next_step") == ""

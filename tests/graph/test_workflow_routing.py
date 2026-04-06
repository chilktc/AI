"""워크플로우 라우팅 함수 단위 테스트."""

import pytest

from src.graph.workflow import (
    route_after_tier0,
    route_after_tier3_podcast,
)


class TestRouteAfterTier0:
    def test_always_returns_tier1_podcast(self):
        state = {"mode": "podcast", "intent": {}}
        assert route_after_tier0(state) == "tier1_podcast"

    def test_ignores_next_step(self):
        state = {"next_step": "some_other_route"}
        assert route_after_tier0(state) == "tier1_podcast"


class TestRouteAfterTier3Podcast:
    def test_pass_verdict_routes_to_tier4(self):
        state = {
            "validation_result": {"verdict": "PASS"},
            "iteration_count": 0,
        }
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_fail_verdict_first_attempt_routes_to_retry(self):
        state = {
            "validation_result": {"verdict": "FAIL"},
            "iteration_count": 0,
        }
        assert route_after_tier3_podcast(state) == "tier2_podcast"

    def test_fail_verdict_max_retries_routes_to_tier4(self):
        state = {
            "validation_result": {"verdict": "FAIL"},
            "iteration_count": 2,
        }
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_critical_fail_first_attempt_routes_to_retry(self):
        state = {
            "validation_result": {"verdict": "CRITICAL_FAIL"},
            "iteration_count": 0,
        }
        assert route_after_tier3_podcast(state) == "tier2_podcast"

    def test_critical_fail_max_retries_routes_to_tier4(self):
        state = {
            "validation_result": {"verdict": "CRITICAL_FAIL"},
            "iteration_count": 4,
        }
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_missing_validation_triggers_retry_on_first_attempt(self):
        """validation_result 없음 (BV 타임아웃) → 재시도 (iteration_count=0)."""
        state = {"iteration_count": 0}
        assert route_after_tier3_podcast(state) == "tier2_podcast"

    def test_missing_validation_triggers_pass_when_retries_exhausted(self):
        """재시도 소진 시 validation_result 없어도 강제 통과."""
        import src.graph.workflow as wf
        state = {"iteration_count": wf._MAX_RETRIES}
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_empty_verdict_triggers_retry_on_first_attempt(self):
        """verdict 없는 validation_result (BV 실패/타임아웃) → 재시도."""
        state = {"validation_result": {}, "iteration_count": 0}
        assert route_after_tier3_podcast(state) == "tier2_podcast"


class TestBuildUnifiedGraphNodes:
    def test_build_unified_graph_has_intent_classifier_node(self):
        """build_unified_graph()에 intent_classifier 노드가 등록된다."""
        from src.graph.workflow import build_unified_graph
        graph = build_unified_graph()
        assert "intent_classifier" in graph.nodes


class TestIntentClassifierNodeUsesCall:
    @pytest.mark.asyncio
    async def test_intent_classifier_node_uses_call_not_process(self):
        """intent_classifier_node가 agent(state)를 호출한다 (process() 직접 호출 아님)."""
        from unittest.mock import AsyncMock, patch

        from src.agents.podcast.intent_classifier import IntentClassifierAgent
        from src.graph.workflow import intent_classifier_node

        mock_agent = AsyncMock(spec=IntentClassifierAgent)
        mock_agent.return_value = {"intent": {}}
        mock_agent.process = AsyncMock(return_value={"intent": {}})

        with patch("src.graph.workflow.IntentClassifierAgent", return_value=mock_agent):
            await intent_classifier_node({"user_input": "test"})

        mock_agent.assert_awaited_once()
        mock_agent.process.assert_not_called()

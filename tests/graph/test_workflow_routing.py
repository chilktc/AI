"""워크플로우 라우팅 함수 단위 테스트."""

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

    def test_missing_validation_defaults_to_pass(self):
        state = {"iteration_count": 0}
        assert route_after_tier3_podcast(state) == "tier4_podcast"

    def test_empty_verdict_defaults_to_pass(self):
        state = {
            "validation_result": {},
            "iteration_count": 0,
        }
        assert route_after_tier3_podcast(state) == "tier4_podcast"

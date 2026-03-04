"""팟캐스트모드 에이전트 테스트 공용 Fixture.

GoT(Graph-of-Thought)를 기본 추론 전략으로 설정한다.
full_threshold=0.0, standard_threshold=0.0 → 모든 complexity에서 GoT 사용.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent


@pytest.fixture(autouse=True)
def got_default_thresholds():
    """GoT를 기본 추론 전략으로 설정 (full_threshold=0.0)."""
    original_load = PodcastReasoningAgent._load_config

    def _patched_load(self):
        original_load(self)
        self.full_threshold = 0.0
        self.standard_threshold = 0.0

    with patch.object(PodcastReasoningAgent, "_load_config", _patched_load):
        yield

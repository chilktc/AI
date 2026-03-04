"""
Episode Memory Agent 단위 테스트.

팟캐스트 전용 메모리 에이전트의 output_key, namespace 분리를 검증한다.
"""

from __future__ import annotations

from src.agents.podcast.episode_memory import EpisodeMemoryAgent


def test_output_key_is_memory_results() -> None:
    """팟캐스트 전용 output_key가 'memory_results'로 설정된다."""
    agent = EpisodeMemoryAgent()
    assert agent._output_key == "memory_results"


def test_namespace_is_podcast_episode() -> None:
    """팟캐스트 전용 namespace가 'mem_podcast_episode'로 분리된다."""
    agent = EpisodeMemoryAgent()
    assert agent._namespace == "mem_podcast_episode"
    assert agent.tier is None

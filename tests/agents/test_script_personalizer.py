"""
Script Personalizer Agent 테스트
"""

import pytest

from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent


def _make_state_with_draft():
    """테스트용 최소 AgentState"""
    seg1 = {
        "segment_id": "s1",
        "segment_type": "opening",
        "duration_minutes": 2,
        "script_text": "안녕하세요, 오늘의 팟캐스트입니다.",
        "word_count": 10,
        "emotional_tone": "warm",
    }
    seg2 = {
        "segment_id": "s2",
        "segment_type": "closing",
        "duration_minutes": 1,
        "script_text": "오늘도 들어주셔서 감사합니다.",
        "word_count": 8,
        "emotional_tone": "calm",
    }
    return {
        "user_id": "user_test_01",
        "session_id": "sess_test_01",
        "script_draft": {
            "episode_id": "ep_test_01",
            "episode_title": "테스트 에피소드",
            "total_duration": 3,
            "segments": [seg1, seg2],
            "key_insights": [],
            "themes": [],
            "is_valid": True,
            "validation_score": 0.9,
            "validation_messages": [],
        },
        "risk_level": 0,
        "safety_flags": {"status": "safe"},
    }


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_write_true():
    """Script Personalizer 완료 후 memory_write=True가 반환에 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()
    result = await agent(state)
    assert result.get("memory_write") is True, "memory_write=True가 반환에 없음"


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_text():
    """memory_text에 에피소드 세그먼트 텍스트가 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()
    result = await agent(state)
    memory_text = result.get("memory_text", "")
    assert "안녕하세요" in memory_text, "첫 번째 세그먼트 텍스트가 memory_text에 없음"
    assert "감사합니다" in memory_text, "두 번째 세그먼트 텍스트가 memory_text에 없음"


@pytest.mark.asyncio
async def test_script_personalizer_sets_memory_metadata():
    """memory_metadata에 user_id, session_id, episode_id가 포함된다."""
    agent = ScriptPersonalizerAgent()
    state = _make_state_with_draft()
    result = await agent(state)
    meta = result.get("memory_metadata", {})
    assert meta.get("user_id") == "user_test_01"
    assert meta.get("session_id") == "sess_test_01"
    assert "episode_id" in meta
    assert "episode_title" in meta

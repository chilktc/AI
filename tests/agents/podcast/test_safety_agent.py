"""
Safety Agent 단위 테스트.

safe/crisis/warning 판정, required_in_script 보장, fallback 로직을 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.safety import SafetyAgent
from src.models.agent_state import AgentState


@pytest.fixture
def agent() -> SafetyAgent:
    with patch.object(SafetyAgent, "get_prompt", return_value="dummy"):
        ag = SafetyAgent()
    ag.get_prompt = lambda key="system_prompt": "dummy"
    return ag


@pytest.mark.asyncio
async def test_safe_status_with_empty_required_in_script(agent: SafetyAgent) -> None:
    """safe 판정 시 required_in_script가 빈 리스트로 보장된다."""
    llm_response = {
        "status": "safe",
        "reasons": [],
        "required_in_script": [],
        "forbidden_topics": [],
    }
    state = AgentState(user_input="오늘 날씨가 좋아요", user_id="u", session_id="s", mode="podcast")

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "safe"
    assert isinstance(sf["required_in_script"], list)
    assert len(sf["required_in_script"]) == 0


@pytest.mark.asyncio
async def test_crisis_keyword_triggers_crisis_fallback(agent: SafetyAgent) -> None:
    """CRISIS 키워드 감지 + LLM 실패 시 crisis fallback이 작동한다."""
    state = AgentState(
        user_input="더 이상 살고 싶지 않아요",
        user_id="u", session_id="s", mode="podcast",
    )

    mock = AsyncMock(side_effect=KeyError("prompt"))
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "crisis"
    assert isinstance(sf["required_in_script"], list)
    assert len(sf["required_in_script"]) > 0  # 최소 기본 안전문구 포함


@pytest.mark.asyncio
async def test_warning_status_gets_default_safety_text(agent: SafetyAgent) -> None:
    """warning 판정 + 빈 required_in_script 시 기본 안전문구가 추가된다."""
    llm_response = {
        "status": "warning",
        "reasons": ["mild_concern"],
        "required_in_script": [],  # LLM이 비웠지만 기본 문구 보장
        "forbidden_topics": [],
    }
    state = AgentState(
        user_input="요즘 우울한 기분이에요",
        user_id="u", session_id="s", mode="podcast",
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "warning"
    assert isinstance(sf["required_in_script"], list)
    assert len(sf["required_in_script"]) >= 2  # 기본 2개 문구


@pytest.mark.asyncio
async def test_required_in_script_always_list(agent: SafetyAgent) -> None:
    """LLM이 잘못된 타입을 반환해도 required_in_script가 항상 list로 보정된다."""
    llm_response = {
        "status": "safe",
        "reasons": "not_a_list",           # 타입 오류
        "required_in_script": "string",    # 타입 오류
        "forbidden_topics": None,          # 타입 오류
    }
    state = AgentState(user_input="테스트 입력", user_id="u", session_id="s", mode="podcast")

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert isinstance(sf["required_in_script"], list)
    assert isinstance(sf["reasons"], list)
    assert isinstance(sf["forbidden_topics"], list)

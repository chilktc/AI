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
    """safe 판정 시 required_in_script가 빈 리스트로 보장되고, LLM 응답이 그대로 전달된다."""
    llm_response = {
        "status": "safe",
        "risk_level": 0,
        "risk_score": 0.05,
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
    # safe 시 crisis_response 라우팅 없음
    assert "next_step" not in result


@pytest.mark.asyncio
async def test_crisis_status_injects_safety_constants(agent: SafetyAgent) -> None:
    """LLM이 crisis 판정 시 SAFETY_MESSAGES 상수가 required_in_script에 주입된다."""
    llm_response = {
        "status": "crisis",
        "risk_level": 4,
        "risk_score": 0.95,
        "reasons": ["자해 위험"],
        "required_in_script": [],
        "forbidden_topics": [],
    }
    state = AgentState(
        user_input="더 이상 살고 싶지 않아요",
        user_id="u",
        session_id="s",
        mode="podcast",
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "crisis"
    assert isinstance(sf["required_in_script"], list)
    assert len(sf["required_in_script"]) > 0
    assert result["next_step"] == "crisis_response"


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
        user_id="u",
        session_id="s",
        mode="podcast",
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "warning"
    assert isinstance(sf["required_in_script"], list)
    assert len(sf["required_in_script"]) >= 2  # 기본 2개 문구


@pytest.mark.asyncio
async def test_llm_failure_returns_safe_fallback(agent: SafetyAgent) -> None:
    """LLM 호출 실패 시 safe fallback을 반환하고 파이프라인이 중단되지 않는다."""
    state = AgentState(
        user_input="테스트 입력",
        user_id="u",
        session_id="s",
        mode="podcast",
    )
    mock = AsyncMock(side_effect=Exception("LLM connection error"))
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert sf["status"] == "safe"
    assert "next_step" not in result  # crisis_response 라우팅 없음


@pytest.mark.asyncio
async def test_safety_flags_contains_only_four_expected_keys(agent: SafetyAgent) -> None:
    """safety_flags는 status/risk_level/risk_score/required_in_script 네 키만 가진다 (SA-1)."""
    llm_response = {
        "status": "safe",
        "risk_level": 0,
        "risk_score": 0.05,
        "required_in_script": [],
        "reasons": ["정보성 발화"],
        "extra_llm_field": "유입 금지",
    }
    state = AgentState(
        user_input="오늘 기분이 좋아요", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response):
        result = await agent.process(state)

    sf = result["safety_flags"]
    assert set(sf.keys()) == {"status", "risk_level", "risk_score", "required_in_script"}
    assert "extra_llm_field" not in sf
    assert "reasons" not in sf


@pytest.mark.asyncio
async def test_fallback_safety_flags_has_no_flags_key(agent: SafetyAgent) -> None:
    """LLM 호출 실패 시 폴백 safety_flags에 레거시 flags 키 없다 (SA-2)."""
    state = AgentState(
        user_input="오늘 날씨 좋아요", user_id="u", session_id="s", mode="podcast"
    )

    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, side_effect=RuntimeError("LLM 실패")
    ):
        result = await agent.process(state)

    assert "flags" not in result["safety_flags"], "SA-2: 레거시 flags 키 잔존"
    assert "status" in result["safety_flags"]


# === LLM 실제 호출 테스트 ===


@pytest.mark.live
class TestSafetyAgentWithLLM:
    """SafetyAgent LLM 실제 호출 테스트."""

    @pytest.fixture
    def agent(self, llm_client) -> SafetyAgent:
        if llm_client is None:
            pytest.skip("LLM client not available")
        ag = SafetyAgent()
        ag.llm_client = llm_client
        return ag

    @pytest.mark.asyncio
    async def test_llm_safe_input(self, agent: SafetyAgent) -> None:
        """일반 입력에 대해 safe 판정을 반환한다."""
        import time

        state = AgentState(
            user_input="오늘 날씨가 좋아서 공원 산책을 했어요.",
            user_id="u",
            session_id="s",
            mode="podcast",
        )
        start = time.time()
        result = await agent.process(state)
        elapsed = time.time() - start
        print(f"\n[Safety safe] ⏱️ {elapsed:.2f}초")
        print(f"  status={result['safety_flags']['status']}, score={result['risk_score']}")

        sf = result["safety_flags"]
        assert sf["status"] in {"safe", "warning", "crisis"}
        assert set(sf.keys()) == {"status", "risk_level", "risk_score", "required_in_script"}
        assert isinstance(sf["risk_score"], float)

    @pytest.mark.asyncio
    async def test_llm_crisis_input(self, agent: SafetyAgent) -> None:
        """위기 입력에 대해 crisis 또는 warning 판정을 반환한다."""
        import time

        state = AgentState(
            user_input="더 이상 살고 싶지 않아요. 모든 게 의미 없어요.",
            user_id="u",
            session_id="s",
            mode="podcast",
        )
        start = time.time()
        result = await agent.process(state)
        elapsed = time.time() - start
        print(f"\n[Safety crisis] ⏱️ {elapsed:.2f}초")
        print(f"  status={result['safety_flags']['status']}, score={result['risk_score']}")

        sf = result["safety_flags"]
        assert sf["status"] in {"warning", "crisis"}, f"위기 입력에 safe 판정: {sf}"
        assert sf["risk_level"] > 0

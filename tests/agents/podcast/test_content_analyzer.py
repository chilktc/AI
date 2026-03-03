"""
Content Analyzer 에이전트 테스트.

Content Analyzer가 사용자 입력에서 팟캐스트 에피소드 주제/테마/구조를
올바르게 추출하는지 검증한다.

v12 리팩터: 38 → 12 테스트 (parametrize + 중복 삭제)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.content_analyzer import (
    _DEFAULTS,
    ContentAnalyzerAgent,
)
from src.models.agent_state import AgentState

# _DEFAULTS에서 테스트용 상수 참조
MAX_DURATION = _DEFAULTS["max_duration"]
MAX_SUB_THEMES = _DEFAULTS["max_sub_themes"]
MAX_THEME_LENGTH = _DEFAULTS["max_theme_length"]
MIN_DURATION = _DEFAULTS["min_duration"]


# === 픽스처 ===


@pytest.fixture
def agent() -> ContentAnalyzerAgent:
    """테스트용 Content Analyzer 에이전트 인스턴스."""
    return ContentAnalyzerAgent()


@pytest.fixture
def base_state() -> AgentState:
    """기본 AgentState — 최소 필수 필드만 포함."""
    return AgentState(
        user_input="요즘 스트레스를 많이 받아서 마음이 힘들어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
    )


@pytest.fixture
def mock_llm_response() -> dict[str, Any]:
    """LLM이 반환할 모의 분석 결과."""
    return {
        "main_theme": "스트레스 해소와 마음 돌봄",
        "sub_themes": ["스트레스 관리", "자기돌봄", "감정 인식"],
        "emotional_journey": {
            "start_emotion": "피로",
            "peak_emotion": "인식",
            "resolution_emotion": "안도",
            "journey_type": "healing",
        },
        "target_duration": 4,
        "narrative_structure": "reflection",
        "key_messages": ["나를 돌보는 것은 이기적이지 않다", "작은 변화가 큰 차이를 만든다"],
    }


# === 1. process() 기본 동작 ===


@pytest.mark.asyncio
async def test_process_returns_content_analysis(
    agent: ContentAnalyzerAgent,
    base_state: AgentState,
    mock_llm_response: dict[str, Any],
) -> None:
    """process()가 content_analysis 필드를 올바르게 반환하는지 확인."""
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
    ):
        result = await agent.process(base_state)

    assert "content_analysis" in result
    assert list(result.keys()) == ["content_analysis"]
    assert result["content_analysis"]["main_theme"] == "스트레스 해소와 마음 돌봄"
    assert result["content_analysis"]["narrative_structure"] == "reflection"


# === 2. Intent 포함/미포함 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "has_intent, expect_in_prompt",
    [
        pytest.param(True, True, id="with_intent"),
        pytest.param(False, False, id="without_intent"),
    ],
)
async def test_process_intent_context(
    agent: ContentAnalyzerAgent,
    mock_llm_response: dict[str, Any],
    has_intent: bool,
    expect_in_prompt: bool,
) -> None:
    """Intent가 있으면 프롬프트에 포함되고, 없으면 포함되지 않는다."""
    state = AgentState(
        user_input="요즘 스트레스를 많이 받아서 마음이 힘들어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
    )
    if has_intent:
        state["intent"] = {"primary_intent": "stress_relief", "complexity_score": 0.6}

    mock = AsyncMock(return_value=mock_llm_response)
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    assert "content_analysis" in result
    user_message = mock.call_args.kwargs.get(
        "user_message", mock.call_args.args[1] if len(mock.call_args.args) > 1 else ""
    )
    if expect_in_prompt:
        assert "stress_relief" in user_message
    else:
        assert "Intent Classifier" not in user_message


# === 3. 분석 깊이 결정 ===


@pytest.mark.parametrize(
    "score, expected_depth",
    [
        pytest.param(0.85, "deep", id="high"),
        pytest.param(0.7, "deep", id="boundary_deep"),
        pytest.param(0.5, "moderate", id="moderate"),
        pytest.param(0.4, "moderate", id="boundary_moderate"),
        pytest.param(0.2, "light", id="low"),
        pytest.param(0.0, "light", id="zero"),
    ],
)
def test_depth_routing(
    agent: ContentAnalyzerAgent, score: float, expected_depth: str
) -> None:
    """complexity_score 기반 분석 깊이 결정."""
    assert agent._determine_depth(score) == expected_depth


# === 4. complexity 추출 ===


@pytest.mark.parametrize(
    "intent_data, expected",
    [
        pytest.param({}, 0.5, id="missing_default"),
        pytest.param({"primary_intent": "test"}, 0.5, id="no_score_default"),
        pytest.param({"complexity_score": -0.5}, 0.0, id="clamp_low"),
        pytest.param({"complexity_score": 1.5}, 1.0, id="clamp_high"),
        pytest.param({"complexity_score": 0.7}, 0.7, id="valid"),
    ],
)
def test_extract_complexity(
    agent: ContentAnalyzerAgent, intent_data: dict, expected: float
) -> None:
    """Intent에서 complexity_score를 추출하고 0.0~1.0 범위로 보정."""
    assert agent._extract_complexity(intent_data) == expected


# === 5. 분석 깊이가 프롬프트에 포함 ===


@pytest.mark.asyncio
async def test_depth_in_prompt(
    agent: ContentAnalyzerAgent,
    mock_llm_response: dict[str, Any],
) -> None:
    """분석 깊이가 LLM 프롬프트에 포함되고 출력에도 반영된다."""
    state = AgentState(
        user_input="직장 상사와의 갈등이 동시에 찾아와서 정말 힘듭니다.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "complex_stress", "complexity_score": 0.85},
    )
    mock = AsyncMock(return_value=mock_llm_response)
    with patch.object(agent, "call_llm_json", mock):
        result = await agent.process(state)

    user_message = mock.call_args.kwargs.get(
        "user_message", mock.call_args.args[1] if len(mock.call_args.args) > 1 else ""
    )
    assert "deep" in user_message
    assert result["content_analysis"]["depth_level"] == "deep"


# === 6. 입력 전처리 ===


@pytest.mark.parametrize(
    "raw, expected",
    [
        pytest.param("  안녕하세요  ", "안녕하세요", id="strip_whitespace"),
        pytest.param("스트레스를   많이    받아요", "스트레스를 많이 받아요", id="collapse_spaces"),
        pytest.param("줄바꿈\n테스트\t입니다", "줄바꿈 테스트 입니다", id="newlines_tabs"),
        pytest.param("   ", "", id="whitespace_only"),
        pytest.param("", "", id="empty"),
    ],
)
def test_normalize_input(
    agent: ContentAnalyzerAgent, raw: str, expected: str
) -> None:
    """입력 전처리 — 공백/줄바꿈 정규화."""
    assert agent._normalize_input(raw) == expected


# === 7. 후처리: main_theme ===


@pytest.mark.parametrize(
    "analysis, expected_theme",
    [
        pytest.param(
            {"main_theme": "가" * 150},
            "가" * MAX_THEME_LENGTH + "...",
            id="truncation",
        ),
        pytest.param({"main_theme": "짧은 주제"}, "짧은 주제", id="short_unchanged"),
        pytest.param({"topic": "스트레스 관리"}, "스트레스 관리", id="fallback_to_topic"),
        pytest.param({}, "", id="missing_default"),
    ],
)
def test_validate_main_theme(
    agent: ContentAnalyzerAgent, analysis: dict, expected_theme: str
) -> None:
    """main_theme 후처리 — 잘라내기, 폴백, 기본값."""
    result = agent._validate_and_correct(analysis, "moderate")
    assert result["main_theme"] == expected_theme


# === 8. 후처리: sub_themes ===


@pytest.mark.parametrize(
    "analysis, check_fn",
    [
        pytest.param(
            {"sub_themes": ["a", "b", "c", "d", "e", "f", "g"]},
            lambda r: len(r["sub_themes"]) == MAX_SUB_THEMES,
            id="truncation_to_max",
        ),
        pytest.param(
            {"themes": ["테마1", "테마2"]},
            lambda r: r["sub_themes"] == ["테마1", "테마2"],
            id="fallback_to_themes",
        ),
        pytest.param(
            {"sub_themes": "not_a_list"},
            lambda r: r["sub_themes"] == [],
            id="invalid_type_fallback",
        ),
    ],
)
def test_validate_sub_themes(
    agent: ContentAnalyzerAgent, analysis: dict, check_fn
) -> None:
    """sub_themes 후처리 — 잘라내기, 폴백, 타입 보정."""
    result = agent._validate_and_correct(analysis, "moderate")
    assert check_fn(result)


# === 9. 후처리: target_duration ===


@pytest.mark.parametrize(
    "analysis, expected_duration",
    [
        pytest.param({"target_duration": 1}, MIN_DURATION, id="min_clamp"),
        pytest.param({"target_duration": 20}, MAX_DURATION, id="max_clamp"),
        pytest.param({}, 4, id="default_when_missing"),
        pytest.param({"target_duration": "invalid"}, 4, id="invalid_type"),
    ],
)
def test_validate_duration(
    agent: ContentAnalyzerAgent, analysis: dict, expected_duration: int
) -> None:
    """target_duration 후처리 — 범위 보정, 기본값."""
    result = agent._validate_and_correct(analysis, "moderate")
    assert result["target_duration"] == expected_duration


# === 10. 후처리: narrative_structure ===


@pytest.mark.parametrize(
    "analysis, expected_structure",
    [
        pytest.param(
            {"narrative_structure": "reflection"}, "reflection", id="valid"
        ),
        pytest.param(
            {"narrative_structure": "invalid_structure"}, "reflection", id="invalid_fallback"
        ),
        pytest.param(
            {"suggested_structure": "personal_story"}, "personal_story", id="suggested_fallback"
        ),
    ],
)
def test_validate_narrative_structure(
    agent: ContentAnalyzerAgent, analysis: dict, expected_structure: str
) -> None:
    """narrative_structure 후처리 — 유효성 검증, 폴백."""
    result = agent._validate_and_correct(analysis, "moderate")
    assert result["narrative_structure"] == expected_structure


# === 11. 엣지케이스 입력 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        pytest.param("힘들어", id="very_short"),
        pytest.param("스트레스. " * 200, id="very_long"),
        pytest.param("😢 오늘은 정말... #힘든날 @멘탈관리 <중요>", id="special_chars"),
    ],
)
async def test_edge_case_inputs(
    agent: ContentAnalyzerAgent,
    mock_llm_response: dict[str, Any],
    user_input: str,
) -> None:
    """극단적 입력(짧은/긴/특수문자)도 정상 처리."""
    state = AgentState(
        user_input=user_input,
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
    )
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
    ):
        result = await agent.process(state)

    assert "content_analysis" in result


# === 12. 레거시 필드명 호환 ===


@pytest.mark.asyncio
async def test_legacy_field_names(agent: ContentAnalyzerAgent) -> None:
    """LLM이 레거시 필드명(topic, themes, suggested_structure)을 반환해도 보정."""
    legacy_response = {
        "topic": "레거시 주제",
        "themes": ["테마1", "테마2", "테마3"],
        "suggested_structure": "expert_qa",
        "target_duration": 4,
    }
    state = AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
    )
    with patch.object(
        agent, "call_llm_json", new_callable=AsyncMock, return_value=legacy_response
    ):
        result = await agent.process(state)

    analysis = result["content_analysis"]
    assert analysis["main_theme"] == "레거시 주제"
    assert analysis["sub_themes"] == ["테마1", "테마2", "테마3"]
    assert analysis["narrative_structure"] == "expert_qa"

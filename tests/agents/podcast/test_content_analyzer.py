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
    """LLM v2.2.0이 반환할 모의 분석 결과 (9개 필드)."""
    return {
        "main_theme": "스트레스 해소와 마음 돌봄",
        "user_summary": {
            "keywords": ["스트레스", "피로"],
            "summary": "스트레스와 피로를 호소하는 사용자",
        },
        "emotional_journey": {
            "opening": "피로와 무기력",
            "development": "원인 인식",
            "climax": "대처 전략 발견",
            "closing": "희망과 안도",
        },
        "key_messages": ["나를 돌보는 것은 이기적이지 않다", "작은 변화가 큰 차이를 만든다"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],
        "target_duration": 4,
        "narrative_structure": "reflection",
        "confidence": 0.85,
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
def test_depth_routing(agent: ContentAnalyzerAgent, score: float, expected_depth: str) -> None:
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
def test_normalize_input(agent: ContentAnalyzerAgent, raw: str, expected: str) -> None:
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
            lambda r: len(r["sub_themes"]) >= 3 and r["sub_themes"][:2] == ["테마1", "테마2"],
            id="fallback_to_themes_with_min_fill",
        ),
        pytest.param(
            {"sub_themes": "not_a_list"},
            lambda r: len(r["sub_themes"]) >= 3,
            id="invalid_type_min_fill",
        ),
    ],
)
def test_validate_sub_themes(agent: ContentAnalyzerAgent, analysis: dict, check_fn) -> None:
    """sub_themes 후처리 — 잘라내기, 폴백, 타입 보정, min 보장."""
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
        pytest.param({"narrative_structure": "reflection"}, "reflection", id="valid"),
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
    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=legacy_response):
        result = await agent.process(state)

    analysis = result["content_analysis"]
    assert analysis["main_theme"] == "레거시 주제"
    assert analysis["sub_themes"] == ["테마1", "테마2", "테마3"]
    assert analysis["narrative_structure"] == "expert_qa"


# === 11. user_input 안전 접근 ===


@pytest.mark.asyncio
async def test_missing_or_empty_user_input_returns_fallback(agent: ContentAnalyzerAgent) -> None:
    """user_input이 없거나 빈 문자열이면 error fallback을 반환한다."""
    # Case 1: 키 자체 없음
    state_no_key = AgentState(user_id="u", session_id="s", mode="podcast")
    result = await agent.process(state_no_key)
    ca = result["content_analysis"]
    assert ca.get("error") == "user_input_missing"
    assert ca["depth_level"] == "light"

    # Case 2: 빈 문자열
    state_empty = AgentState(user_input="", user_id="u", session_id="s", mode="podcast")
    result2 = await agent.process(state_empty)
    ca2 = result2["content_analysis"]
    assert ca2.get("error") == "user_input_missing"


# === CA-1/CA-2/CA-3 출력 필드 화이트리스트 + min_sub_themes 보장 ===


def test_validate_and_correct_excludes_unexpected_fields(
    agent: ContentAnalyzerAgent,
) -> None:
    """_validate_and_correct가 예상 외 LLM 필드를 결과에 포함하지 않는다 (CA-1)."""
    analysis = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "climax": "전환", "closing": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": ["스트레스", "감정", "관계"],
        "unknown_new_field": "임의 LLM 추가 필드",
        "debug_info": {"tokens": 125},
    }
    result = agent._validate_and_correct(analysis, depth_level="moderate")

    assert "unknown_new_field" not in result, "임의 LLM 필드 유입 금지"
    assert "debug_info" not in result, "디버그 필드 유입 금지"
    assert "sub_themes" in result
    assert len(result["sub_themes"]) >= 3, "min_sub_themes 보장"


def test_validate_and_correct_enforces_min_sub_themes(
    agent: ContentAnalyzerAgent,
) -> None:
    """LLM이 sub_themes를 빈 배열로 반환하면 min_sub_themes 보정 (CA-2)."""
    analysis = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "climax": "전환", "closing": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="moderate")

    assert len(result["sub_themes"]) >= agent.min_sub_themes, (
        f"sub_themes 최소 {agent.min_sub_themes}개 보장 실패"
    )


def test_build_db_payload_includes_trace_id(
    agent: ContentAnalyzerAgent,
) -> None:
    """_build_db_payload가 trace_id를 포함한다."""
    validated = {
        "user_summary": {"keywords": ["스트레스"], "summary": "힘든 사용자"},
        "main_theme": "스트레스 관리",
        "emotional_journey": {"opening": "피로", "development": "인식", "climax": "전환", "closing": "안도"},
        "key_messages": ["자기돌봄이 중요"],
        "depth_level": "moderate",
        "sub_themes": ["직장 스트레스", "감정 조절", "자기돌봄"],
        "target_duration": 5,
        "narrative_structure": "reflection",
        "confidence": 0.85,
    }
    db_payload = agent._build_db_payload(validated, trace_id="trace_abc")

    assert db_payload["trace_id"] == "trace_abc"
    assert db_payload["main_theme"] == "스트레스 관리"
    assert db_payload["sub_themes"] == ["직장 스트레스", "감정 조절", "자기돌봄"]


def test_validate_and_correct_validates_user_summary_type(
    agent: ContentAnalyzerAgent,
) -> None:
    """user_summary가 dict 아닐 때 빈 구조로 보정한다 (CA-1)."""
    analysis = {
        "user_summary": "문자열로 잘못 반환",
        "main_theme": "주제",
        "emotional_journey": {"opening": "피로", "development": "인식", "climax": "전환", "closing": "안도"},
        "key_messages": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="light")

    assert isinstance(result["user_summary"], dict)
    assert "keywords" in result["user_summary"]
    assert isinstance(result["user_summary"]["keywords"], list)


def test_validate_and_correct_validates_emotional_journey_type(
    agent: ContentAnalyzerAgent,
) -> None:
    """emotional_journey가 dict 아닐 때 4-키 빈 구조로 보정한다 (CA-1, CA-3)."""
    analysis = {
        "user_summary": {},
        "main_theme": "주제",
        "emotional_journey": "문자열로 잘못 반환",
        "key_messages": [],
    }
    result = agent._validate_and_correct(analysis, depth_level="light")

    ej = result["emotional_journey"]
    assert isinstance(ej, dict)
    assert set(ej.keys()) == {"opening", "development", "climax", "closing"}


def test_validate_and_correct_ensures_confidence_is_float(
    agent: ContentAnalyzerAgent,
) -> None:
    """confidence 필드가 항상 0.0~1.0 float으로 보정된다 (CA-3)."""
    analysis_str = {
        "main_theme": "주제",
        "user_summary": {},
        "emotional_journey": {},
        "key_messages": [],
        "confidence": "0.9",
    }
    result_str = agent._validate_and_correct(analysis_str, depth_level="light")
    assert isinstance(result_str["confidence"], float)
    assert 0.0 <= result_str["confidence"] <= 1.0

    analysis_missing = {
        "main_theme": "주제",
        "user_summary": {},
        "emotional_journey": {},
        "key_messages": [],
    }
    result_missing = agent._validate_and_correct(analysis_missing, depth_level="light")
    assert isinstance(result_missing["confidence"], float)


def test_validate_and_correct_limits_key_messages_to_five(
    agent: ContentAnalyzerAgent,
) -> None:
    """key_messages는 최대 5개 제한, dict 타입이면 빈 리스트 반환 (CA-1)."""
    analysis_over = {
        "user_summary": {},
        "main_theme": "주제",
        "emotional_journey": {},
        "key_messages": ["a", "b", "c", "d", "e", "f"],
    }
    result = agent._validate_and_correct(analysis_over, depth_level="light")
    assert len(result["key_messages"]) <= 5

    analysis_bad = {
        "user_summary": {},
        "main_theme": "주제",
        "emotional_journey": {},
        "key_messages": {"잘못된": "타입"},
    }
    result_bad = agent._validate_and_correct(analysis_bad, depth_level="light")
    assert result_bad["key_messages"] == []


@pytest.mark.asyncio
async def test_error_path_emotional_journey_has_four_keys(
    agent: ContentAnalyzerAgent,
) -> None:
    """user_input 누락 에러 경로의 emotional_journey가 4-키 구조다 (CA-3)."""
    state = AgentState(user_input="", user_id="u", session_id="s", mode="podcast")
    result = await agent.process(state)
    ej = result["content_analysis"]["emotional_journey"]
    assert set(ej.keys()) == {"opening", "development", "climax", "closing"}

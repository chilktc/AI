"""
Content Analyzer 에이전트 테스트.

Content Analyzer가 사용자 입력에서 팟캐스트 에피소드 주제/테마/구조를
올바르게 추출하는지 검증한다.

v11 추가:
    - complexity_score 기반 분석 깊이 테스트
    - 입력 전처리 테스트
    - LLM 결과 후처리 (검증/보정) 테스트
    - 엣지케이스: 빈 입력, 극단적 길이, 필수 필드 누락, 잘못된 타입
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.content_analyzer import (
    MAX_DURATION,
    MAX_SUB_THEMES,
    MAX_THEME_LENGTH,
    MIN_DURATION,
    VALID_NARRATIVE_STRUCTURES,
    ContentAnalyzerAgent,
    content_analyzer_agent,
    content_analyzer_node,
)
from src.models.agent_state import AgentState

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
def state_with_intent() -> AgentState:
    """Intent Classifier 결과가 포함된 AgentState."""
    return AgentState(
        user_input="요즘 스트레스를 많이 받아서 마음이 힘들어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={
            "primary_intent": "stress_relief",
            "complexity_score": 0.6,
        },
    )


@pytest.fixture
def state_high_complexity() -> AgentState:
    """높은 complexity_score (deep 분석) AgentState."""
    return AgentState(
        user_input="직장 상사와의 갈등, 가족 문제, 경제적 어려움이 동시에 찾아와서 정말 힘듭니다.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={
            "primary_intent": "complex_stress",
            "complexity_score": 0.85,
        },
    )


@pytest.fixture
def state_low_complexity() -> AgentState:
    """낮은 complexity_score (light 분석) AgentState."""
    return AgentState(
        user_input="오늘 기분이 좋아요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={
            "primary_intent": "positive_feeling",
            "complexity_score": 0.2,
        },
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


# === 기본 동작 테스트 ===


class TestContentAnalyzerAgent:
    """Content Analyzer 에이전트 기본 동작 테스트."""

    @pytest.mark.asyncio
    async def test_process_returns_content_analysis(
        self,
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
        assert result["content_analysis"]["main_theme"] == "스트레스 해소와 마음 돌봄"
        assert result["content_analysis"]["narrative_structure"] == "reflection"

    @pytest.mark.asyncio
    async def test_process_includes_intent_context(
        self,
        agent: ContentAnalyzerAgent,
        state_with_intent: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """Intent Classifier 결과가 있으면 참고 정보로 포함하는지 확인."""
        mock = AsyncMock(return_value=mock_llm_response)
        with patch.object(agent, "call_llm_json", mock):
            await agent.process(state_with_intent)

        # call_llm_json 호출 시 user_message에 Intent 분석 결과가 포함되어야 한다
        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "stress_relief" in user_message
        assert "0.6" in user_message

    @pytest.mark.asyncio
    async def test_process_without_intent(
        self,
        agent: ContentAnalyzerAgent,
        base_state: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """Intent가 없는 상태에서도 정상 동작하는지 확인."""
        mock = AsyncMock(return_value=mock_llm_response)
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(base_state)

        assert "content_analysis" in result
        # Intent 참고 정보가 user_message에 포함되지 않아야 한다
        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "Intent Classifier" not in user_message

    @pytest.mark.asyncio
    async def test_process_only_returns_content_analysis_field(
        self,
        agent: ContentAnalyzerAgent,
        base_state: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """process()가 content_analysis 외 다른 필드를 반환하지 않는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(base_state)

        assert list(result.keys()) == ["content_analysis"]

    def test_agent_attributes(self, agent: ContentAnalyzerAgent) -> None:
        """에이전트 기본 속성이 올바르게 설정되는지 확인."""
        assert agent.name == "content_analyzer"
        assert agent.tier == 1


# === v11 고도화: 분석 깊이 테스트 ===


class TestDepthDetermination:
    """complexity_score 기반 분석 깊이 결정 테스트."""

    def test_high_complexity_returns_deep(self, agent: ContentAnalyzerAgent) -> None:
        """complexity ≥ 0.7이면 'deep' 반환."""
        assert agent._determine_depth(0.7) == "deep"
        assert agent._determine_depth(0.85) == "deep"
        assert agent._determine_depth(1.0) == "deep"

    def test_moderate_complexity_returns_moderate(self, agent: ContentAnalyzerAgent) -> None:
        """0.4 ≤ complexity < 0.7이면 'moderate' 반환."""
        assert agent._determine_depth(0.4) == "moderate"
        assert agent._determine_depth(0.5) == "moderate"
        assert agent._determine_depth(0.69) == "moderate"

    def test_low_complexity_returns_light(self, agent: ContentAnalyzerAgent) -> None:
        """complexity < 0.4이면 'light' 반환."""
        assert agent._determine_depth(0.0) == "light"
        assert agent._determine_depth(0.2) == "light"
        assert agent._determine_depth(0.39) == "light"

    def test_extract_complexity_default(self, agent: ContentAnalyzerAgent) -> None:
        """Intent에 complexity_score가 없으면 기본값 0.5 반환."""
        assert agent._extract_complexity({}) == 0.5
        assert agent._extract_complexity({"primary_intent": "test"}) == 0.5

    def test_extract_complexity_clamps_range(self, agent: ContentAnalyzerAgent) -> None:
        """complexity_score를 0.0~1.0 범위로 보정."""
        assert agent._extract_complexity({"complexity_score": -0.5}) == 0.0
        assert agent._extract_complexity({"complexity_score": 1.5}) == 1.0
        assert agent._extract_complexity({"complexity_score": 0.7}) == 0.7

    @pytest.mark.asyncio
    async def test_depth_level_included_in_prompt(
        self,
        agent: ContentAnalyzerAgent,
        state_high_complexity: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """분석 깊이가 LLM 프롬프트에 포함되는지 확인."""
        mock = AsyncMock(return_value=mock_llm_response)
        with patch.object(agent, "call_llm_json", mock):
            await agent.process(state_high_complexity)

        user_message = mock.call_args.kwargs.get(
            "user_message", mock.call_args.args[1] if len(mock.call_args.args) > 1 else ""
        )
        assert "deep" in user_message

    @pytest.mark.asyncio
    async def test_depth_level_in_output(
        self,
        agent: ContentAnalyzerAgent,
        state_low_complexity: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """분석 깊이가 출력 결과에 포함되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state_low_complexity)

        assert result["content_analysis"]["depth_level"] == "light"


# === v11 고도화: 입력 전처리 테스트 ===


class TestInputPreprocessing:
    """입력 전처리 테스트."""

    def test_normalize_strips_whitespace(self, agent: ContentAnalyzerAgent) -> None:
        """앞뒤 공백 제거."""
        assert agent._normalize_input("  안녕하세요  ") == "안녕하세요"

    def test_normalize_collapses_multiple_spaces(self, agent: ContentAnalyzerAgent) -> None:
        """연속 공백을 단일 공백으로 축소."""
        assert agent._normalize_input("스트레스를   많이    받아요") == "스트레스를 많이 받아요"

    def test_normalize_handles_newlines_and_tabs(self, agent: ContentAnalyzerAgent) -> None:
        """줄바꿈/탭을 공백으로 변환."""
        assert agent._normalize_input("줄바꿈\n테스트\t입니다") == "줄바꿈 테스트 입니다"

    def test_normalize_empty_input(self, agent: ContentAnalyzerAgent) -> None:
        """빈 입력을 정상 처리."""
        assert agent._normalize_input("") == ""
        assert agent._normalize_input("   ") == ""


# === v11 고도화: 후처리 (검증/보정) 테스트 ===


class TestValidateAndCorrect:
    """LLM 결과 후처리 테스트."""

    def test_main_theme_truncation(self, agent: ContentAnalyzerAgent) -> None:
        """100자 초과 주제를 잘라내는지 확인."""
        long_theme = "가" * 150
        analysis = {"main_theme": long_theme}
        result = agent._validate_and_correct(analysis, "moderate")
        assert len(result["main_theme"]) == MAX_THEME_LENGTH + 3  # +3은 "..."
        assert result["main_theme"].endswith("...")

    def test_main_theme_short_unchanged(self, agent: ContentAnalyzerAgent) -> None:
        """100자 이하 주제는 변경하지 않는다."""
        analysis = {"main_theme": "짧은 주제"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["main_theme"] == "짧은 주제"

    def test_main_theme_fallback_to_topic(self, agent: ContentAnalyzerAgent) -> None:
        """main_theme 없으면 topic에서 가져온다 (LLM 응답 필드명 호환)."""
        analysis = {"topic": "스트레스 관리"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["main_theme"] == "스트레스 관리"

    def test_sub_themes_truncation(self, agent: ContentAnalyzerAgent) -> None:
        """하위 주제 5개 초과 시 5개로 자른다."""
        analysis = {"sub_themes": ["a", "b", "c", "d", "e", "f", "g"]}
        result = agent._validate_and_correct(analysis, "moderate")
        assert len(result["sub_themes"]) == MAX_SUB_THEMES

    def test_sub_themes_fallback_to_themes(self, agent: ContentAnalyzerAgent) -> None:
        """sub_themes 없으면 themes에서 가져온다."""
        analysis = {"themes": ["테마1", "테마2"]}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["sub_themes"] == ["테마1", "테마2"]

    def test_sub_themes_invalid_type(self, agent: ContentAnalyzerAgent) -> None:
        """sub_themes가 리스트가 아니면 빈 리스트로 보정."""
        analysis = {"sub_themes": "not_a_list"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["sub_themes"] == []

    def test_target_duration_min_clamp(self, agent: ContentAnalyzerAgent) -> None:
        """target_duration 최솟값 3분 보정."""
        analysis = {"target_duration": 1}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["target_duration"] == MIN_DURATION

    def test_target_duration_max_clamp(self, agent: ContentAnalyzerAgent) -> None:
        """target_duration 최댓값 5분 보정."""
        analysis = {"target_duration": 20}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["target_duration"] == MAX_DURATION

    def test_target_duration_default_when_missing(self, agent: ContentAnalyzerAgent) -> None:
        """target_duration 없으면 기본값 4분."""
        analysis = {}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["target_duration"] == 4

    def test_target_duration_invalid_type(self, agent: ContentAnalyzerAgent) -> None:
        """target_duration이 숫자가 아니면 기본값 4분."""
        analysis = {"target_duration": "invalid"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["target_duration"] == 4

    def test_narrative_structure_valid(self, agent: ContentAnalyzerAgent) -> None:
        """유효한 서사 구조 값은 변경하지 않는다."""
        for structure in VALID_NARRATIVE_STRUCTURES:
            analysis = {"narrative_structure": structure}
            result = agent._validate_and_correct(analysis, "moderate")
            assert result["narrative_structure"] == structure

    def test_narrative_structure_invalid_fallback(self, agent: ContentAnalyzerAgent) -> None:
        """유효하지 않은 서사 구조는 'reflection' 기본값으로 보정."""
        analysis = {"narrative_structure": "invalid_structure"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["narrative_structure"] == "reflection"

    def test_narrative_structure_fallback_to_suggested(self, agent: ContentAnalyzerAgent) -> None:
        """narrative_structure 없으면 suggested_structure에서 가져온다."""
        analysis = {"suggested_structure": "personal_story"}
        result = agent._validate_and_correct(analysis, "moderate")
        assert result["narrative_structure"] == "personal_story"

    def test_depth_level_always_set(self, agent: ContentAnalyzerAgent) -> None:
        """depth_level이 항상 출력에 포함된다."""
        analysis = {}
        for depth in ["light", "moderate", "deep"]:
            result = agent._validate_and_correct(analysis, depth)
            assert result["depth_level"] == depth

    def test_empty_analysis_gets_defaults(self, agent: ContentAnalyzerAgent) -> None:
        """완전히 빈 LLM 응답도 유효한 기본값으로 보정된다."""
        result = agent._validate_and_correct({}, "moderate")
        assert result["main_theme"] == ""
        assert result["sub_themes"] == []
        assert result["target_duration"] == 4
        assert result["narrative_structure"] == "reflection"
        assert result["depth_level"] == "moderate"


# === 엣지케이스 테스트 ===


class TestEdgeCases:
    """엣지케이스 및 실패 시나리오 테스트."""

    @pytest.mark.asyncio
    async def test_very_short_input(
        self,
        agent: ContentAnalyzerAgent,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """극단적으로 짧은 입력 (5자 미만)도 정상 처리."""
        state = AgentState(
            user_input="힘들어",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state)

        assert "content_analysis" in result

    @pytest.mark.asyncio
    async def test_very_long_input(
        self,
        agent: ContentAnalyzerAgent,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """극단적으로 긴 입력 (1000자 이상)도 정상 처리."""
        state = AgentState(
            user_input="스트레스. " * 200,  # 약 1200자
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state)

        assert "content_analysis" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_input(
        self,
        agent: ContentAnalyzerAgent,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """공백만 있는 입력도 정상 처리 (normalize 후 빈 문자열)."""
        state = AgentState(
            user_input="   \t\n   ",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state)

        assert "content_analysis" in result

    @pytest.mark.asyncio
    async def test_special_characters_input(
        self,
        agent: ContentAnalyzerAgent,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """특수문자가 포함된 입력 정상 처리."""
        state = AgentState(
            user_input="😢 오늘은 정말... #힘든날 @멘탈관리 <중요>",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state)

        assert "content_analysis" in result

    @pytest.mark.asyncio
    async def test_intent_with_missing_complexity(
        self,
        agent: ContentAnalyzerAgent,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """intent에 complexity_score가 없으면 기본 moderate 분석."""
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
            intent={"primary_intent": "test_intent"},
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_llm_response
        ):
            result = await agent.process(state)

        # 기본값 0.5 → moderate
        assert result["content_analysis"]["depth_level"] == "moderate"

    @pytest.mark.asyncio
    async def test_llm_returns_legacy_field_names(
        self,
        agent: ContentAnalyzerAgent,
    ) -> None:
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


# === LangGraph 노드 함수 테스트 ===


class TestContentAnalyzerNode:
    """LangGraph 노드 함수 테스트."""

    @pytest.mark.asyncio
    async def test_node_function_calls_agent(
        self,
        base_state: AgentState,
        mock_llm_response: dict[str, Any],
    ) -> None:
        """content_analyzer_node가 에이전트를 올바르게 호출하는지 확인."""
        with patch.object(
            content_analyzer_agent,
            "process",
            new_callable=AsyncMock,
            return_value={"content_analysis": mock_llm_response},
        ):
            result = await content_analyzer_node(base_state)

        assert "content_analysis" in result

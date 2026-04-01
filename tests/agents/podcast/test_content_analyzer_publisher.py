"""
ContentAnalyzerAgent → AgentDataPublisher 연동 테스트.

ContentAnalyzerAgent.process()가 AgentDataPublisher.publish()를 올바른 인자로
호출하는지, publish() 실패 시 에이전트 반환값에 영향이 없는지 검증한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.content_analyzer import ContentAnalyzerAgent
from src.api.backend_resources import RESOURCE_CONTENT_ANALYSIS
from src.models.agent_state import AgentState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent() -> ContentAnalyzerAgent:
    """테스트용 ContentAnalyzerAgent 인스턴스."""
    return ContentAnalyzerAgent()


@pytest.fixture
def sample_llm_response() -> dict:
    """정상적인 LLM 콘텐츠 분석 응답."""
    return {
        "main_theme": "직장 스트레스 관리",
        "sub_themes": ["업무 과부하", "대인관계", "번아웃 예방"],
        "target_duration": 4,
        "narrative_structure": "personal_story",
        "emotional_journey": ["공감", "분석", "해결책", "마무리"],
        "depth_level": "moderate",
    }


@pytest.fixture
def sample_state() -> AgentState:
    """표준 테스트 상태."""
    return AgentState(
        user_input="직장 스트레스가 심해서 번아웃이 올 것 같아요",
        user_id="user_456",
        session_id="sess_def",
        mode="podcast",
        intent={"primary_intent": "mental_health", "complexity_score": 0.5},
    )


# ---------------------------------------------------------------------------
# Tests: publish() 호출 검증
# ---------------------------------------------------------------------------


class TestContentAnalyzerPublish:
    """ContentAnalyzerAgent가 AgentDataPublisher.publish()를 올바르게 호출하는지 검증."""

    @pytest.mark.asyncio
    async def test_publish_called_with_correct_args(
        self,
        agent: ContentAnalyzerAgent,
        sample_llm_response: dict,
        sample_state: AgentState,
    ) -> None:
        """publish()가 올바른 resource, user/session, data로 호출되는지 통합 검증."""
        mock_publish = AsyncMock(return_value=True)

        with (
            patch.object(
                agent, "call_llm_json", new_callable=AsyncMock, return_value=sample_llm_response
            ),
            patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as MockPublisher,
        ):
            MockPublisher.return_value.publish = mock_publish
            result = await agent.process(sample_state)

        mock_publish.assert_awaited_once()
        call_kwargs = mock_publish.call_args.kwargs
        # resource 검증
        assert call_kwargs["resource"] == RESOURCE_CONTENT_ANALYSIS
        # user/session 검증
        assert call_kwargs["user_id"] == "user_456"
        assert call_kwargs["session_id"] == "sess_def"
        # data 검증
        assert call_kwargs["data"] == result["content_analysis"]

    @pytest.mark.asyncio
    async def test_publish_called_with_empty_user_session_when_missing(
        self,
        agent: ContentAnalyzerAgent,
        sample_llm_response: dict,
    ) -> None:
        """state에 user_id/session_id가 없으면 빈 문자열이 전달된다."""
        state = AgentState(user_input="간단한 주제입니다", mode="podcast")
        mock_publish = AsyncMock(return_value=True)

        with (
            patch.object(
                agent, "call_llm_json", new_callable=AsyncMock, return_value=sample_llm_response
            ),
            patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as MockPublisher,
        ):
            MockPublisher.return_value.publish = mock_publish
            await agent.process(state)

        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["user_id"] == ""
        assert call_kwargs["session_id"] == ""


# ---------------------------------------------------------------------------
# Tests: publish() 실패 시 에이전트 영향 없음
# ---------------------------------------------------------------------------


class TestContentAnalyzerPublishFailure:
    """publish() 실패 시 에이전트 반환값에 영향이 없는지 검증."""

    @pytest.mark.asyncio
    async def test_agent_returns_correctly_when_publish_fails(
        self,
        agent: ContentAnalyzerAgent,
        sample_llm_response: dict,
        sample_state: AgentState,
    ) -> None:
        """publish()가 False를 반환해도 content_analysis는 정상 반환된다."""
        mock_publish = AsyncMock(return_value=False)

        with (
            patch.object(
                agent, "call_llm_json", new_callable=AsyncMock, return_value=sample_llm_response
            ),
            patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as MockPublisher,
        ):
            MockPublisher.return_value.publish = mock_publish
            result = await agent.process(sample_state)

        assert "content_analysis" in result
        assert result["content_analysis"]["main_theme"] == "직장 스트레스 관리"
        assert result["content_analysis"]["narrative_structure"] == "personal_story"

    @pytest.mark.asyncio
    async def test_validated_analysis_preserved_despite_publish_failure(
        self,
        agent: ContentAnalyzerAgent,
        sample_state: AgentState,
    ) -> None:
        """publish() 실패 시에도 _validate_and_correct()의 보정이 적용된 결과가 반환된다."""
        # 범위 밖 target_duration → 보정 후 5분
        llm_response = {
            "main_theme": "테스트",
            "sub_themes": ["a", "b", "c"],
            "target_duration": 99,  # 범위 밖 → max 5
            "narrative_structure": "invalid_structure",  # 유효하지 않음 → reflection
        }
        mock_publish = AsyncMock(return_value=False)

        with (
            patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value=llm_response),
            patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as MockPublisher,
        ):
            MockPublisher.return_value.publish = mock_publish
            result = await agent.process(sample_state)

        analysis = result["content_analysis"]
        assert analysis["target_duration"] == 5  # clamped
        assert analysis["narrative_structure"] == "reflection"  # fallback

    @pytest.mark.asyncio
    async def test_publish_result_does_not_appear_in_return(
        self,
        agent: ContentAnalyzerAgent,
        sample_llm_response: dict,
        sample_state: AgentState,
    ) -> None:
        """에이전트 반환값에 publish 결과가 포함되지 않는다 (기존 계약 유지)."""
        mock_publish = AsyncMock(return_value=True)

        with (
            patch.object(
                agent, "call_llm_json", new_callable=AsyncMock, return_value=sample_llm_response
            ),
            patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as MockPublisher,
        ):
            MockPublisher.return_value.publish = mock_publish
            result = await agent.process(sample_state)

        # AgentState 계약: content_analysis 키만 반환
        assert set(result.keys()) == {"content_analysis"}

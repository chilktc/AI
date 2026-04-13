import time
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.script_generator import ScriptGeneratorAgent
from src.models.agent_state import AgentState


@pytest.fixture
def live_agent(llm_client):
    """Ollama LLM을 사용하는 라이브 테스트용 에이전트."""
    if llm_client is None:
        pytest.skip("Ollama client not available")
    agent = ScriptGeneratorAgent()
    agent.llm_client = llm_client
    return agent


@pytest.mark.live
@pytest.mark.asyncio
async def test_script_generator_title_generation(live_agent):
    start_time = time.time()
    title = await live_agent._generate_title("Mental Health", ["CBT"], {"start_emotion": "sad"})
    elapsed_time = time.time() - start_time
    print(f"\n[Generate Title] ⏱️ 추론 시간: {elapsed_time:.2f}초")
    assert isinstance(title, str)
    assert len(title) > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_script_generator_insights_extraction(live_agent):
    segments = [{"script_text": "첫 번째로 번아웃은 누구에게나 올 수 있는 흔한 증상입니다."}]
    start_time = time.time()
    insights = await live_agent._extract_insights(segments)
    elapsed_time = time.time() - start_time
    print(f"\n[Extract Insights] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert isinstance(insights, list)


@pytest.mark.live
@pytest.mark.asyncio
async def test_script_generator_process(live_agent):
    state = {
        "main_theme": "Mental Health",
        "segment_plan": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "duration_minutes": 1,
                "key_points": ["Welcome"],
                "emotional_tone": "calm",
                "transition_hint": "next",
            }
        ],
        "knowledge_context": {},
    }

    start_time = time.time()
    result = await live_agent.process(state)
    elapsed_time = time.time() - start_time
    print(f"\n[Script Generator Process] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert "script_draft" in result
    draft = result["script_draft"]
    assert "episode_title" in draft
    assert len(draft["segments"]) == 1
    assert "script_text" in draft["segments"][0]
    assert isinstance(draft["key_insights"], list)


@pytest.mark.live
@pytest.mark.asyncio
async def test_script_generator_includes_safety_context_when_warning(live_agent):
    """Safety warning 상태일 때 safety_context가 스크립트 메타데이터에 포함된다."""
    state = {
        "content_analysis": {
            "main_theme": "스트레스 관리",
            "sub_themes": ["번아웃"],
            "emotional_journey": {
                "opening": "불안",
                "development": "이해",
                "climax": "전환",
                "closing": "안정",
            },
            "target_duration": 3,
        },
        "safety_flags": {
            "status": "warning",
            "required_in_script": [
                "전문 상담이 필요하시면 정신건강 위기상담 전화 1577-0199로 연락해주세요."
            ],
        },
        "reasoning_result": {},
        "segment_plan": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "duration_minutes": 1,
                "key_points": ["스트레스 공감"],
                "emotional_tone": "차분함",
                "transition_hint": "",
            }
        ],
        "knowledge_context": {},
    }
    result = await live_agent.process(state)
    draft = result["script_draft"]
    assert "safety_context" in draft["metadata"]
    assert draft["metadata"]["safety_context"]["status"] == "warning"
    assert len(draft["metadata"]["safety_context"]["required_in_script"]) > 0


@pytest.mark.live
@pytest.mark.asyncio
async def test_script_generator_no_safety_context_when_safe(live_agent):
    """Safety safe 상태일 때 safety_context.status가 'safe'이다."""
    state = {
        "content_analysis": {
            "main_theme": "운동 습관",
            "sub_themes": [],
            "emotional_journey": {},
            "target_duration": 3,
        },
        "safety_flags": {"status": "safe"},
        "reasoning_result": {},
        "segment_plan": [
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "duration_minutes": 1,
                "key_points": ["운동"],
                "emotional_tone": "활기참",
                "transition_hint": "",
            }
        ],
        "knowledge_context": {},
    }
    result = await live_agent.process(state)
    draft = result["script_draft"]
    assert draft["metadata"]["safety_context"]["status"] == "safe"


# ──────────────────────────────────────────────
# Mock 기반 단위 테스트 (Ollama 불필요)
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_injects_revision_feedback_into_prompt():
    """iteration_count > 0일 때 validation_result.action이 _generate_segment_script에 전달된다."""
    agent = ScriptGeneratorAgent()

    state = AgentState(
        user_input="스트레스 관리",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        iteration_count=1,
        validation_result={
            "verdict": "FAIL",
            "action": {
                "decision": "revise",
                "revision_instructions": "도입부 감정 공감 강화 필요",
                "priority_fixes": ["도입부 공감 강화", "톤 조정"],
            },
        },
        reasoning_result={"episode_structure": [{"section": "intro", "duration_ratio": 1.0}]},
        content_analysis={"main_theme": "스트레스", "sub_themes": [], "target_duration": 5},
    )

    with (
        patch.object(agent, "_generate_segment_script", new_callable=AsyncMock) as mock_gen,
        patch.object(agent, "_generate_title", new_callable=AsyncMock, return_value="테스트 제목"),
        patch.object(agent, "_extract_insights", new_callable=AsyncMock, return_value=[]),
    ):
        mock_gen.return_value = {
            "segment_id": "seg_1",
            "script_text": "내용",
            "word_count": 10,
            "duration_minutes": 5,
            "emotional_tone": "neutral",
            "tts_markers": [],
        }
        await agent.process(state)

    call_kwargs = mock_gen.call_args.kwargs
    assert "revision_feedback" in call_kwargs
    assert "도입부 감정 공감 강화 필요" in call_kwargs["revision_feedback"]


@pytest.mark.asyncio
async def test_no_revision_feedback_on_first_attempt():
    """iteration_count == 0이면 revision_feedback이 빈 문자열이다."""
    agent = ScriptGeneratorAgent()
    state = AgentState(
        user_input="테스트",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        iteration_count=0,
    )

    with (
        patch.object(agent, "_generate_segment_script", new_callable=AsyncMock) as mock_gen,
        patch.object(agent, "_generate_title", new_callable=AsyncMock, return_value="제목"),
        patch.object(agent, "_extract_insights", new_callable=AsyncMock, return_value=[]),
    ):
        mock_gen.return_value = {
            "segment_id": "s1",
            "script_text": "내용",
            "word_count": 5,
            "duration_minutes": 5,
            "emotional_tone": "neutral",
            "tts_markers": [],
        }
        await agent.process(state)

    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("revision_feedback", "") == ""


@pytest.mark.asyncio
async def test_missing_content_analysis_uses_empty_dict_not_state():
    """content_analysis 없을 때 state 전체가 아닌 빈 dict를 fallback으로 사용한다."""
    agent = ScriptGeneratorAgent()
    state = AgentState(
        user_input="테스트",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        # content_analysis 없음
    )

    with (
        patch.object(agent, "_generate_segment_script", new_callable=AsyncMock) as mock_gen,
        patch.object(agent, "_generate_title", new_callable=AsyncMock, return_value="제목"),
        patch.object(agent, "_extract_insights", new_callable=AsyncMock, return_value=[]),
    ):
        mock_gen.return_value = {
            "segment_id": "s1",
            "script_text": "내용",
            "word_count": 5,
            "duration_minutes": 5,
            "emotional_tone": "neutral",
            "tts_markers": [],
        }
        result = await agent.process(state)

    # state 전체가 아닌 기본값으로 처리됨 — script_draft가 정상 반환되어야 함
    assert "script_draft" in result

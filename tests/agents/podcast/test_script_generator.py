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
        "content_analysis": {
            "main_theme": "마음 건강",
            "sub_themes": [],
            "emotional_journey": {},
            "target_duration": 3,
        },
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
        "knowledge_results": {},
    }

    start_time = time.time()
    result = await live_agent.process(state)
    elapsed_time = time.time() - start_time
    print(f"\n[Script Generator Process] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert "script_draft" in result
    draft = result["script_draft"]
    assert "episode_title" in draft
    assert "script_text" in draft
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
        "knowledge_results": {},
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
        "knowledge_results": {},
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
        content_analysis={"main_theme": "테스트 주제", "sub_themes": [], "target_duration": 5},
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

    # content_analysis 없음 → main_theme 빈 문자열 → 조기 반환
    assert "script_draft" in result
    assert result["script_draft"].get("_error") == "main_theme_missing"
    assert "error" not in result  # top-level error 키 없음


def test_script_generator_source_has_no_mental_health_hardcode() -> None:
    """ScriptGeneratorAgent 소스에 'Mental Health' 하드코딩 없다 (SG-1)."""
    import inspect

    source = inspect.getsource(ScriptGeneratorAgent)
    assert "Mental Health" not in source, "SG-1: Mental Health 하드코딩 발견됨"


@pytest.mark.asyncio
async def test_script_generator_error_path_no_top_level_error_key():
    """실패 시 top-level 'error' 키 대신 script_draft 내부에 _error 포함 (SG-2)."""
    agent = ScriptGeneratorAgent()
    state = AgentState(
        user_input="오늘 하루",
        user_id="u",
        session_id="s",
        mode="podcast",
        content_analysis={"main_theme": "스트레스"},
    )

    # _generate_title에서 예외 발생 → except 블록 진입
    with patch.object(
        agent, "_generate_title", new_callable=AsyncMock, side_effect=RuntimeError("test error")
    ):
        result = await agent.process(state)

    assert "error" not in result, "top-level 'error' 키는 AgentState 미정의"
    assert "script_draft" in result
    assert "_error" in result["script_draft"]


# === Knowledge Results 주입 경로 ===


@pytest.mark.asyncio
async def test_script_generator_reads_knowledge_results_state_key() -> None:
    """ScriptGenerator는 AgentState 정의 필드 knowledge_results를 읽어야 한다.

    - state['knowledge_results']['articles']의 _synthesis 기사 content가
      knowledge_summary로 세그먼트 prompt에 포함되어야 한다.
    - state['knowledge_context']는 AgentState에 없는 키이므로 폴백 경로가
      남아 있으면 안 된다.
    """
    agent = ScriptGeneratorAgent()

    state: AgentState = AgentState(
        content_analysis={
            "main_theme": "번아웃 회복",
            "sub_themes": [],
            "emotional_journey": {"start_emotion": "지침"},
            "target_duration": 2,
        },
        segment_plan=[
            {
                "segment_id": "seg_001",
                "segment_type": "intro",
                "duration_minutes": 1,
                "key_points": ["번아웃 정의"],
                "emotional_tone": "calm",
                "transition_hint": "본론",
            }
        ],
        knowledge_results={
            "articles": [
                {
                    "id": "_synthesis",
                    "title": "검색 결과 종합",
                    "content": "번아웃은 만성 스트레스로 인한 소진 상태이며 CBT가 효과적이다.",
                    "score": 1.0,
                    "source": "KT RAG Suite TextGen",
                }
            ],
            "guidelines": [],
        },
    )

    captured: dict[str, str] = {}

    async def _fake_generate_segment_script(
        self,
        segment,
        episode_title,
        main_theme,
        emotional_journey,
        previous_context,
        knowledge_context,
        revision_feedback="",
    ):
        # 구현이 세그먼트 생성기에 전달하는 knowledge_context를 포착
        captured["knowledge_context"] = repr(knowledge_context)
        return {**segment, "script_text": "테스트 스크립트"}

    with (
        patch.object(
            ScriptGeneratorAgent,
            "_generate_segment_script",
            new=_fake_generate_segment_script,
        ),
        patch.object(
            ScriptGeneratorAgent,
            "_generate_title",
            new=AsyncMock(return_value="테스트 제목"),
        ),
        patch.object(
            ScriptGeneratorAgent,
            "_extract_insights",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await agent.process(state)

    # knowledge_results가 실제로 세그먼트 생성기에 전달되었는지 확인
    assert (
        "번아웃은 만성 스트레스" in captured["knowledge_context"]
    ), "knowledge_results의 _synthesis content가 세그먼트 생성기에 전달되어야 함"


@pytest.mark.asyncio
async def test_script_generator_synthesis_extraction_from_articles() -> None:
    """_generate_segment_script에서 articles 구조로부터 knowledge_summary를 뽑는다."""
    agent = ScriptGeneratorAgent()

    knowledge_context_with_synthesis = {
        "articles": [
            {
                "id": "_synthesis",
                "title": "검색 결과 종합",
                "content": "번아웃은 CBT로 회복 가능하다.",
                "source": "KT RAG Suite TextGen",
            },
            {"id": "d1", "title": "CBT", "content": "본문", "source": "A"},
        ],
        "guidelines": [],
    }

    prompt_capture: dict[str, str] = {}

    async def _fake_call_llm(self, system_prompt, user_message, **kwargs):
        prompt_capture["user_message"] = user_message
        return "생성된 스크립트"

    segment = {
        "segment_id": "seg_001",
        "segment_type": "body",
        "duration_minutes": 2,
        "key_points": ["핵심"],
        "emotional_tone": "calm",
        "transition_hint": "마무리",
    }

    with patch.object(ScriptGeneratorAgent, "call_llm", new=_fake_call_llm):
        await agent._generate_segment_script(
            segment=segment,
            episode_title="T",
            main_theme="번아웃",
            emotional_journey={"start_emotion": "지침"},
            previous_context="",
            knowledge_context=knowledge_context_with_synthesis,
        )

    assert (
        "번아웃은 CBT로 회복 가능하다" in prompt_capture["user_message"]
    ), "articles[0]=_synthesis의 content가 prompt에 포함되어야 함"


@pytest.mark.asyncio
async def test_script_generator_synthesis_fallback_when_no_synthesis() -> None:
    """_synthesis 기사가 없으면 상위 기사 title+content를 조합해 summary를 만든다."""
    agent = ScriptGeneratorAgent()

    knowledge_context_plain = {
        "articles": [
            {"id": "d1", "title": "CBT 인지왜곡", "content": "자동적 사고 이론", "source": "A"},
            {"id": "d2", "title": "DBT 감정조절", "content": "변증법적 치료", "source": "B"},
        ],
        "guidelines": [],
    }

    prompt_capture: dict[str, str] = {}

    async def _fake_call_llm(self, system_prompt, user_message, **kwargs):
        prompt_capture["user_message"] = user_message
        return "생성된 스크립트"

    segment = {
        "segment_id": "seg_001",
        "segment_type": "body",
        "duration_minutes": 2,
        "key_points": [],
        "emotional_tone": "calm",
        "transition_hint": "",
    }

    with patch.object(ScriptGeneratorAgent, "call_llm", new=_fake_call_llm):
        await agent._generate_segment_script(
            segment=segment,
            episode_title="T",
            main_theme="마음",
            emotional_journey={},
            previous_context="",
            knowledge_context=knowledge_context_plain,
        )

    # 상위 기사의 title 또는 content가 prompt에 포함
    assert "CBT 인지왜곡" in prompt_capture["user_message"]
    assert "자동적 사고 이론" in prompt_capture["user_message"]

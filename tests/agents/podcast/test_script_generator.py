import time

import pytest

from src.agents.podcast.script_generator import ScriptGeneratorAgent


@pytest.fixture
def agent(llm_client):
    if llm_client is None:
        pytest.skip("Ollama client not available")
    agent = ScriptGeneratorAgent()
    agent.llm_client = llm_client
    return agent


@pytest.mark.asyncio
async def test_script_generator_title_generation(agent):
    start_time = time.time()
    title = await agent._generate_title("Mental Health", ["CBT"], {"start_emotion": "sad"})
    elapsed_time = time.time() - start_time
    print(f"\n[Generate Title] ⏱️ 추론 시간: {elapsed_time:.2f}초")
    assert isinstance(title, str)
    assert len(title) > 0


@pytest.mark.asyncio
async def test_script_generator_insights_extraction(agent):
    segments = [{"script_text": "첫 번째로 번아웃은 누구에게나 올 수 있는 흔한 증상입니다."}]
    start_time = time.time()
    insights = await agent._extract_insights(segments)
    elapsed_time = time.time() - start_time
    print(f"\n[Extract Insights] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert isinstance(insights, list)


@pytest.mark.asyncio
async def test_script_generator_process(agent):
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
    result = await agent.process(state)
    elapsed_time = time.time() - start_time
    print(f"\n[Script Generator Process] ⏱️ 추론 시간: {elapsed_time:.2f}초")

    assert "script_draft" in result
    draft = result["script_draft"]
    assert "episode_title" in draft
    assert len(draft["segments"]) == 1
    assert "script_text" in draft["segments"][0]
    assert isinstance(draft["key_insights"], list)


@pytest.mark.asyncio
async def test_script_generator_includes_safety_context_when_warning(agent):
    """Safety warning 상태일 때 safety_context가 스크립트 메타데이터에 포함된다."""
    state = {
        "content_analysis": {
            "main_theme": "스트레스 관리",
            "sub_themes": ["번아웃"],
            "emotional_journey": {"opening": "불안", "resolution": "안정"},
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
    result = await agent.process(state)
    draft = result["script_draft"]
    assert "safety_context" in draft["metadata"]
    assert draft["metadata"]["safety_context"]["status"] == "warning"
    assert len(draft["metadata"]["safety_context"]["required_in_script"]) > 0


@pytest.mark.asyncio
async def test_script_generator_no_safety_context_when_safe(agent):
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
    result = await agent.process(state)
    draft = result["script_draft"]
    assert draft["metadata"]["safety_context"]["status"] == "safe"

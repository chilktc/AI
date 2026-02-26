import pytest
from unittest.mock import AsyncMock, patch
from src.agents.podcast.script_generator import ScriptGeneratorAgent
import time

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
        "segment_plan": [{
            "segment_id": "seg_001",
            "segment_type": "intro",
            "duration_minutes": 1,
            "key_points": ["Welcome"],
            "emotional_tone": "calm",
            "transition_hint": "next"
        }],
        "knowledge_context": {}
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

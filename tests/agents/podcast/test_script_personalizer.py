# agents/tests/test_script_personalizer.py
"""
Script Personalizer Agent 테스트

실행:
    pytest agents/tests/test_script_personalizer.py -v -s
"""

import pytest
from src.agents.common.schemas import (
    ValidatedScript,
    ScriptSegment,
    EmotionalJourney,
    UserProfile,
    PersonalizedScript
)
import time
from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent


# =============================================================================
# 테스트 데이터
# =============================================================================

def create_sample_script() -> ValidatedScript:
    """샘플 스크립트"""
    return ValidatedScript(
        episode_title="번아웃, 그것은 나약함이 아닙니다",
        total_duration=15,
        segments=[
            ScriptSegment(
                segment_id="opening",
                segment_type="opening",
                duration_minutes=3,
                script_text="여러분, 안녕하세요. 오늘은 번아웃에 대해 이야기해볼게요. 요즘 많이 지치셨나요?",
                word_count=25,
                emotional_tone="warm",
                tts_markers=[]
            ),
            ScriptSegment(
                segment_id="education",
                segment_type="education",
                duration_minutes=8,
                script_text="번아웃은 단순한 피로가 아닙니다. 세계보건기구에서도 공식적으로 인정한 직업 현상이에요.",
                word_count=30,
                emotional_tone="informative",
                tts_markers=[]
            ),
            ScriptSegment(
                segment_id="closing",
                segment_type="closing",
                duration_minutes=4,
                script_text="오늘 이야기가 도움이 되셨길 바랍니다. 여러분을 응원합니다.",
                word_count=18,
                emotional_tone="hopeful",
                tts_markers=[]
            ),
        ],
        key_insights=["번아웃은 신호다"],
        themes=["번아웃", "스트레스"]
    )


def create_sample_journey() -> EmotionalJourney:
    """샘플 감정 여정"""
    return EmotionalJourney(
        start_emotion="exhausted",
        peak_emotion="understood",
        resolution_emotion="hopeful",
        journey_type="healing"
    )


SAMPLE_PROFILES = {
    "young_casual": UserProfile(
        user_id="user_young",
        age_group="20s",
        preferred_style="casual",
        interaction_history=[],
        preferred_attitude="empathetic"
    ),
    "middle_formal": UserProfile(
        user_id="user_middle",
        age_group="40s",
        preferred_style="formal",
        interaction_history=[{"topic": "stress"}],
        preferred_attitude="rational"
    ),
    "experienced": UserProfile(
        user_id="user_exp",
        age_group="30s",
        preferred_style="neutral",
        interaction_history=[
            {"topic": "anxiety"},
            {"topic": "work"},
            {"topic": "relationships"},
            {"topic": "sleep"},
            {"topic": "stress"},
            {"topic": "burnout"},
        ],
        preferred_attitude="balanced"
    ),
}


# =============================================================================
# 결과 출력 함수
# =============================================================================

def print_script_result(original: ValidatedScript, result: dict, profile_name: str, elapsed_time: float = None):
    """스크립트 개인화 결과 출력"""
    output_str = result.get("final_output", "{}")
    import json
    
    script_data = json.loads(output_str) if output_str else {}
    meta = script_data.get("personalization_meta", {})
    segments = script_data.get("segments", [])
    
    print(f"\n{'='*60}")
    if elapsed_time is not None:
        print(f"⏱️ 추론 시간: {elapsed_time:.2f}초")
    print(f"👤 프로필: {profile_name}")
    print(f"📋 적용 스타일: {meta.get('applied_style')}")
    print(f"🔄 조정된 세그먼트: {meta.get('adjusted_segments')}")
    
    print(f"\n📝 세그먼트 변화:")
    for orig in original.segments:
        pers = next((s for s in segments if s.get('segment_id') == orig.segment_id), None)
        if pers:
            changed = orig.script_text != pers.get('script_text')
            status = "🔄 변경" if changed else "➡️ 유지"
            print(f"\n   [{orig.segment_id}] {status}")
            if changed:
                print(f"   원본: {orig.script_text[:50]}...")
                print(f"   변경: {pers.get('script_text')[:50]}...")
    print(f"{'='*60}")


# =============================================================================
# LLM 없이 테스트 (규칙 기반)
# =============================================================================




# =============================================================================
# LLM 사용 테스트 (MLX)
# =============================================================================

class TestWithLLM:
    """LLM을 직접 사용하는 테스트 (Ollama)"""
    
    @pytest.fixture
    def agent(self, llm_client):
        if llm_client is None:
            pytest.skip("Ollama client not available")
        agent = ScriptPersonalizerAgent(
            db_client=None,
            enable_deep_personalization=True
        )
        agent.llm_client = llm_client
        
        # Mock _get_user_profile to return our sample profiles
        original_get_profile = agent._get_user_profile
        
        def mock_get_profile(user_id):
            for name, profile in SAMPLE_PROFILES.items():
                if profile.user_id == user_id:
                    return profile
            return original_get_profile(user_id)
            
        agent._get_user_profile = mock_get_profile
        
        return agent
    
    @pytest.fixture
    def create_state(self):
        def _create(user_id: str = "test_user"):
            return {
                "user_input": "번아웃 팟캐스트",
                "user_id": user_id,
                "script_draft": create_sample_script().model_dump(),
                "emotional_journey": create_sample_journey().model_dump()
            }
        return _create
    
    @pytest.mark.asyncio
    async def test_llm_basic_personalization(self, agent, create_state):
        """LLM 기본 개인화"""
        state = create_state()
        start_time = time.time()
        result = await agent.process(state)
        elapsed_time = time.time() - start_time
        
        print_script_result(create_sample_script(), result, "LLM 기본", elapsed_time)
        
        assert result.get("final_output") is not None
    
    @pytest.mark.asyncio
    async def test_llm_deep_personalization_threshold(self, agent):
        """심화 개인화 임계값"""
        # 이력 적은 사용자
        new_user = SAMPLE_PROFILES["young_casual"]
        # 이력 많은 사용자
        exp_user = SAMPLE_PROFILES["experienced"]
        
        print(f"\n🔍 심화 개인화 자격:")
        print(f"   young_casual ({len(new_user.interaction_history)}회): {agent._should_deep_personalize(new_user)}")
        print(f"   experienced ({len(exp_user.interaction_history)}회): {agent._should_deep_personalize(exp_user)}")
        
        assert agent._should_deep_personalize(new_user) == False
        assert agent._should_deep_personalize(exp_user) == True
    
    @pytest.mark.asyncio
    async def test_llm_various_profiles(self, agent, create_state):
        """다양한 프로필로 개인화"""
        original = create_sample_script()
        
        for name, profile in SAMPLE_PROFILES.items():
            state = create_state(user_id=profile.user_id)
            start_time = time.time()
            result = await agent.process(state)
            elapsed_time = time.time() - start_time
            
            print_script_result(original, result, name, elapsed_time)
            
            assert result.get("final_output") is not None


# =============================================================================
# 직접 실행
# =============================================================================

if __name__ == "__main__":
    print("\n🚀 Script Personalizer 직접 테스트")
    print("=" * 60)
    
    original = create_sample_script()
    
    # LLM 없이 테스트
    print("\n📌 규칙 기반 테스트")
    agent = ScriptPersonalizerAgent(llm_client=None, db_client=None, enable_deep_personalization=False)
    
    for name, profile in SAMPLE_PROFILES.items():
        state = {
            "user_input": "번아웃 팟캐스트",
            "user_id": profile.user_id,
            "script_draft": original.model_dump(),
            "emotional_journey": create_sample_journey().model_dump()
        }
        result = agent.process(state)
        print_script_result(original, result, name)
    
    # LLM 사용 테스트
    print("\n\n📌 Ollama LLM 테스트")
    try:
        from src.agents.common.llm_client import create_ollama_client
        
        ollama_client = create_ollama_client()
        agent_with_llm = ScriptPersonalizerAgent(
            llm_client=ollama_client,
            db_client=None,
            enable_deep_personalization=True
        )
        
        state = {
            "user_input": "번아웃 팟캐스트",
            "user_id": "user_exp",
            "script_draft": original.model_dump(),
            "emotional_journey": create_sample_journey().model_dump()
        }
        result = agent_with_llm.process(state)
        print_script_result(original, result, "LLM experienced")
        
    except ImportError:
        print("⚠️ openai 모듈을 사용할 수 없습니다. pip install openai")
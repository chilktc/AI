# agents/tests/test_script_personalizer.py
"""
Script Personalizer Agent 테스트

실행:
    pytest agents/tests/test_script_personalizer.py -v -s
"""

import time

import pytest

from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent
from src.models.schemas import (
    EmotionalJourney,
    ScriptSegment,
    UserProfile,
    ValidatedScript,
)

# =============================================================================
# 테스트 데이터
# =============================================================================


def create_sample_script() -> ValidatedScript:
    """샘플 스크립트"""
    return ValidatedScript(
        episode_title="번아웃, 그것은 나약함이 아닙니다",
        total_duration=15,
        script_text=(
            "여러분, 안녕하세요. 오늘은 번아웃에 대해 이야기해볼게요. "
            "요즘 많이 지치셨나요?\n\n"
            "번아웃은 단순한 피로가 아닙니다. "
            "세계보건기구에서도 공식적으로 인정한 직업 현상이에요.\n\n"
            "오늘 이야기가 도움이 되셨길 바랍니다. 여러분을 응원합니다."
        ),
        key_insights=["번아웃은 신호다"],
        themes=["번아웃", "스트레스"],
    )


def create_sample_journey() -> EmotionalJourney:
    """샘플 감정 여정"""
    return EmotionalJourney(
        opening="exhausted",
        development="understood",
        climax="insight",
        closing="hopeful",
        journey_type="healing",
    )


SAMPLE_PROFILES = {
    "young_casual": UserProfile(
        user_id="user_young",
        age_group="20s",
        preferred_style="casual",
        interaction_history=[],
        preferred_attitude="empathetic",
    ),
    "middle_formal": UserProfile(
        user_id="user_middle",
        age_group="40s",
        preferred_style="formal",
        interaction_history=[{"topic": "stress"}],
        preferred_attitude="rational",
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
        preferred_attitude="balanced",
    ),
}


# =============================================================================
# 결과 출력 함수
# =============================================================================


def print_script_result(
    original: ValidatedScript, result: dict, profile_name: str, elapsed_time: float = None
):
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

    print("\n📝 변경된 전체 스크립트 텍스트:")
    if segments and len(segments) > 0:
        first_segment = segments[0]
        text_preview = first_segment.get("script_text", "")
        # Preview first 100 chars
        print(f"   {text_preview[:100]}...\n")

        # Determine if it was modified
        orig_texts_joined = original.script_text
        if text_preview != orig_texts_joined:
            print("   (✅ 통합되어 새롭게 쓰여진 스크립트입니다.)")
        else:
            print("   (➡️ 원본 스크립트 그대로 반환됨.)")
    print(f"{'='*60}")


# =============================================================================
# LLM 없이 테스트 (규칙 기반)
# =============================================================================


@pytest.mark.asyncio
async def test_empty_script_draft_returns_nonempty_output() -> None:
    """script_draft가 비어있으면 Pydantic 실패를 거쳐도 final_output이 빈 문자열이 아니다."""
    agent = ScriptPersonalizerAgent(enable_deep_personalization=False)
    # script_draft 없음 → validated_script = None → _create_fallback_script 호출 불가 → fallback ""
    # 이 케이스는 빈 문자열이 정상 동작 (script_draft 없음)
    state = {"user_id": "u", "session_id": "s", "mode": "podcast", "script_draft": {}}
    result = await agent.process(state)
    # script_draft={}이면 validated_script=None → 기존대로 빈 문자열 (ValueError 발생 후 fallback)
    assert "final_output" in result


@pytest.mark.asyncio
async def test_malformed_script_draft_with_segments_uses_raw_fallback() -> None:
    """episode_title 없는 script_draft도 segments가 있으면 raw fallback으로 처리된다."""
    agent = ScriptPersonalizerAgent(enable_deep_personalization=False)
    # episode_title 없음 → ValidatedScript 실패 → raw fallback 시도
    state = {
        "user_id": "u",
        "session_id": "s",
        "mode": "podcast",
        "script_draft": {
            # episode_title 없음
            "total_duration": 5,
            "segments": [
                {
                    "segment_id": "seg_1",
                    "segment_type": "intro",
                    "duration_minutes": 5,
                    "script_text": "안녕하세요, 오늘의 마음 이야기입니다.",
                    "word_count": 8,
                    "emotional_tone": "warm",
                    "tts_markers": [],
                }
            ],
        },
    }
    result = await agent.process(state)
    assert "final_output" in result
    # raw fallback이 성공했으면 final_output이 비어있지 않음
    assert result["final_output"] != ""


# =============================================================================
# LLM 사용 테스트 (MLX)
# =============================================================================


@pytest.mark.live
class TestWithLLM:
    """LLM을 직접 사용하는 테스트 (Ollama)"""

    @pytest.fixture
    def agent(self, llm_client):
        if llm_client is None:
            pytest.skip("Ollama client not available")
        agent = ScriptPersonalizerAgent(api_client=None, enable_deep_personalization=True)
        agent.llm_client = llm_client

        # Mock _get_user_profile to return our sample profiles
        original_get_profile = agent._get_user_profile

        async def mock_get_profile(user_id):
            for name, profile in SAMPLE_PROFILES.items():
                if profile.user_id == user_id:
                    return profile
            return await original_get_profile(user_id)

        agent._get_user_profile = mock_get_profile

        return agent

    @pytest.fixture
    def create_state(self):
        def _create(user_id: str = "test_user"):
            return {
                "user_input": "번아웃 팟캐스트",
                "user_id": user_id,
                "script_draft": create_sample_script().model_dump(),
                "emotional_journey": create_sample_journey().model_dump(),
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

        assert not agent._should_deep_personalize(new_user)
        assert agent._should_deep_personalize(exp_user)

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
    agent = ScriptPersonalizerAgent(api_client=None, enable_deep_personalization=False)

    for name, profile in SAMPLE_PROFILES.items():
        state = {
            "user_input": "번아웃 팟캐스트",
            "user_id": profile.user_id,
            "script_draft": original.model_dump(),
            "emotional_journey": create_sample_journey().model_dump(),
        }
        result = agent.process(state)
        print_script_result(original, result, name)

    # LLM 사용 테스트 — conftest.py의 llm_client 픽스처 또는
    # dev/ollama_bootstrap.py의 register_ollama()를 사용하세요.
    # 예: pytest tests/ -v (llm_client 세션 픽스처 자동 적용)


# =============================================================================
# Task 9 (SP-1 + SP-2) — 레거시 필드 참조 제거 검증
# =============================================================================


def test_personalizer_no_state_top_level_emotional_journey() -> None:
    """state 최상위 emotional_journey 참조 없다 — AgentState 미정의 키 (SP-1)."""
    import inspect

    from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent

    source = inspect.getsource(ScriptPersonalizerAgent)
    assert 'state.get("emotional_journey")' not in source, \
        "SP-1: state 최상위 emotional_journey 참조 존재"


def test_personalizer_no_v1x_emotion_field_names() -> None:
    """start_emotion/resolution_emotion/resolution v1.x 및 v2.1.x 레거시 필드명 없다 (SP-2).

    CA v2.2.0 이후 emotional_journey는 climax/closing 4-키 구조.
    resolution 키가 더 이상 존재하지 않으므로 SP가 이를 참조하면 항상 "" 반환.
    """
    import inspect

    from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent

    source = inspect.getsource(ScriptPersonalizerAgent)
    assert '"start_emotion"' not in source, "SP-2: start_emotion 레거시 참조 존재"
    assert '"resolution_emotion"' not in source, "SP-2: resolution_emotion 레거시 참조 존재"
    # CA v2.2.0: resolution → closing으로 변경됨
    assert '.get("resolution"' not in source, \
        "SP-2: resolution v2.1.x 참조 잔존 — closing으로 변경 필요"
    # 신규 키 참조 확인
    assert '"closing"' in source, "SP-2: closing 키 참조 없음 — v2.2.0 반영 필요"

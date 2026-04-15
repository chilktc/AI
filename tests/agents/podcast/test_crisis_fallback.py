"""TIER 2~4 에이전트 CRISIS 폴백 단위 테스트.

각 에이전트가 safety_flags.status="crisis" 상태에서 LLM 미호출 + 올바른 CRISIS 폴백 값을
반환하는지 검증한다. LLM 호출 여부는 call_llm_json/call_llm 모킹으로 확인한다.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_crisis_state(**overrides: Any) -> dict[str, Any]:
    """CRISIS 판정 후 TIER 2에 전달되는 AgentState."""
    from src.agents.shared.safety_constants import SAFETY_MESSAGES

    base: dict[str, Any] = {
        "user_input": "너무 힘들어서 죽고 싶다",
        "user_id": "test_user",
        "session_id": "sess_crisis_test",
        "safety_flags": {
            "status": "crisis",
            "risk_level": 4,
            "risk_score": 0.95,
            "required_in_script": [SAFETY_MESSAGES["crisis"]],
        },
        "risk_level": 4,
        "risk_score": 0.95,
        # TIER 1 에이전트들이 정상 실행된 결과 (TIER 1은 취소 안 됨)
        "content_analysis": {
            "main_theme": "정서적 위기",
            "sub_themes": ["힘듦", "지지", "안내"],
            "emotional_journey": {
                "opening": "고통",
                "development": "공감",
                "climax": "위기",
                "closing": "안내",
            },
            "key_messages": ["전문 도움이 필요합니다"],
            "user_summary": {"keywords": ["위기"], "summary": "위기 상황"},
            "target_duration": 4,
            "narrative_structure": "reflection",
            "confidence": 0.3,
            "depth_level": "light",
        },
        "emotion_vectors": {
            "primary_emotion": "crisis",
            "intensity": 0.95,
            "valence": -0.9,
            "arousal": 0.9,
            "secondary_emotions": [],
            "tone_recommendation": "supportive_neutral",
            "emotional_journey_hint": ["안정화 단계"],
        },
        "intent": {"intent_type": "unknown", "complexity_score": 0.0},
        "script_draft": None,
    }
    base.update(overrides)
    return base


class TestScriptGeneratorCrisisFallback:
    """ScriptGenerator: CRISIS 시 LLM 미호출 + script_draft 하드코딩 반환."""

    @pytest.mark.asyncio
    async def test_crisis_returns_hardcoded_script_draft(self) -> None:
        """CRISIS 상태에서 script_draft가 CRISIS 하드코딩 값으로 반환된다."""
        from src.agents.podcast.script_generator import ScriptGeneratorAgent
        from src.agents.shared.safety_constants import SAFETY_MESSAGES

        agent = ScriptGeneratorAgent()
        with (
            patch.object(agent, "call_llm_json", new_callable=AsyncMock) as mock_llm_json,
            patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_llm,
        ):
            result = await agent.process(_make_crisis_state())

        # LLM 미호출 검증
        mock_llm_json.assert_not_called()
        mock_llm.assert_not_called()

        # script_draft 반환 검증
        assert "script_draft" in result
        sd = result["script_draft"]
        assert sd["episode_title"] == "마음 돌봄 안내"
        assert SAFETY_MESSAGES["crisis"][:20] in sd["script_text"]
        assert sd["tts_markers"] == []

    @pytest.mark.asyncio
    async def test_safe_state_does_not_use_crisis_fallback(self) -> None:
        """safe 상태에서는 CRISIS 폴백 대신 정상 LLM 경로가 호출된다 (회귀)."""
        from src.agents.podcast.script_generator import ScriptGeneratorAgent
        from src.agents.shared.safety_constants import CRISIS_FALLBACK_VALUES

        agent = ScriptGeneratorAgent()
        state = _make_crisis_state(
            safety_flags={"status": "safe"},
        )

        # 정상 LLM 모킹 — CRISIS 폴백 분기를 타지 않는지 확인
        dummy_script = {
            "episode_title": "정상 에피소드",
            "total_duration": 5,
            "script_text": "정상 스크립트 본문",
            "tts_markers": [],
            "key_insights": [],
            "themes": [],
        }
        with patch.object(
            agent, "call_llm_json", new=AsyncMock(return_value=dummy_script)
        ) as mock_llm_json:
            result = await agent.process(state)

        # LLM이 실제로 호출되어야 한다 (CRISIS 폴백이 아닌 경로)
        mock_llm_json.assert_called()
        # CRISIS 폴백 값이 반환되지 않아야 한다
        assert result.get("script_draft") != CRISIS_FALLBACK_VALUES["script_draft"]


class TestVisualizationCrisisFallback:
    """Visualization: CRISIS 시 LLM/이미지 미생성 + visual_data(image_url) 반환."""

    @pytest.mark.asyncio
    async def test_crisis_returns_visual_data_with_image_url(self) -> None:
        """CRISIS 상태에서 visual_data가 non-empty image_url과 함께 반환된다."""
        from src.agents.podcast.visualization import VisualizationAgent
        from src.agents.shared.safety_constants import CRISIS_FALLBACK_IMAGE_URL

        agent = VisualizationAgent.__new__(VisualizationAgent)
        # BaseAgent 최소 초기화
        agent.name = "visualization"
        agent.tier = 2
        agent.logger = MagicMock()

        with (
            patch.object(agent, "call_llm_json", new_callable=AsyncMock) as mock_llm,
            patch.object(agent, "call_image_gen", new_callable=AsyncMock) as mock_img,
        ):
            result = await agent.process(_make_crisis_state())

        # LLM/이미지 생성 미호출
        mock_llm.assert_not_called()
        mock_img.assert_not_called()

        # visual_data 검증
        assert "visual_data" in result
        vd = result["visual_data"]
        assert vd["image_url"] == CRISIS_FALLBACK_IMAGE_URL
        assert vd["image_url"] != "" and vd["image_url"] is not None
        assert vd["status"] == "crisis_fallback"


class TestBatchValidatorCrisisFallback:
    """BatchValidator: CRISIS 시 LLM 미호출 + auto-PASS 반환."""

    @pytest.mark.asyncio
    async def test_crisis_returns_auto_pass(self) -> None:
        """CRISIS 상태에서 verdict="PASS", forced_pass=True가 반환된다."""
        from src.agents.podcast.batch_validator import BatchValidatorAgent

        agent = BatchValidatorAgent()
        state = _make_crisis_state(
            script_draft={  # CRISIS script_draft (ScriptGenerator가 설정했을 값)
                "episode_title": "마음 돌봄 안내",
                "total_duration": 0,
                "script_text": "위기 안내 메시지",
                "tts_markers": [],
                "key_insights": [],
                "themes": [],
            }
        )

        with patch.object(agent, "call_llm_json", new_callable=AsyncMock) as mock_llm:
            result = await agent.process(state)

        mock_llm.assert_not_called()

        assert "validation_result" in result
        vr = result["validation_result"]
        assert vr["verdict"] == "PASS"
        assert vr["forced_pass"] is True
        assert vr["action"]["decision"] == "approve"


class TestScriptPersonalizerCrisisFallback:
    """ScriptPersonalizer: CRISIS 시 LLM 미호출 + PersonalizedScript JSON 반환."""

    @pytest.mark.asyncio
    async def test_crisis_returns_valid_json_with_ep_crisis_id(self) -> None:
        """CRISIS 상태에서 final_output이 유효한 JSON이고 episode_id가 ep_crisis_로 시작한다."""
        from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent
        from src.agents.shared.safety_constants import SAFETY_MESSAGES

        agent = ScriptPersonalizerAgent()
        state = _make_crisis_state(
            script_draft={
                "episode_title": "마음 돌봄 안내",
                "total_duration": 0,
                "script_text": SAFETY_MESSAGES["crisis"],
                "tts_markers": [],
                "key_insights": [],
                "themes": [],
            }
        )

        with (
            patch.object(agent, "_apply_deep_personalization", new_callable=AsyncMock) as mock_deep,
            patch.object(agent, "_get_user_profile", new_callable=AsyncMock),
        ):
            result = await agent.process(state)

        # LLM 심화 개인화 미호출
        mock_deep.assert_not_called()

        # final_output이 유효한 JSON
        assert "final_output" in result
        final_json = result["final_output"]
        assert final_json != "", "final_output이 빈 문자열"

        parsed = json.loads(final_json)
        assert parsed["episode_id"].startswith(
            "ep_crisis_"
        ), f"episode_id가 ep_crisis_로 시작하지 않음: {parsed['episode_id']!r}"
        assert SAFETY_MESSAGES["crisis"][:20] in parsed["script_text"]
        assert parsed["personalization_meta"]["attitude_applied"] == "crisis"

    @pytest.mark.asyncio
    async def test_crisis_final_output_parseable_by_build_episode_data(self) -> None:
        """CRISIS final_output이 _build_episode_data()에서 파싱 가능하다."""

        from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent
        from src.agents.shared.safety_constants import SAFETY_MESSAGES
        from src.api.routes.podcasts import _build_episode_data

        agent = ScriptPersonalizerAgent()
        state = _make_crisis_state(
            script_draft={
                "episode_title": "마음 돌봄 안내",
                "total_duration": 0,
                "script_text": SAFETY_MESSAGES["crisis"],
                "tts_markers": [],
                "key_insights": [],
                "themes": [],
            }
        )

        with patch.object(agent, "_get_user_profile", new_callable=AsyncMock):
            sp_result = await agent.process(state)

        state["final_output"] = sp_result["final_output"]
        episode_data = _build_episode_data(state)

        assert episode_data.episode_id.startswith("ep_crisis_")
        assert episode_data.script_text != ""
        assert SAFETY_MESSAGES["crisis"][:20] in episode_data.script_text

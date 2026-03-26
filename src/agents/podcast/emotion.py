from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.context_utils import clamp
from src.api.backend_resources import RESOURCE_EMOTION_LOG
from src.api.publisher import AgentDataPublisher
from src.models.agent_state import AgentState


class EmotionAgent(BaseAgent):
    """
    Emotion Agent (TIER 1)

    ✅ 출력 키: emotion_vectors
    - BatchValidator/ContentAnalyzer가 기대하는 키 스펙을 고정합니다.
    - valence(-1~1), arousal(0~1) 유지
    - emotional_journey_hint는 안정적으로 list 반환

    [TIER 1 규칙]
    - user_input, intent(TIER0)까지만 참조합니다.
    """

    def __init__(self) -> None:
        super().__init__(name="emotion", tier=1)

    async def process(self, state: AgentState) -> dict[str, Any]:
        user_input = str(state.get("user_input", ""))
        intent = state.get("intent", {})
        if not isinstance(intent, dict):
            intent = {}

        try:
            vec = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=(
                    f"[사용자 입력]\n{user_input}\n\n"
                    f"[Intent 참고(TIER0)]\n{intent}\n\n"
                    "반드시 JSON으로 반환:\n"
                    "{\n"
                    '  "primary_emotion": str,\n'
                    '  "intensity": float (0~1),\n'
                    '  "valence": float (-1~1),\n'
                    '  "arousal": float (0~1),\n'
                    '  "secondary_emotions": list[str],\n'
                    '  "tone_recommendation": str,\n'
                    '  "emotional_journey_hint": list[str]\n'
                    "}\n"
                ),
            )
        except KeyError:
            text = user_input
            primary = "anxiety" if "불안" in text else ("sadness" if "우울" in text else "neutral")
            vec = {
                "primary_emotion": primary,
                "intensity": 0.7 if primary != "neutral" else 0.3,
                "valence": -0.4 if primary in ("anxiety", "sadness") else 0.0,
                "arousal": 0.7 if primary == "anxiety" else 0.3,
                "secondary_emotions": [],
                "tone_recommendation": "supportive_neutral",
                "emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],
            }

        secondary = vec.get("secondary_emotions", [])
        journey = vec.get("emotional_journey_hint", [])

        emotion_vectors = {
            "primary_emotion": str(vec.get("primary_emotion", "neutral")),
            "intensity": clamp(vec.get("intensity", 0.3), 0.0, 1.0, 0.3),
            "valence": clamp(vec.get("valence", 0.0), -1.0, 1.0, 0.0),
            "arousal": clamp(vec.get("arousal", 0.3), 0.0, 1.0, 0.3),
            "secondary_emotions": secondary if isinstance(secondary, list) else [],
            "tone_recommendation": str(vec.get("tone_recommendation", "supportive_neutral")),
            "emotional_journey_hint": journey if isinstance(journey, list) else [],
        }

        # 백엔드에 감정 데이터 직접 전달 (실패 시 예외 미전파)
        publisher = AgentDataPublisher()
        await publisher.publish(
            resource=RESOURCE_EMOTION_LOG,
            data=emotion_vectors,
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
        )

        return {"emotion_vectors": emotion_vectors}


emotion_agent = EmotionAgent()


async def emotion_node(state: AgentState) -> dict[str, Any]:
    return await emotion_agent(state)
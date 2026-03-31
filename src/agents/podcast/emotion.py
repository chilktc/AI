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

    def _build_intent_context(self, intent: dict) -> str:
        """Intent dict에서 감정 분석에 필요한 필드만 추출한다.

        전체 dict(17개 필드, ~500~800 토큰) 대신 4개 핵심 필드만 전달하여
        요청당 400~700 토큰을 절감한다. Safety Agent 패턴 참고.

        Args:
            intent: TIER 0 Intent Classifier 결과 dict
        Returns:
            감정 분석 참고용 요약 문자열 (3~4줄) 또는 빈 문자열
        """
        if not intent:
            return ""
        flags = intent.get("flags", {}) if isinstance(intent.get("flags"), dict) else {}
        entities = intent.get("detected_entities", {}) if isinstance(intent.get("detected_entities"), dict) else {}
        prior_emotions = entities.get("emotions", [])
        intent_type = intent.get("intent_type", "")
        urgency_level = flags.get("urgency_level", "")
        risk_flag = flags.get("risk_flag", False)

        lines = []
        if intent_type:
            lines.append(f"intent_type: {intent_type}")
        if prior_emotions:
            lines.append(f"detected_emotions: {prior_emotions}")
        if urgency_level:
            lines.append(f"urgency_level: {urgency_level}")
        if risk_flag:
            lines.append(f"risk_flag: {risk_flag}")
        return "\n".join(lines)

    async def process(self, state: AgentState) -> dict[str, Any]:
        """감정 벡터를 추출한다.

        Args:
            state: AgentState — user_input, intent 필드 읽음
        Returns:
            {"emotion_vectors": {...}} — AgentState에 병합됨
        """
        user_input = str(state.get("user_input", ""))
        intent = state.get("intent", {})
        if not isinstance(intent, dict):
            intent = {}

        intent_context = self._build_intent_context(intent)
        intent_section = f"[Intent 참고]\n{intent_context}\n\n" if intent_context else ""

        try:
            vec = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=(
                    f"[사용자 입력]\n{user_input}\n\n"
                    f"{intent_section}"
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


async def emotion_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Emotion Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = EmotionAgent()
    return await agent(state)
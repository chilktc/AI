from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class SafetyAgent(BaseAgent):
    """
    Safety Agent (TIER 1)
    ✅ 출력 키: safety_flags

    [중요] required_in_script는 BatchValidator가 "리스트"라고 가정하고 읽습니다.
    - status가 safe여도 반드시 []를 반환하도록 보장합니다.
      (None이면 downstream에서 NoneType 에러 가능)

    [TIER 1 규칙]
    - user_input, intent(TIER 0)까지만 참조합니다.
      같은 TIER 1 결과(content_analysis/emotion_vectors 등)는 참조하지 않습니다.
    """

    CRISIS_KEYWORDS = (
        "자살",
        "자해",
        "죽고 싶",
        "살고 싶지",
        "목숨",
        "극단적 선택",
        "죽어버릴",
        "해치고 싶",
        "살인",
        "폭력",
    )

    def __init__(self) -> None:
        super().__init__(name="safety", tier=1)

    async def process(self, state: AgentState) -> dict[str, Any]:
        user_input = str(state.get("user_input", ""))
        intent = state.get("intent", {})  # ✅ TIER0 only
        if not isinstance(intent, dict):
            intent = {}

        crisis_hit = any(k in user_input for k in self.CRISIS_KEYWORDS)
        risk_flag = bool(intent.get("risk_flag", False))

        llm_judgement: dict[str, Any] | None = None
        try:
            llm_judgement = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=(
                    f"[사용자 입력]\n{user_input}\n\n"
                    f"[Intent 참고(TIER0)]\n{intent}\n\n"
                    "반드시 JSON으로 반환:\n"
                    "{\n"
                    '  "status": "safe"|"warning"|"crisis",\n'
                    '  "reasons": list[str],\n'
                    '  "required_in_script": list[str],\n'
                    '  "forbidden_topics": list[str]\n'
                    "}\n\n"
                    "중요:\n"
                    "- required_in_script에는 downstream이 그대로 스크립트에 넣을 수 있는 "
                    "구체적인 안전 고지 문구를 넣어주세요.\n"
                    "- status=safe여도 required_in_script는 반드시 빈 리스트([])로 포함하세요.\n"
                ),
            )
        except KeyError:
            llm_judgement = None

        # ---- 최종 결정 + 보정 ----
        if isinstance(llm_judgement, dict) and llm_judgement:
            status = str(llm_judgement.get("status", "safe"))
            reasons = llm_judgement.get("reasons", [])
            required_in_script = llm_judgement.get("required_in_script", [])
            forbidden_topics = llm_judgement.get("forbidden_topics", [])
        else:
            status = "crisis" if crisis_hit else ("warning" if risk_flag else "safe")
            reasons = []
            forbidden_topics = []
            required_in_script = []

        # 타입 보정: 항상 list
        if not isinstance(reasons, list):
            reasons = []
        if not isinstance(forbidden_topics, list):
            forbidden_topics = []
        if not isinstance(required_in_script, list):
            required_in_script = []

        # 상태 보정
        if status not in ("safe", "warning", "crisis"):
            status = "warning" if (crisis_hit or risk_flag) else "safe"

        # status별 기본 안전문구(LLM이 비워도 최소 보장)
        if status == "warning" and len(required_in_script) == 0:
            required_in_script = [
                "본 내용은 일반적인 정보 제공이며, 의학적 진단이나 치료를 대체하지 않습니다.",
                "불편함이 지속되면 전문가 상담 또는 공신력 있는 기관의 도움을 권합니다.",
            ]
        if status == "crisis" and len(required_in_script) == 0:
            required_in_script = [
                "지금 즉시 주변의 도움을 받을 수 있는 사람/기관에 연락해 주세요.",
                "위급한 상황이라면 지역의 긴급전화/응급서비스를 이용해 주세요.",
            ]

        # ✅ safe여도 required_in_script는 항상 []로 존재해야 함 (이미 보정 완료)

        safety_flags = {
            "status": status,
            "reasons": reasons,
            "forbidden_topics": forbidden_topics,
            "required_in_script": required_in_script,  # ✅ 항상 list
            "tone_guidelines": {
                "avoid_medical_claims": True,
                "avoid_diagnosis": True,
                "use_supportive_neutral_tone": True,
            },
            "_debug": {
                "rule_crisis_hit": crisis_hit,
                "intent_risk_flag": risk_flag,
                "llm_used": bool(llm_judgement),
            },
        }

        return {"safety_flags": safety_flags}


safety_agent = SafetyAgent()


async def safety_node(state: AgentState) -> dict[str, Any]:
    return await safety_agent(state)
"""
Safety Agent — 사용자 입력의 안전성 판정 및 위기 선점.

TIER 1 (병렬) | 모델: settings.yaml 설정을 따름 (기본 Sonnet)
"""
from __future__ import annotations

from typing import Any
from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.safety_constants import SAFETY_MESSAGES
from src.models.agent_state import AgentState

class SafetyAgent(BaseAgent):
    """사용자 입력의 위험도를 평가하고, CRISIS 시 즉시 대응 로직을 트리거한다."""

    def __init__(self) -> None:
        # [정석 복구] 하드코딩을 제거하고 BaseAgent의 자동 설정 로드 방식을 따릅니다.
        # super().__init__ 호출 시 name="safety"를 통해 settings.yaml의 설정을 읽어옵니다.
        super().__init__(name="safety", tier=1)

    async def process(self, state: AgentState) -> dict[str, Any]:
        """안전성 판정 및 시스템 상수 결합 로직을 수행한다."""
        user_input = state.get("user_input", "")
        
        # [최적화] AGENT_IO_ANALYSIS.md 권고에 따라 intent 전체가 아닌 risk_flag만 추출
        intent = state.get("intent", {})
        risk_flag = intent.get("flags", {}).get("risk_flag", False)
        
        # LLM 컨텍스트 구성 (토큰 절약형)
        intent_ref = f"[Intent 위기감지 참고] risk_flag: {risk_flag}\n\n" if risk_flag else ""
        
        # [품질 강화] 모델이 답변 뒤에 사족을 붙여 JSON 파싱 에러(Extra data)가 나는 것을 방지하기 위해 지시문 추가
        user_message = (
            f"{intent_ref}사용자 입력 분석 요청:\n{user_input}\n\n"
            "IMPORTANT: Respond ONLY with a valid JSON object. "
            "No preamble, no explanation, no markdown backticks."
        )
        
        # 1. LLM 호출 (시스템 프롬프트는 YAML에서 정의된 경로를 통해 자동 로드됨)
        result = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=user_message
        )
        
        # 2. 판정 결과 및 상태 추출
        status = result.get("status", "safe") # safe, warning, crisis
        risk_level = result.get("risk_level", 0)
        
        # 3. [상수 결합] status가 crisis 또는 warning일 때 고정 문구 주입
        # 법적/임상적 안전 안내 문구를 LLM 생성값보다 우선하여 배치한다.
        if status in SAFETY_MESSAGES:
            system_msg = SAFETY_MESSAGES[status]
            llm_reasons = result.get("reasons", [])
            # 시스템 상수 문구를 리스트의 최상단에 배치
            result["required_in_script"] = [system_msg] + llm_reasons
        
        # 4. [제어 로직] CLAUDE.md의 CRISIS 선점 메커니즘 지원
        update_data = {
            "safety_flags": result,
            "risk_level": risk_level,
            "risk_score": result.get("risk_score", 0.0)
        }
        
        if status == "crisis":
            # TIER 1 병렬 작업을 중단시키는 CANCEL SIGNAL 역할의 next_step 설정
            update_data["next_step"] = "crisis_response"
            
        return update_data

# --- 싱글톤 + 노드 래퍼 ---
# 인스턴스 생성 시점에 settings.yaml을 참조하여 llm_client가 초기화됩니다.
safety_agent = SafetyAgent()

async def safety_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Safety Agent. 3인 합의된 workflow.py에서 호출됨."""
    return await safety_agent(state)
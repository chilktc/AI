"""
Batch Validator — 팟캐스트 스크립트 품질 검증 에이전트.

TIER 3에서 Script Generator(개발자1)가 생성한 script_draft를 검증한다.
검증 실패 시 TIER 2 재시도를 요청한다.
최대 2회 재시도 후에는 강제 통과한다.
iteration_count 증가는 workflow의 increment_iteration_node()가 전담한다.

담당: 개발자3
출력 필드: validation_result
모델: Sonnet 4
"""

from __future__ import annotations

from typing import Any

from config.loader import get_settings
from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.context_utils import build_section
from src.models.agent_state import AgentState

# 시스템 프롬프트는 prompts/podcast/batch_validator.yaml에서 로드한다.
# BaseAgent의 get_prompt()로 접근.


class BatchValidatorAgent(BaseAgent):
    """
    팟캐스트 스크립트 품질 검증 에이전트.

    Script Generator가 생성한 스크립트를 5가지 기준으로 검증하고,
    실패 시 TIER 2 재시도를 요청한다. 최대 2회 재시도.
    """

    def __init__(self) -> None:
        super().__init__(name="batch_validator", tier=3)
        try:
            cfg = get_settings().get_agent_config("batch_validator")
        except Exception:
            cfg = {}
        self.max_retries: int = cfg.get("max_retries", 2)

    async def process(self, state: AgentState) -> dict[str, Any]:
        """스크립트 품질을 검증하고 통과 여부를 결정한다.

        TIER 1/2 결과를 조합해 LLM에 스크립트 품질 검증을 요청하고,
        approve/revise/escalate 판정에 따라 verdict를 설정한다.
        라우팅 결정은 workflow.py의 route_after_tier3_podcast()가 verdict를 읽어 처리한다.

        Args:
            state: 현재 AgentState. 참조 필드 (모두 TIER 1/2 결과):
                - script_draft (dict): Script Generator(TIER 2)가 생성한 스크립트.
                - content_analysis (dict): Content Analyzer(TIER 1) 분석 결과.
                - reasoning_result (dict): Podcast Reasoning(TIER 1) 추론 결과.
                - safety_flags (dict): Safety Agent(TIER 1) 안전 플래그.
                - emotion_vectors (dict): Emotion Agent(TIER 1) 감정 벡터.
                - iteration_count (int): 현재 재시도 횟수 (기본값 0).
                  max_retries 초과 시 강제 통과(forced_pass) 처리에 사용.

        Returns:
            변경된 필드만 포함한 dict:
                - validation_result (dict): 검증 결과 상세.
                  - verdict (str): "PASS" | "FAIL" | "CRITICAL_FAIL".
                  - overall_score (float): 종합 품질 점수.
                  - action (dict): LLM 판정 결과 (decision: approve|revise|escalate).
                  - forced_pass (bool): iteration_count 초과 시만 포함.

        Raises:
            없음. LLM 호출 실패 시 verdict="FAIL" 결과를 반환한다.
        """
        script_draft = state.get("script_draft", {})
        content_analysis = state.get("content_analysis", {})
        reasoning_result = state.get("reasoning_result", {})
        safety_flags = state.get("safety_flags", {})
        emotion_vectors = state.get("emotion_vectors", {})
        iteration_count = state.get("iteration_count", 0)

        # CRISIS 폴백 — LLM 미호출, auto-PASS 반환
        if safety_flags.get("status") == "crisis":
            from src.agents.shared.safety_constants import CRISIS_FALLBACK_VALUES

            self.logger.info("[BatchValidator] CRISIS 폴백 — 자동 PASS")
            return {"validation_result": CRISIS_FALLBACK_VALUES["validation_result"]}

        # 빈 스크립트 조기 반환 — LLM 호출 절약
        if not script_draft:
            self.logger.warning(
                "스크립트가 비어있어 검증 실패 (iteration_count=%d)", iteration_count
            )
            return {
                "validation_result": {
                    "verdict": "FAIL",
                    "overall_score": 0.0,
                    "action": {
                        "decision": "revise",
                        "revision_instructions": (
                            f"Empty script_draft (iteration={iteration_count})"
                        ),
                        "priority_fixes": [],
                    },
                },
            }

        # 검증 컨텍스트 조합
        validation_context = self._build_validation_context(
            script_draft, content_analysis, reasoning_result, safety_flags, emotion_vectors
        )

        # LLM으로 스크립트 품질 검증
        try:
            validation = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=validation_context,
            )
        except Exception as e:
            self.logger.error("[BatchValidator] LLM 호출 실패 — FAIL 처리: %s", e)
            return {
                "validation_result": {
                    "verdict": "FAIL",
                    "decision": "revise",
                    "overall_score": 0.0,
                    "action": {"decision": "revise"},
                    "error": "llm_call_failed",
                }
            }

        # BV-1: LLM 응답에서 명시 필드만 추출
        result = self._build_validation_result(validation)
        decision = result["action"]["decision"]
        passed = decision == "approve"

        if passed:
            self.logger.info("스크립트 검증 통과 (score=%.2f)", result["overall_score"])
            return {"validation_result": result}

        elif decision == "escalate":
            self.logger.warning(
                "스크립트 검증 CRITICAL_FAIL — 평가 미달 (score=%.2f)",
                result["overall_score"],
            )
            return {"validation_result": result}

        elif iteration_count < self.max_retries:
            self.logger.warning(
                "스크립트 검증 실패 — 현재 %d/%d (score=%.2f)",
                iteration_count,
                self.max_retries,
                result["overall_score"],
            )
            return {"validation_result": result}

        else:
            self.logger.warning(
                "스크립트 검증 실패 — 최대 재시도 초과, 강제 통과 (score=%.2f)",
                result["overall_score"],
            )
            result["forced_pass"] = True
            return {"validation_result": result}

    def _build_validation_result(self, validation: dict[str, Any]) -> dict[str, Any]:
        """LLM 응답에서 명시 필드만 추출하고 verdict를 설정한다.

        scores 기반으로 decision을 교차검증하여 LLM hallucination을 보정한다.
        """
        PASS_THRESHOLD = 0.65
        SAFETY_CRITICAL_THRESHOLD = 0.5

        action = validation.get("action", {})
        if not isinstance(action, dict):
            action = {}
        decision = action.get("decision", "revise")
        original_decision = decision

        # 코드 레벨 보정: scores 기반으로 decision 교차검증
        scores = validation.get("scores", {})
        if isinstance(scores, dict) and scores:
            numeric_scores = [float(v) for v in scores.values() if isinstance(v, (int, float))]
            safety_score = float(scores.get("safety_compliance", 1.0))

            if safety_score < SAFETY_CRITICAL_THRESHOLD:
                decision = "escalate"
            elif numeric_scores and all(s >= PASS_THRESHOLD for s in numeric_scores):
                decision = "approve"
            elif numeric_scores and any(s < PASS_THRESHOLD for s in numeric_scores):
                if decision == "approve":
                    decision = "revise"

        if decision != original_decision:
            self.logger.warning(
                "BV decision 보정: %s → %s (scores=%s)",
                original_decision,
                decision,
                scores,
            )

        verdict_map = {"approve": "PASS", "revise": "FAIL", "escalate": "CRITICAL_FAIL"}

        result: dict[str, Any] = {
            "verdict": verdict_map.get(decision, "FAIL"),
            "overall_score": float(validation.get("overall_score", 0.0)),
            "action": {
                "decision": decision,
                "revision_instructions": str(action.get("revision_instructions", "")),
                "priority_fixes": (
                    action.get("priority_fixes", [])
                    if isinstance(action.get("priority_fixes"), list)
                    else []
                ),
            },
        }
        if isinstance(validation.get("scores"), dict):
            result["scores"] = validation["scores"]
        if isinstance(validation.get("critical_issues"), list):
            result["critical_issues"] = validation["critical_issues"]
        return result

    def _build_validation_context(
        self,
        script_draft: dict[str, Any],
        content_analysis: dict[str, Any],
        reasoning_result: dict[str, Any],
        safety_flags: dict[str, Any],
        emotion_vectors: dict[str, Any],
    ) -> str:
        """검증에 필요한 컨텍스트 정보를 조합한다."""
        parts = [self._build_script_context(script_draft)]
        parts.extend(
            self._build_analysis_context(
                content_analysis, reasoning_result, safety_flags, emotion_vectors
            )
        )
        return "\n\n".join(parts)

    def _build_script_context(self, script_draft: dict[str, Any]) -> str:
        """스크립트 세그먼트별 본문을 포함한 검증 컨텍스트를 구성한다."""
        if not script_draft:
            return "[스크립트]\n(스크립트가 비어있음 — 구조 완전성 검증 실패)"

        script_parts: list[str] = []
        title = script_draft.get("episode_title", "")
        if title:
            script_parts.append(f"제목: {title}")

        script_text = script_draft.get("script_text", "")
        if script_text:
            script_parts.append(f"[전체 스크립트]\n{script_text}")

        markers = script_draft.get("tts_markers", [])
        if markers:
            script_parts.append(f"\n[TTS 마커]: {len(markers)}개 적용됨")

        insights = script_draft.get("key_insights", [])
        if insights:
            script_parts.append(f"핵심 인사이트: {insights}")

        content = "\n\n".join(script_parts) if script_parts else "(내용 없음)"
        return f"[스크립트]\n{content}"

    def _build_analysis_context(
        self,
        content_analysis: dict[str, Any],
        reasoning_result: dict[str, Any],
        safety_flags: dict[str, Any],
        emotion_vectors: dict[str, Any],
    ) -> list[str]:
        """콘텐츠 분석·추론·감정·Safety 정보를 검증 섹션으로 구성한다."""
        parts: list[str] = []

        content_sec = build_section(
            "원본 콘텐츠 분석",
            content_analysis,
            ["main_theme", "narrative_structure", "depth_level"],
        )
        if content_sec:
            parts.append(content_sec)

        reasoning_sec = build_section(
            "추론 결과",
            reasoning_result,
            ["narrative_flow", "key_points"],
        )
        if reasoning_sec:
            parts.append(reasoning_sec)

        if emotion_vectors:
            emotion_sec = build_section(
                "사용자 감정 상태",
                emotion_vectors,
                ["primary_emotion", "intensity"],
            )
            if emotion_sec:
                emotion_sec += "\n- 주의: 스크립트의 톤이 위 감정 상태에 적합한지 검증 필요"
                parts.append(emotion_sec)

        # Safety 섹션은 상태별 조건 문구가 있으므로 수동 구성 유지
        if safety_flags:
            status = safety_flags.get("status", "safe")
            safety_parts = [f"[Safety 상태]\n- 상태: {status}"]
            if status == "safe":
                safety_parts.append(
                    "- Safety Agent가 'safe'로 판정하였으므로, "
                    "별도의 안전 경고 문구는 필요하지 않습니다.\n"
                    "- safety_compliance는 유해 콘텐츠 부재와 "
                    "의료/법률 조언 경계만 확인하세요."
                )
            elif status == "warning":
                safety_parts.append(
                    "- 주의: Safety Agent가 'warning'을 "
                    "발행했으므로, 스크립트에 안전 경고 문구가 "
                    "포함되어야 합니다."
                )
                required = safety_flags.get("required_in_script", [])
                if required:
                    safety_parts.append(f"- 스크립트에 포함 필요: {required}")
            parts.append("\n".join(safety_parts))

        return parts


async def batch_validator_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Batch Validator.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = BatchValidatorAgent()
    return await agent(state)

"""
Batch Validator — 팟캐스트 스크립트 품질 검증 에이전트.

TIER 3에서 Script Generator(개발자1)가 생성한 script_draft를 검증한다.
검증 실패 시 iteration_count를 증가시키고 TIER 2 재시도를 요청한다.
최대 2회 재시도 후에는 강제 통과한다.

담당: 개발자3
출력 필드: validation_result, next_step, iteration_count
모델: Sonnet 4
"""

from __future__ import annotations

from typing import Any

from config.loader import get_settings
from src.agents.shared.base_agent import BaseAgent
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
        """
        스크립트 품질을 검증하고 통과 여부를 결정한다.

        입력 (모두 TIER 1/2 결과 — TIER 3이므로 참조 정당):
            - script_draft: Script Generator(TIER 2)가 생성한 스크립트
            - content_analysis: Content Analyzer(TIER 1) 분석 결과
            - reasoning_result: Podcast Reasoning(TIER 1) 추론 결과
            - safety_flags: Safety Agent(TIER 1) 안전 플래그
            - emotion_vectors: Emotion Agent(TIER 1) 감정 벡터 — 톤 적합성 판단용

        출력:
            - validation_result: 검증 결과 상세
            - next_step: 다음 단계 라우팅 ("script_personalizer" 또는 "retry_script")
            - iteration_count: 재시도 카운터 (실패 시 증가)
        """
        script_draft = state.get("script_draft", {})
        content_analysis = state.get("content_analysis", {})
        reasoning_result = state.get("reasoning_result", {})
        safety_flags = state.get("safety_flags", {})
        emotion_vectors = state.get("emotion_vectors", {})
        iteration_count = state.get("iteration_count", 0)

        # 검증 컨텍스트 조합
        validation_context = self._build_validation_context(
            script_draft, content_analysis, reasoning_result, safety_flags, emotion_vectors
        )

        # LLM으로 스크립트 품질 검증
        validation = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=validation_context,
        )

        # 검증 결과에 따른 라우팅 결정
        passed = validation.get("passed", False)

        if passed:
            # 검증 통과 → TIER 4 (Script Personalizer)로 진행
            self.logger.info("스크립트 검증 통과 (score=%.2f)", validation.get("overall_score", 0))
            return {
                "validation_result": validation,
                "next_step": "script_personalizer",
            }

        elif iteration_count < self.max_retries:
            # 검증 실패 + 재시도 가능 → TIER 2 재시도
            new_count = iteration_count + 1
            self.logger.warning(
                "스크립트 검증 실패 — 재시도 %d/%d (score=%.2f)",
                new_count,
                self.max_retries,
                validation.get("overall_score", 0),
            )
            return {
                "validation_result": validation,
                "iteration_count": new_count,
                "next_step": "retry_script",
            }

        else:
            # 검증 실패 + 최대 재시도 초과 → 강제 통과
            self.logger.warning(
                "스크립트 검증 실패 — 최대 재시도 초과, 강제 통과 (score=%.2f)",
                validation.get("overall_score", 0),
            )
            return {
                "validation_result": {**validation, "forced_pass": True},
                "next_step": "script_personalizer",
            }

    def _build_validation_context(
        self,
        script_draft: dict[str, Any],
        content_analysis: dict[str, Any],
        reasoning_result: dict[str, Any],
        safety_flags: dict[str, Any],
        emotion_vectors: dict[str, Any],
    ) -> str:
        """검증에 필요한 컨텍스트 정보를 조합한다."""
        parts = []

        # 스크립트 내용 — 검증에 필요한 핵심 필드만 추출 (토큰 절감)
        if script_draft:
            script_parts = []
            title = script_draft.get("title", "")
            if title:
                script_parts.append(f"제목: {title}")
            full_script = script_draft.get("full_script", "")
            if full_script:
                script_parts.append(f"본문:\n{full_script}")
            # segments에서 구조 정보만 추출 (본문은 full_script에 포함)
            segments = script_draft.get("segments", [])
            if segments:
                seg_summary = ", ".join(
                    s.get("type", "unknown") if isinstance(s, dict) else str(s)
                    for s in segments[:10]  # 최대 10개까지만
                )
                script_parts.append(f"세그먼트 구성: [{seg_summary}] (총 {len(segments)}개)")
            content = "\n".join(script_parts) if script_parts else "(내용 없음)"
            parts.append(f"[스크립트]\n{content}")
        else:
            parts.append("[스크립트]\n(스크립트가 비어있음 — 구조 완전성 검증 실패)")

        # 원본 콘텐츠 분석 (비교 기준)
        if content_analysis:
            parts.append(
                f"[원본 콘텐츠 분석]\n"
                f"- 주제: {content_analysis.get('topic', 'N/A')}\n"
                f"- 유형: {content_analysis.get('episode_type', 'N/A')}\n"
                f"- 깊이: {content_analysis.get('depth_level', 'N/A')}"
            )

        # 추론 결과 (비교 기준)
        if reasoning_result:
            parts.append(
                f"[추론 결과]\n"
                f"- 내러티브: {reasoning_result.get('narrative_flow', 'N/A')}\n"
                f"- 핵심 포인트: {reasoning_result.get('key_points', [])}"
            )

        # 사용자 감정 상태 (톤 적합성 판단 근거)
        if emotion_vectors:
            parts.append(
                f"[사용자 감정 상태]\n"
                f"- 주요 감정: {emotion_vectors.get('primary_emotion', 'N/A')}\n"
                f"- 감정 강도: {emotion_vectors.get('intensity', 'N/A')}\n"
                f"- 주의: 스크립트의 톤이 위 감정 상태에 적합한지 검증 필요"
            )

        # Safety 플래그 (경고 반영 확인용)
        if safety_flags:
            status = safety_flags.get("status", "safe")
            parts.append(f"[Safety 상태]\n- 상태: {status}")
            if status == "warning":
                parts.append("- 주의: 스크립트에 안전 경고 문구가 포함되어야 합니다")

        return "\n\n".join(parts)


# LangGraph 노드 함수로 사용할 에이전트 인스턴스
batch_validator_agent = BatchValidatorAgent()


async def batch_validator_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Batch Validator."""
    return await batch_validator_agent(state)

"""
Learning Agent — 사용자 패턴 학습 에이전트 (비동기).

최종 에피소드 출력 후 비동기로 실행된다.
사용자의 상호작용 패턴(선호 주제, 감정 패턴, 대화 스타일)을 학습하고
결과를 백엔드 API로 저장한다.

팟캐스트 파이프라인의 비동기 후처리 단계에서 실행된다.

담당: 개발자3
출력: 백엔드 API 저장 (AgentState에 직접 반영 없음)
모델: Haiku (경량)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.context_utils import build_context, build_section
from src.api.backend_resources import RESOURCE_LEARNING, TYPE_LEARNING
from src.api.client import BackendClient
from src.api.contracts import SaveRequest
from src.models.agent_state import AgentState

# 시스템 프롬프트는 prompts/podcast/learning.yaml에서 로드한다.
# BaseAgent의 get_prompt()로 접근.


class LearningAgent(BaseAgent):
    """
    사용자 패턴 학습 에이전트 (비동기).

    세션의 전체 처리 결과를 분석하여 사용자 패턴을 학습하고
    백엔드 API에 저장한다. AgentState에는 직접 반영하지 않는다.
    """

    def __init__(self) -> None:
        super().__init__(name="learning", tier=None)  # 비동기 — TIER 없음
        self._api_client = BackendClient()

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        세션 결과를 분석하여 사용자 패턴을 학습한다.

        입력: 전체 AgentState (읽기 전용)
        출력: 빈 dict (AgentState 변경 없음, 백엔드 API로만 저장)
        """
        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        mode = state.get("mode", "podcast")

        # 학습에 필요한 컨텍스트 조합
        learning_context = self._build_learning_context(state)

        # LLM으로 사용자 패턴 분석
        learning_data = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=learning_context,
        )

        # 백엔드 API로 학습 결과 저장
        await self._save_learning_result(
            user_id=user_id,
            session_id=session_id,
            mode=mode,
            learning_data=learning_data,
        )

        # AgentState에는 변경 없음 (비동기 후처리)
        return {}

    def _build_learning_context(self, state: AgentState) -> str:
        """학습 분석에 필요한 세션 컨텍스트를 조합한다."""
        # 사용자 입력 (plain text이므로 build_section 대신 직접 포맷)
        user_input = state.get("user_input", "")
        user_input_sec = f"[사용자 입력]\n{user_input}" if user_input else ""

        emotion_sec = build_section(
            "감정 분석",
            state.get("emotion_vectors", {}),
            ["primary_emotion", "intensity"],
        )

        content_sec = build_section(
            "콘텐츠 분석",
            state.get("content_analysis", {}),
            ["topic", "episode_type"],
        )

        # 의도 분류 — 사용자 관심사 및 복잡도 추적
        intent_sec = build_section(
            "의도 분류",
            state.get("intent", {}),
            ["intent_type", "complexity_score"],
        )

        # 안전성 분석 — 위험 패턴 추적
        safety_sec = build_section(
            "안전성 분석",
            state.get("safety_flags", {}),
            ["status", "risk_score"],
        )

        # 추론 결과 — 세션 깊이 추적
        reasoning_sec = build_section(
            "추론 결과",
            state.get("reasoning_result", {}),
            ["depth_level", "method"],
        )

        # 검증 결과 — 품질 추이 분석
        validation_sec = build_section(
            "검증 결과",
            state.get("validation_result", {}),
            ["overall_score", "safety_compliance"],
        )

        # 최종 출력 — 너무 길면 앞부분만 포함
        final_output = state.get("final_output", "")
        if final_output:
            truncated = final_output[:500] + ("..." if len(final_output) > 500 else "")
            output_sec = f"[최종 출력 (요약)]\n{truncated}"
        else:
            output_sec = ""

        result = build_context(
            user_input_sec,
            emotion_sec,
            content_sec,
            intent_sec,
            safety_sec,
            reasoning_sec,
            validation_sec,
            output_sec,
        )
        return result if result else "세션 데이터가 부족합니다."

    async def _save_learning_result(
        self,
        user_id: str,
        session_id: str,
        mode: str,
        learning_data: dict[str, Any],
    ) -> None:
        """학습 결과를 백엔드 API로 저장한다."""
        try:
            request = SaveRequest(
                user_id=user_id,
                session_id=session_id,
                type=TYPE_LEARNING,
                data={
                    "mode": mode,
                    "learning_data": learning_data,
                },
                timestamp=datetime.now(timezone.utc),
            )
            await self._api_client.save(RESOURCE_LEARNING, request)
            self.logger.info("학습 결과 저장 완료 (user=%s, session=%s)", user_id, session_id)

        except Exception as e:
            # 학습 저장 실패는 파이프라인을 중단하지 않는다 (비동기 후처리)
            self.logger.warning("학습 결과 저장 실패 — %s: %s", type(e).__name__, str(e))


async def learning_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Learning Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = LearningAgent()
    return await agent(state)

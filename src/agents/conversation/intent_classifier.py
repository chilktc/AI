"""
Intent Classifier Agent
사용자 입력의 의도를 분류하고 메타데이터를 추출합니다.

TIER 0 에이전트: 모든 대화의 첫 번째 처리 단계
"""

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.app_config import (
    CRISIS_KEYWORDS,
    DEFAULT_COMPLEXITY_SCORE,
    DEFAULT_INTENT,
    INTENT_TYPES,
    PODCAST_KEYWORDS,
    REDIS_CONFIG,
)
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.models.schemas import (
    DetectedEntities,
    IntentClassifierOutput,
    IntentFlags,
)


class IntentClassifierAgent(BaseAgent):
    """
    Intent Classifier Agent
    [Standard] settings.yaml의 설정을 그대로 따르는 버전입니다.
    """

    def __init__(
        self,
        use_llm: bool = True,
        use_redis: bool = False,
        redis_client: Optional[Any] = None,
    ):
        """
        Args:
            use_llm: LLM 사용 여부
            use_redis: Redis 캐싱 사용 여부
            redis_client: Redis 클라이언트
        """
        # 부모 클래스(BaseAgent)가 settings.yaml에서 
        # intent_classifier에 배정된 모델(haiku)을 자동으로 로드합니다.
        super().__init__(name="intent_classifier", tier=0)

        self.use_llm = use_llm
        if not self.use_llm:
            self.llm_client = None

        self.use_redis = use_redis
        self.redis_client = redis_client

        # 설정값 로드
        self.intent_types = INTENT_TYPES
        self.crisis_keywords = CRISIS_KEYWORDS
        self.podcast_keywords = PODCAST_KEYWORDS

    async def process(self, state: AgentState) -> dict:
        """LangGraph 노드 로직 (원본 유지)"""
        start_time = datetime.now()
        try:
            user_input = state.get("user_input", "")
            user_id = state.get("user_id", "anonymous")
            session_id = state.get("session_id", "session_0")
            trace_id = f"trace_{uuid.uuid4().hex[:12]}"

            self.logger.info(f"[IntentClassifier] Processing user={user_id}")

            previous_intent = self._get_previous_intent(session_id)
            normalized_input = self._normalize_input(user_input)

            # STEP 1: 규칙 기반 빠른 분류
            preliminary_result = self._preliminary_classify(normalized_input)

            if preliminary_result["is_crisis"]:
                result = self._create_crisis_result(trace_id, preliminary_result["detected_keywords"])
                self._cache_result(session_id, trace_id, result)
                return {
                    "intent": result.model_dump(),
                    "risk_level": 4,
                    "risk_score": 1.0,
                    "safety_flags": {"risk_detected": True},
                    "next_step": "safety_intervention",
                }

            # STEP 2: LLM 기반 정밀 분류
            if self.llm_client:
                llm_result = await self._llm_classify(user_input, normalized_input, previous_intent, preliminary_result["intent"])
            else:
                llm_result = self._rule_based_classify(normalized_input, preliminary_result)

            # STEP 3: 결과 최종화
            final_result = self._validate_and_finalize(llm_result, preliminary_result, trace_id)
            self._cache_result(session_id, trace_id, final_result)

            risk_level = 4 if final_result.flags.risk_flag else 0
            next_step = "safety_intervention" if risk_level > 0 else "process_normal"

            return {
                "intent": final_result.model_dump(),
                "risk_level": risk_level,
                "risk_score": 1.0 if risk_level > 0 else 0.0,
                "safety_flags": {"risk_detected": final_result.flags.risk_flag},
                "next_step": next_step,
            }

        except Exception as e:
            self.logger.error(f"[IntentClassifier] Error: {str(e)}")
            fallback = self._create_fallback_result(trace_id if "trace_id" in locals() else "unknown")
            return {"intent": fallback.model_dump(), "risk_level": 0, "next_step": "process_normal"}

    # --- 내부 헬퍼 함수들 (기존과 동일하여 생략 가능하나 전체 요청하셨으므로 유지) ---
    def _normalize_input(self, user_input: str) -> str:
        return user_input.strip().lower()

    def _preliminary_classify(self, normalized_input: str) -> Dict[str, Any]:
        result = {"is_crisis": False, "detected_keywords": [], "intent": DEFAULT_INTENT, "confidence": 0.5}
        for keyword in self.crisis_keywords:
            if keyword in normalized_input:
                result.update({"is_crisis": True, "intent": "crisis", "confidence": 1.0})
                result["detected_keywords"].append(keyword)
        return result

    async def _llm_classify(self, user_input, normalized_input, previous_intent, preliminary_intent) -> Dict[str, Any]:
        previous_context = f"Previous Intent: {previous_intent.get('intent_type')}" if previous_intent else ""
        prompt = self.get_prompt("system_prompt").format(
            previous_context=previous_context,
            preliminary_intent=preliminary_intent,
            user_input=user_input
        )
        return await self.call_llm_json(system_prompt=prompt, user_message=user_input)

    def _rule_based_classify(self, normalized_input, preliminary_result):
        return {"intent_type": preliminary_result["intent"], "complexity_score": 0.5, 
                "detected_entities": {"emotions": [], "topics": [], "persons": []},
                "flags": {"requires_memory": False, "requires_knowledge": False, "visualization_hint": False, "urgency_level": 0, "risk_flag": False}}

    def _validate_and_finalize(self, llm_result, preliminary_result, trace_id) -> IntentClassifierOutput:
        entities = DetectedEntities(**llm_result.get("detected_entities", {"emotions":[], "topics":[], "persons":[]}))
        flags = IntentFlags(**llm_result.get("flags", {"risk_flag": False}))
        return IntentClassifierOutput(
            intent_type=llm_result.get("intent_type", DEFAULT_INTENT),
            complexity_score=llm_result.get("complexity_score", 0.5),
            detected_entities=entities,
            flags=flags,
            trace_id=trace_id,
            classified_at=datetime.now()
        )

    def _create_crisis_result(self, trace_id, detected_keywords) -> IntentClassifierOutput:
        return IntentClassifierOutput(intent_type="crisis", complexity_score=1.0, 
                                      detected_entities=DetectedEntities(emotions=["위기"]), 
                                      flags=IntentFlags(risk_flag=True, urgency_level=3), 
                                      trace_id=trace_id, classified_at=datetime.now())

    def _create_fallback_result(self, trace_id: str) -> IntentClassifierOutput:
        return IntentClassifierOutput(intent_type=DEFAULT_INTENT, complexity_score=0.5, 
                                      detected_entities=DetectedEntities(), flags=IntentFlags(), 
                                      trace_id=trace_id, classified_at=datetime.now())

    def _get_previous_intent(self, session_id):
        return None # Redis 연동 필요 시 구현

    def _cache_result(self, session_id, trace_id, result):
        pass # Redis 연동 필요 시 구현

# --- 노드 생성 함수 ---
async def create_intent_classifier_node(use_llm=True, use_redis=False, redis_client=None):
    agent = IntentClassifierAgent(use_llm=use_llm, use_redis=use_redis, redis_client=redis_client)
    async def _node(state: AgentState): return await agent.process(state)
    return _node
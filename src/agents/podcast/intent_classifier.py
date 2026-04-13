# agents/podcast/intent_classifier.py
"""
Intent Classifier Agent
사용자 입력의 의도를 분류하고 메타데이터를 추출합니다.

TIER 0 에이전트: 모든 대화의 첫 번째 처리 단계
- 1차 위기 감지 (risk_flag) 역할
- complexity_score 산출하여 Reasoning Agent에 전달
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Callable, Coroutine

from config.app_config import (
    CRISIS_KEYWORDS,
    DEFAULT_COMPLEXITY_SCORE,
    DEFAULT_INTENT,
    INTENT_TYPES,
    PODCAST_KEYWORDS,
    REDIS_CONFIG,
)
from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.llm_client import LLMClient
from src.models.agent_state import AgentState
from src.models.schemas import (
    DetectedEntities,
    IntentClassifierOutput,
    IntentFlags,
)


class IntentClassifierAgent(BaseAgent):
    """
    Intent Classifier Agent

    주요 기능:
    1. 규칙 기반 빠른 분류 (위기 상황 우선 감지)
    2. LLM 기반 정밀 분류
    3. 결과 캐싱 (Redis, 선택적)
    """

    def __init__(
        self,
        use_llm: bool = True,
        use_redis: bool = False,
        redis_client: Any | None = None,
    ):
        """
        Args:
            use_llm: LLM 사용 여부
            use_redis: Redis 캐싱 사용 여부
            redis_client: Redis 클라이언트 - 외부에서 주입
        """
        super().__init__(name="intent_classifier", tier=0)

        self.use_llm = use_llm
        if not self.use_llm:
            self.llm_client: LLMClient | None = None  # type: ignore[assignment]

        self.use_redis = use_redis
        self.redis_client = redis_client

        # 설정값 로드
        self.intent_types = INTENT_TYPES
        self.crisis_keywords = CRISIS_KEYWORDS
        self.podcast_keywords = PODCAST_KEYWORDS

    async def process(self, state: AgentState) -> dict:
        """
        LangGraph 노드 함수 (비동기)

        Args:
            state: 대화 상태

        Returns:
            업데이트된 대화 상태
        """
        start_time = datetime.now()

        try:
            # 입력 추출
            user_input = state.get("user_input", "")
            user_id = state.get("user_id", "anonymous")
            session_id = state.get("session_id", "session_0")
            learning_pattern: dict[str, Any] = state.get("learning_pattern") or {}

            # 추적 ID 생성
            trace_id = f"trace_{uuid.uuid4().hex[:12]}"

            self.logger.info(
                f"[IntentClassifier] Processing input for user={user_id}, trace={trace_id}"
            )

            # 이전 intent 조회 (Redis에서, 선택적)
            previous_intent = self._get_previous_intent(session_id)

            # 입력 전처리
            normalized_input = self._normalize_input(user_input)

            # STEP 1: 규칙 기반 빠른 분류 (위기 상황 우선)
            preliminary_result = self._preliminary_classify(normalized_input)

            # 위기 상황이면 LLM 호출 없이 바로 반환 (안전 우선)
            if preliminary_result["is_crisis"]:
                self.logger.warning(
                    "[IntentClassifier] Crisis detected! " "Keywords: %s",
                    preliminary_result["detected_keywords"],
                )
                result = self._create_crisis_result(
                    trace_id=trace_id, detected_keywords=preliminary_result["detected_keywords"]
                )
                self._cache_result(session_id, trace_id, result)
                return {
                    "intent": self._extract_intent_dict(result),
                    "risk_level": 4,
                    "risk_score": 1.0,
                    "safety_flags": {"risk_detected": True, "details": "Crisis keywords detected"},
                }

            # STEP 2: LLM 기반 정밀 분류
            if self.llm_client:
                llm_result = await self._llm_classify(
                    user_input=user_input,
                    normalized_input=normalized_input,
                    previous_intent=previous_intent,
                    preliminary_intent=preliminary_result["intent"],
                    learning_pattern=learning_pattern,
                )
            else:
                # LLM이 없으면 규칙 기반 결과 사용
                self.logger.info(
                    "[IntentClassifier] No LLM client, using rule-based classification"
                )
                llm_result = self._rule_based_classify(
                    normalized_input=normalized_input, preliminary_result=preliminary_result
                )

            # STEP 3: 결과 검증 및 후처리
            final_result = self._validate_and_finalize(
                llm_result=llm_result, preliminary_result=preliminary_result, trace_id=trace_id
            )

            # Redis 캐싱 (선택적)
            self._cache_result(session_id, trace_id, final_result)

            # 처리 시간 로깅
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.info(
                "[IntentClassifier] Completed in %.2fms, " "intent=%s",
                processing_time,
                final_result.intent_type,
            )

            risk_level = 4 if final_result.flags.risk_flag else 0
            risk_score = 1.0 if final_result.flags.risk_flag else 0.0

            return {
                "intent": self._extract_intent_dict(final_result),
                "risk_level": risk_level,
                "risk_score": risk_score,
                "safety_flags": {"risk_detected": final_result.flags.risk_flag},
            }

        except Exception as e:
            self.logger.error("[IntentClassifier] Error: %s", e)

            # 에러 시 기본값 반환
            fallback = self._create_fallback_result(
                trace_id if "trace_id" in locals() else "unknown"
            )
            return {
                "intent": self._extract_intent_dict(fallback),
                "risk_level": 0,
                "risk_score": 0.0,
                "safety_flags": {"risk_detected": False, "error": str(e)},
            }

    # =========================================================================
    # STEP 1: 규칙 기반 빠른 분류
    # =========================================================================

    def _normalize_input(self, user_input: str) -> str:
        """입력 텍스트 정규화"""
        # 앞뒤 공백 제거
        normalized = user_input.strip()
        # 입력 길이 제한 (4000자)
        if len(normalized) > 4000:
            normalized = normalized[:4000]
        # 연속 공백 제거
        normalized = re.sub(r"\s+", " ", normalized)
        # 소문자 변환 (한글은 영향 없음)
        normalized = normalized.lower()
        return normalized

    def _preliminary_classify(self, normalized_input: str) -> dict[str, Any]:
        """
        규칙 기반 1차 분류
        - 위기 키워드 감지
        - 팟캐스트 요청 감지
        - 기본 의도 추정
        """
        result: dict[str, Any] = {
            "is_crisis": False,
            "is_podcast_request": False,
            "detected_keywords": [],
            "intent": DEFAULT_INTENT,
            "confidence": 0.5,
        }

        # 1. 위기 키워드 감지 (최우선)
        for keyword in self.crisis_keywords:
            if keyword in normalized_input:
                result["is_crisis"] = True
                result["detected_keywords"].append(keyword)
                result["intent"] = "crisis"
                result["confidence"] = 1.0

        if result["is_crisis"]:
            return result

        # 2. 팟캐스트 요청 감지
        for keyword in self.podcast_keywords:
            if keyword in normalized_input:
                result["is_podcast_request"] = True
                result["detected_keywords"].append(keyword)
                result["intent"] = "podcast_request"
                result["confidence"] = 0.8
                return result

        # 3. 기본 패턴 매칭
        # 감정 표현 패턴
        emotion_patterns = [
            r"힘들",
            r"우울",
            r"슬[프퍼]",
            r"불안",
            r"걱정",
            r"스트레스",
            r"지[치쳤]",
            r"외로[워움운]",
        ]
        for pattern in emotion_patterns:
            if re.search(pattern, normalized_input):
                result["intent"] = "emotional_support"
                result["confidence"] = 0.7
                return result

        # 질문 패턴 (정보 요청)
        question_patterns = [
            r"\?$",
            r"뭐야",
            r"뭘까",
            r"어떻게",
            r"왜\s",
            r"알려",
            r"설명",
        ]
        for pattern in question_patterns:
            if re.search(pattern, normalized_input):
                result["intent"] = "information"
                result["confidence"] = 0.6
                return result

        # 상담 요청 패턴
        counseling_patterns = [
            r"상담",
            r"고민",
            r"조언",
            r"어떻게\s*해야",
            r"도움",
        ]
        for pattern in counseling_patterns:
            if re.search(pattern, normalized_input):
                result["intent"] = "counseling"
                result["confidence"] = 0.7
                return result

        # 기본값: 일상대화
        result["intent"] = "casual_chat"
        result["confidence"] = 0.5

        return result

    # =========================================================================
    # STEP 2: LLM 기반 정밀 분류
    # =========================================================================

    def _build_llm_prompt(
        self,
        user_input: str,
        previous_intent: dict[str, Any] | None,
        preliminary_intent: str,
        learning_pattern: dict[str, Any] | None = None,
    ) -> str:
        """LLM 프롬프트 생성"""

        previous_context = ""
        if previous_intent:
            previous_context = (
                f"Previous Turn Intent: "
                f"{previous_intent.get('intent_type', 'unknown')}"
                f"\n(Consider conversation continuity)"
            )

        learning_context = ""
        if learning_pattern:
            parts = []
            if "preferred_format" in learning_pattern:
                parts.append(f"Preferred Format: {learning_pattern['preferred_format']}")
            if "emotional_trend" in learning_pattern:
                parts.append(f"Emotional Trend: {learning_pattern['emotional_trend']}")
            if parts:
                learning_context = "User Learning Pattern:\n" + "\n".join(parts)

        # PromptLoader를 통해 yaml에서 로드된 system_prompt 포맷팅
        base_prompt = self.get_prompt("system_prompt")

        prompt = base_prompt.format(
            previous_context=previous_context,
            preliminary_intent=preliminary_intent,
            user_input=user_input,
        )

        if learning_context:
            prompt = f"{learning_context}\n\n{prompt}"

        return prompt

    async def _llm_classify(
        self,
        user_input: str,
        normalized_input: str,
        previous_intent: dict[str, Any] | None,
        preliminary_intent: str,
        learning_pattern: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LLM을 사용한 정밀 분류"""

        prompt = self._build_llm_prompt(
            user_input=user_input,
            previous_intent=previous_intent,
            preliminary_intent=preliminary_intent,
            learning_pattern=learning_pattern,
        )

        try:
            # LLM 클라이언트의 비동기 JSON 생성 메서드 호출
            parsed = await self.call_llm_json(system_prompt=prompt, user_message=user_input)

            # 필수 필드 검증 및 기본값 설정
            parsed.setdefault("intent_type", DEFAULT_INTENT)
            parsed.setdefault("complexity_score", DEFAULT_COMPLEXITY_SCORE)
            parsed.setdefault("detected_entities", {"emotions": [], "topics": [], "persons": []})
            parsed.setdefault(
                "flags",
                {
                    "requires_memory": False,
                    "requires_knowledge": False,
                    "visualization_hint": False,
                    "urgency_level": 0,
                },
            )
            parsed.setdefault("reasoning", "")

            # complexity_score 범위 제한
            parsed["complexity_score"] = max(0.0, min(1.0, float(parsed["complexity_score"])))

            # intent_type 유효성 검증
            if parsed["intent_type"] not in self.intent_types:
                self.logger.warning(
                    "[IntentClassifier] Invalid intent_type: " "%s, using default",
                    parsed["intent_type"],
                )
                parsed["intent_type"] = DEFAULT_INTENT

            return parsed

        except Exception as e:
            self.logger.error("[IntentClassifier] LLM classification failed: %s", e)
            # LLM 실패 시 규칙 기반 결과 사용
            return {
                "intent_type": preliminary_intent,
                "complexity_score": DEFAULT_COMPLEXITY_SCORE,
                "detected_entities": {"emotions": [], "topics": [], "persons": []},
                "flags": {
                    "requires_memory": False,
                    "requires_knowledge": False,
                    "visualization_hint": False,
                    "urgency_level": 0,
                },
                "reasoning": "Fallback to rule-based classification due to LLM error",
            }

    def _rule_based_classify(
        self, normalized_input: str, preliminary_result: dict[str, Any]
    ) -> dict[str, Any]:
        """LLM 없이 규칙 기반으로만 분류"""

        # 복잡도 계산 (간단한 휴리스틱)
        complexity = self._calculate_complexity(normalized_input)

        # 엔티티 추출 (간단한 규칙 기반)
        entities = self._extract_entities_rule_based(normalized_input)

        # 플래그 결정
        flags = self._determine_flags(
            normalized_input=normalized_input,
            intent=preliminary_result["intent"],
            complexity=complexity,
        )

        return {
            "intent_type": preliminary_result["intent"],
            "complexity_score": complexity,
            "detected_entities": entities,
            "flags": flags,
            "reasoning": (
                "Rule-based classification with " f"confidence {preliminary_result['confidence']}"
            ),
        }

    def _calculate_complexity(self, normalized_input: str) -> float:
        """입력의 복잡도 계산"""

        complexity = 0.3  # 기본값

        # 길이 기반 (긴 입력 = 더 복잡)
        length = len(normalized_input)
        if length > 200:
            complexity += 0.3
        elif length > 100:
            complexity += 0.2
        elif length > 50:
            complexity += 0.1

        # 문장 수 기반
        sentences = re.split(r"[.!?。]", normalized_input)
        sentence_count = len([s for s in sentences if s.strip()])
        if sentence_count > 3:
            complexity += 0.2
        elif sentence_count > 1:
            complexity += 0.1

        # 질문 포함 여부
        if "?" in normalized_input:
            complexity += 0.1

        return min(1.0, complexity)

    def _extract_entities_rule_based(self, normalized_input: str) -> dict[str, list[str]]:
        """규칙 기반 엔티티 추출"""

        entities: dict[str, list[str]] = {"emotions": [], "topics": [], "persons": []}

        # 감정 키워드 매핑
        emotion_keywords = {
            "슬픔": ["슬프", "슬퍼", "우울", "눈물"],
            "불안": ["불안", "걱정", "초조", "두려"],
            "분노": ["화나", "짜증", "열받", "분노"],
            "기쁨": ["기쁘", "행복", "좋아", "즐거"],
            "피로": ["피곤", "지치", "힘들", "지침"],
            "외로움": ["외로", "혼자", "고독"],
        }

        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in normalized_input:
                    if emotion not in entities["emotions"]:
                        entities["emotions"].append(emotion)

        # 주제 키워드 매핑
        topic_keywords = {
            "직장": ["회사", "직장", "업무", "일", "상사", "동료"],
            "가족": ["가족", "부모", "엄마", "아빠", "형제", "자녀"],
            "연애": ["연애", "남친", "여친", "애인", "사랑"],
            "학업": ["학교", "공부", "시험", "성적"],
            "건강": ["건강", "아프", "병원", "몸"],
            "수면": ["잠", "수면", "불면", "피곤"],
        }

        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in normalized_input:
                    if topic not in entities["topics"]:
                        entities["topics"].append(topic)

        return entities

    def _determine_flags(
        self, normalized_input: str, intent: str, complexity: float
    ) -> dict[str, Any]:
        """플래그 결정"""

        flags = {
            "requires_memory": False,
            "requires_knowledge": False,
            "visualization_hint": False,
            "urgency_level": 0,
            "risk_flag": False,
        }

        # 메모리 필요 여부 (대화 연속성 힌트)
        memory_hints = ["아까", "전에", "그때", "저번에", "말했던", "이야기했던"]
        for hint in memory_hints:
            if hint in normalized_input:
                flags["requires_memory"] = True
                break

        # 지식 필요 여부 (정보 요청 힌트)
        if intent == "information" or complexity > 0.7:
            flags["requires_knowledge"] = True

        # 시각화 힌트
        visual_hints = ["보여", "그래프", "차트", "이미지", "그림"]
        for hint in visual_hints:
            if hint in normalized_input:
                flags["visualization_hint"] = True
                break

        # 긴급도 (emotional_support나 counseling이면 약간 높임)
        if intent == "emotional_support":
            flags["urgency_level"] = 1
        elif intent == "counseling":
            flags["urgency_level"] = 1
        elif intent == "crisis":
            flags["urgency_level"] = 3
            flags["risk_flag"] = True

        return flags

    # =========================================================================
    # STEP 3: 결과 검증 및 후처리
    # =========================================================================

    def _validate_and_finalize(
        self, llm_result: dict[str, Any], preliminary_result: dict[str, Any], trace_id: str
    ) -> IntentClassifierOutput:
        """결과 검증 및 최종화"""

        # 안전 우선 원칙: preliminary가 crisis면 LLM 결과 무시
        if preliminary_result["is_crisis"] and llm_result["intent_type"] != "crisis":
            self.logger.warning(
                "[IntentClassifier] Overriding LLM result with crisis due to safety-first principle"
            )
            llm_result["intent_type"] = "crisis"
            llm_result["flags"]["urgency_level"] = 3
            llm_result["flags"]["risk_flag"] = True

        # DetectedEntities 객체 생성
        entities = DetectedEntities(
            emotions=llm_result["detected_entities"].get("emotions", []),
            topics=llm_result["detected_entities"].get("topics", []),
            persons=llm_result["detected_entities"].get("persons", []),
        )

        # IntentFlags 객체 생성
        flags = IntentFlags(
            requires_memory=llm_result["flags"].get("requires_memory", False),
            requires_knowledge=llm_result["flags"].get("requires_knowledge", False),
            visualization_hint=llm_result["flags"].get("visualization_hint", False),
            urgency_level=llm_result["flags"].get("urgency_level", 0),
            risk_flag=llm_result["flags"].get("risk_flag", False),
        )

        # 최종 결과 생성
        result = IntentClassifierOutput(
            intent_type=llm_result["intent_type"],
            complexity_score=llm_result["complexity_score"],
            detected_entities=entities,
            flags=flags,
            reasoning=llm_result.get("reasoning"),
            trace_id=trace_id,
            classified_at=datetime.now(),
        )

        return result

    def _create_crisis_result(
        self, trace_id: str, detected_keywords: list[str]
    ) -> IntentClassifierOutput:
        """위기 상황 결과 생성"""

        return IntentClassifierOutput(
            intent_type="crisis",
            complexity_score=1.0,
            detected_entities=DetectedEntities(emotions=["위기"], topics=["안전"], persons=[]),
            flags=IntentFlags(
                requires_memory=False,
                requires_knowledge=False,
                visualization_hint=False,
                urgency_level=3,
                risk_flag=True,
            ),
            reasoning=f"Crisis keywords detected: {detected_keywords}",
            trace_id=trace_id,
            classified_at=datetime.now(),
        )

    def _create_fallback_result(self, trace_id: str) -> IntentClassifierOutput:
        """폴백 결과 생성 (에러 시)"""

        return IntentClassifierOutput(
            intent_type=DEFAULT_INTENT,
            complexity_score=DEFAULT_COMPLEXITY_SCORE,
            detected_entities=DetectedEntities(),
            flags=IntentFlags(),
            reasoning="Fallback result due to processing error",
            trace_id=trace_id,
            classified_at=datetime.now(),
        )

    @staticmethod
    def _extract_intent_dict(result: IntentClassifierOutput) -> dict[str, Any]:
        """IntentClassifierOutput에서 명시된 whitelist 필드만 추출한다 (IC-1).

        model_dump() 대신 명시 추출을 사용하여 Pydantic 모델에 필드가 추가될 때
        의도치 않은 필드가 AgentState의 intent 필드에 유입되는 것을 방지한다.

        Args:
            result: IntentClassifierOutput 인스턴스

        Returns:
            whitelist 필드만 포함한 dict
        """
        return {
            "intent_type": result.intent_type,
            "complexity_score": result.complexity_score,
            "detected_entities": result.detected_entities.model_dump(),
            "flags": result.flags.model_dump(),
            "reasoning": result.reasoning,
            "trace_id": result.trace_id,
            "classified_at": result.classified_at,
        }

    # =========================================================================
    # Redis 캐싱 (선택적)
    # =========================================================================

    def _get_previous_intent(self, session_id: str) -> dict[str, Any] | None:
        """이전 턴의 intent 조회 (Redis에서)"""

        if not self.use_redis or not self.redis_client:
            return None

        try:
            key = f"intent:session:{session_id}:latest"
            cached = self.redis_client.get(key)
            if cached:
                result: dict[str, Any] = json.loads(cached)
                return result
        except Exception as e:
            self.logger.warning("[IntentClassifier] Redis get failed: %s", e)

        return None

    def _cache_result(self, session_id: str, trace_id: str, result: IntentClassifierOutput) -> None:
        """결과를 Redis에 캐싱"""

        if not self.use_redis or not self.redis_client:
            return

        try:
            # 세션별 최신 intent 저장
            key = f"intent:session:{session_id}:latest"
            value = json.dumps(
                {
                    "intent_type": result.intent_type,
                    "complexity_score": result.complexity_score,
                    "trace_id": result.trace_id,
                    "classified_at": result.classified_at.isoformat(),
                }
            )
            self.redis_client.setex(key, REDIS_CONFIG["intent_cache_ttl"], value)

            # 개별 trace 저장
            trace_key = f"intent:{session_id}:{trace_id}"
            self.redis_client.setex(
                trace_key, REDIS_CONFIG["intent_cache_ttl"], result.model_dump_json()
            )

        except Exception as e:
            self.logger.warning("[IntentClassifier] Redis set failed: %s", e)


# =============================================================================
# LangGraph 노드 함수 (외부에서 사용)
# =============================================================================


async def create_intent_classifier_node(
    use_llm: bool = True, use_redis: bool = False, redis_client: Any | None = None
) -> Callable[[AgentState], Coroutine[Any, Any, dict[str, Any]]]:
    """
    LangGraph에서 사용할 노드 함수 생성
    """
    agent = IntentClassifierAgent(use_llm=use_llm, use_redis=use_redis, redis_client=redis_client)

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

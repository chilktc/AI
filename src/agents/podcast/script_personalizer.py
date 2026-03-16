# agents/podcast/script_personalizer.py
"""
Script Personalizer Agent
검증된 스크립트에 사용자 맞춤 스타일을 적용합니다.

TIER 4 에이전트: 팟캐스트 모드의 마지막 처리 단계
- 배치 전체 스타일 조정
- Learning Agent로 학습 이벤트 전송
"""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.app_config import (
    AGE_GROUP_STYLE_DEFAULTS,
    ATTITUDE_SETTINGS,
    DEFAULT_ATTITUDE,
    FORMALITY_REPLACEMENTS,
    STYLE_MAPPINGS,
)
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.models.schemas import (
    EmotionalJourney,
    LearningEvent,
    PersonalizationMeta,
    PersonalizedScript,
    ScriptSegment,
    UserProfile,
    ValidatedScript,
)


class ScriptPersonalizerAgent(BaseAgent):
    """
    Script Personalizer Agent

    주요 기능:
    1. 사용자 프로필 기반 스타일 전략 결정
    2. 규칙 기반 스타일 조정 (호칭, 말투 등)
    3. 심화 개인화 (LLM, 선택적)
    4. Learning Agent로 학습 이벤트 전송
    """

    def __init__(
        self,
        db_client: Optional[Any] = None,
        enable_deep_personalization: bool = False,
    ):
        """
        Args:
            db_client: 데이터베이스 클라이언트 (사용자 프로필 조회용) - 외부에서 주입
            enable_deep_personalization: 심화 개인화 활성화 여부
        """
        super().__init__(name="script_personalizer", tier=4)

        self.enable_deep_personalization = enable_deep_personalization
        if not self.enable_deep_personalization:
            self.llm_client = None

        self.db_client = db_client

    async def process(self, state: AgentState) -> dict:
        """
        LangGraph 노드 함수 (비동기)

        Args:
            state: 팟캐스트 상태

        Returns:
            업데이트된 팟캐스트 상태 파편
        """
        start_time = datetime.now()

        try:
            user_id = state.get("user_id", "anonymous")

            # script_draft에서 Pydantic 객체 복원
            script_data = state.get("script_draft", {})
            validated_script = ValidatedScript(**script_data) if script_data else None
            emotional_journey = None  # LangGraph 설계상 별도 추출 또는 계산 필요

            # 에피소드 ID 생성
            episode_id = f"ep_{uuid.uuid4().hex[:12]}"

            self.logger.info(
                f"[ScriptPersonalizer] Processing for user={user_id}, episode={episode_id}"
            )

            # 검증된 스크립트 확인
            if validated_script is None:
                raise ValueError("validated_script is required but not provided")

            # STEP 1: 사용자 프로필 조회 및 스타일 전략 결정
            user_profile = self._get_user_profile(user_id)
            personalization_strategy = self._determine_strategy(user_profile)

            self.logger.info(f"[ScriptPersonalizer] Strategy: {personalization_strategy}")

            # STEP 2: 규칙 기반 스타일 조정
            adjusted_script, adjusted_segments = self._apply_rule_based_adjustments(
                script=validated_script,
                strategy=personalization_strategy,
                user_profile=user_profile,
            )

            # STEP 3: 심화 개인화 (선택적, LLM 사용)
            if self.enable_deep_personalization and self._should_deep_personalize(user_profile):
                adjusted_script = await self._apply_deep_personalization(
                    script=adjusted_script,
                    user_profile=user_profile,
                    strategy=personalization_strategy,
                    emotional_journey=emotional_journey,
                )

            # STEP 4: 최종 스크립트 구성
            personalized_script = self._finalize_script(
                episode_id=episode_id,
                adjusted_script=adjusted_script,
                strategy=personalization_strategy,
                user_profile=user_profile,
                adjusted_segments=adjusted_segments,
            )

            # 처리 시간 로깅
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.info(f"[ScriptPersonalizer] Completed in {processing_time:.2f}ms")

            return {
                "final_output": personalized_script.model_dump_json()  # 문자열 형태의 최종 스크립트 반환
            }

        except Exception as e:
            self.logger.error(f"[ScriptPersonalizer] Error: {str(e)}")

            # 에러 시 원본 스크립트 그대로 반환
            fallback = ""
            if "validated_script" in locals() and validated_script:
                fallback_script = self._create_fallback_script(
                    validated_script=validated_script, user_id=user_id
                )
                fallback = fallback_script.model_dump_json()

            return {"final_output": fallback}

    # =========================================================================
    # STEP 1: 사용자 프로필 조회 및 스타일 전략 결정
    # =========================================================================

    def _get_user_profile(self, user_id: str) -> UserProfile:
        """
        사용자 프로필 조회

        실제 구현 시 db_client를 통해 MySQL에서 조회
        """

        if self.db_client:
            try:
                profile_data = self._query_user_profile(user_id)
                if profile_data:
                    return UserProfile(**profile_data)
            except Exception as e:
                self.logger.warning(f"[ScriptPersonalizer] Failed to fetch user profile: {str(e)}")

        # 기본 프로필 반환
        self.logger.info(f"[ScriptPersonalizer] Using default profile for user={user_id}")
        return UserProfile(
            user_id=user_id,
            age_group="30s",
            preferred_style="neutral",
            interaction_history=[],
            accessibility_needs=None,
            preferred_attitude=DEFAULT_ATTITUDE,
        )

    def _query_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        데이터베이스에서 사용자 프로필 조회

        이 메서드는 db_client 인터페이스에 맞게 수정 필요
        """
        if self.db_client is None:
            return None

        # MySQL 쿼리 예시 (실제 구현 시 수정 필요)
        # 예: SQLAlchemy, PyMySQL 등에 맞게 조정
        try:
            # 예시 쿼리 구조
            query = """
                SELECT user_id, age_group, preferred_style, 
                       preferred_attitude, accessibility_needs
                FROM user_profiles
                WHERE user_id = %s
            """
            # 실제 실행은 db_client 인터페이스에 따라 다름
            # result = self.db_client.execute(query, (user_id,))
            # return result.fetchone()

            # 현재는 None 반환 (DB 연결 전까지)
            return None

        except Exception as e:
            self.logger.error(f"[ScriptPersonalizer] DB query failed: {str(e)}")
            return None

    def _determine_strategy(self, user_profile: UserProfile) -> Dict[str, Any]:
        """
        사용자 프로필 기반 개인화 전략 결정
        """

        strategy = {
            "formality": "medium",
            "emoji_usage": False,
            "sentence_length": "medium",
            "explanation_depth": "moderate",
            "attitude": DEFAULT_ATTITUDE,
        }

        # 1. 연령대 기반 기본 스타일 적용
        age_group = user_profile.age_group
        if age_group in AGE_GROUP_STYLE_DEFAULTS:
            age_defaults = AGE_GROUP_STYLE_DEFAULTS[age_group]
            strategy.update(age_defaults)

        # 2. 선호 스타일 오버라이드
        preferred_style = user_profile.preferred_style
        if preferred_style in STYLE_MAPPINGS:
            style_override = STYLE_MAPPINGS[preferred_style]
            strategy.update(style_override)

        # 3. 태도 설정
        if user_profile.preferred_attitude:
            strategy["attitude"] = user_profile.preferred_attitude

        # 4. 상호작용 이력 기반 조정 (경험 있는 사용자)
        if len(user_profile.interaction_history) > 5:
            # 더 자세한 설명 제공
            strategy["explanation_depth"] = "detailed"

        return strategy

    # =========================================================================
    # STEP 2: 규칙 기반 스타일 조정
    # =========================================================================

    def _apply_rule_based_adjustments(
        self, script: ValidatedScript, strategy: Dict[str, Any], user_profile: UserProfile
    ) -> tuple:
        """
        규칙 기반 스타일 조정 적용

        Returns:
            tuple: (조정된 스크립트, 조정된 세그먼트 ID 목록)
        """

        # 깊은 복사로 원본 보존
        adjusted_segments = []
        new_segments = []

        formality = strategy.get("formality", "medium")
        replacements = FORMALITY_REPLACEMENTS.get(formality, {})
        attitude = strategy.get("attitude", DEFAULT_ATTITUDE)

        for segment in script.segments:
            # 세그먼트 복사
            new_segment = ScriptSegment(
                segment_id=segment.segment_id,
                segment_type=segment.segment_type,
                duration_minutes=segment.duration_minutes,
                script_text=segment.script_text,
                word_count=segment.word_count,
                emotional_tone=segment.emotional_tone,
                tts_markers=segment.tts_markers.copy() if segment.tts_markers else [],
            )

            script_text = new_segment.script_text
            original_text = script_text

            # 2-1: 호칭/격식 조정 (단어 치환)
            for old_word, new_word in replacements.items():
                script_text = script_text.replace(old_word, new_word)

            # 2-2: 태도 기반 조정
            script_text = self._apply_attitude_adjustment(script_text, attitude)

            # 2-3: 이모지 처리
            if not strategy.get("emoji_usage", False):
                script_text = self._remove_emojis(script_text)

            # 2-4: 접근성 조정
            if user_profile.accessibility_needs:
                script_text, new_segment.tts_markers = self._apply_accessibility_adjustments(
                    script_text, user_profile.accessibility_needs, new_segment.tts_markers
                )

            # 변경 여부 확인
            if script_text != original_text:
                adjusted_segments.append(new_segment.segment_id)

            new_segment.script_text = script_text
            new_segment.word_count = len(script_text.split())
            new_segments.append(new_segment)

        # 조정된 스크립트 생성
        adjusted_script = ValidatedScript(
            episode_title=script.episode_title,
            total_duration=script.total_duration,
            segments=new_segments,
            key_insights=script.key_insights,
            themes=script.themes,
        )

        return adjusted_script, adjusted_segments

    def _apply_attitude_adjustment(self, text: str, attitude: str) -> str:
        """태도 기반 텍스트 조정"""

        if attitude not in ATTITUDE_SETTINGS:
            return text

        settings = ATTITUDE_SETTINGS[attitude]

        # 간단한 규칙: 특정 키워드 앞에 공감 표현 추가
        if attitude == "empathetic":
            # 문장 시작에 공감 표현이 없으면 자연스럽게 유지
            # (실제로는 LLM이 더 잘 처리함)
            pass
        elif attitude == "rational":
            # 감정적 표현을 약간 완화
            pass

        return text

    def _remove_emojis(self, text: str) -> str:
        """이모지 제거"""

        # 이모지 패턴 (간단한 버전)
        # 이모지 패턴 (수정된 버전)
        # 한글 범위(AC00-D7A3)를 건드리지 않도록 주의
        emoji_pattern = re.compile(
            "["
            "\U0001f600-\U0001f64f"  # Emoticons
            "\U0001f300-\U0001f5ff"  # Symbols & Pictographs
            "\U0001f680-\U0001f6ff"  # Transport & Map Symbols
            "\U0001f1e0-\U0001f1ff"  # Flags (iOS)
            "\U00002702-\U000027b0"  # Dingbats
            "]+",
            flags=re.UNICODE,
        )
        return emoji_pattern.sub("", text)

    def _apply_accessibility_adjustments(
        self, text: str, accessibility_needs: List[str], tts_markers: List
    ) -> tuple:
        """접근성 조정 적용"""

        new_markers = list(tts_markers) if tts_markers else []

        if "visual_impairment" in accessibility_needs:
            # TTS를 위한 추가 마커 삽입
            # 문단 사이에 짧은 휴식 추가
            from src.models.schemas import TTSMarker

            # 문장 끝마다 휴식 마커 추가
            sentences = re.split(r"([.!?])", text)
            position = 0
            for sentence in sentences:
                if sentence in ".!?":
                    new_markers.append(TTSMarker(position=position, instruction="pause_short"))
                position += len(sentence)

        if "hearing_impairment" in accessibility_needs:
            # 청각 장애인용: 더 명확한 문장 구조
            # (실제로는 LLM이 더 잘 처리함)
            pass

        return text, new_markers

    # =========================================================================
    # STEP 3: 심화 개인화 (LLM 사용, 선택적)
    # =========================================================================

    def _should_deep_personalize(self, user_profile: UserProfile) -> bool:
        """심화 개인화 적용 여부 결정"""

        # 상호작용 이력이 5회 이상인 경우에만 LLM 호출
        return len(user_profile.interaction_history) > 5

    async def _apply_deep_personalization(
        self,
        script: ValidatedScript,
        user_profile: UserProfile,
        strategy: Dict[str, Any],
        emotional_journey: Optional[EmotionalJourney],
    ) -> ValidatedScript:
        """LLM을 사용한 심화 개인화 (전체 대본 통합 처리)"""

        if not self.llm_client:
            return script

        self.logger.info("[ScriptPersonalizer] Applying deep personalization with LLM (Integrated)")

        # 1. 문서 전체의 세그먼트 내용을 하나로 통합
        integrated_text_blocks = []
        for segment in script.segments:
            integrated_text_blocks.append(
                f"[Segment: {segment.segment_type}]\n{segment.script_text}"
            )
        full_script_text = "\n\n".join(integrated_text_blocks)

        new_segments = []

        try:
            # 2. 통합된 텍스트를 LLM에 한 번에 전달하여 단일 스크립트 확보
            integrated_personalized_text = await self._personalize_integrated_script_with_llm(
                full_script_text=full_script_text,
                user_profile=user_profile,
                strategy=strategy,
                emotional_journey=emotional_journey,
            )

            # 3. 통합된 텍스트를 하나의 'full_episode' 세그먼트에 담아 반환 
            # (Validation/Schemas 와의 호환성을 위해 단일 요소의 list로 처리)
            single_segment = ScriptSegment(
                segment_id="full_episode",
                segment_type="integrated",
                duration_minutes=script.total_duration,
                script_text=integrated_personalized_text,
                word_count=len(integrated_personalized_text.split()),
                emotional_tone="mixed",
                tts_markers=[],
            )
            new_segments.append(single_segment)

        except Exception as e:
            self.logger.warning(
                f"[ScriptPersonalizer] Integrated LLM personalization failed: {str(e)}"
            )
            # 실패 시 원본 그대로 반환
            return script

        return ValidatedScript(
            episode_title=script.episode_title,
            total_duration=script.total_duration,
            segments=new_segments,
            key_insights=script.key_insights,
            themes=script.themes,
        )

    async def _personalize_integrated_script_with_llm(
        self,
        full_script_text: str,
        user_profile: UserProfile,
        strategy: Dict[str, Any],
        emotional_journey: Optional[EmotionalJourney],
    ) -> str:
        """개별 세그먼트 LLM 개인화"""

        # 상호작용 요약 생성
        interaction_summary = self._summarize_interactions(user_profile.interaction_history)

        emotional_context = ""
        if emotional_journey:
            emotional_context = f"""
Emotional Journey:
- Opening: {emotional_journey.opening}
- Development: {emotional_journey.development}
- Resolution: {emotional_journey.resolution}
- Type: {emotional_journey.journey_type}
"""

        prompt = f"""Rewrite and personalize the following entire podcast script into a single, cohesive episode.

Original Integrated Script:
{full_script_text}

User Profile:
- Age Group: {user_profile.age_group}
- Preferred Style: {user_profile.preferred_style}
- Preferred Attitude: {user_profile.preferred_attitude}
- Previous Interactions: {interaction_summary}

{emotional_context}

Personalization Strategy:
- Formality: {strategy.get('formality', 'medium')}
- Attitude: {strategy.get('attitude', 'balanced')}
- Explanation Depth: {strategy.get('explanation_depth', 'moderate')}

Adjust the language, examples, and pacing to better resonate with this user 
while ensuring that all parts flow naturally into one immersive episode.

Important:
- Keep the response in Korean.
- Return ONLY the final integrated script text, without breakdown by segment tags like [Segment: opening].
- Preserve key information and insights.
- Do not add conversational explanations before or after the script (e.g. "Here is your script:").
"""

        try:
            response = await self.call_llm(
                system_prompt=self.get_prompt("system_prompt"), user_message=prompt
            )
            return response.strip()
        except Exception as e:
            self.logger.error(f"[ScriptPersonalizer] LLM call failed: {str(e)}")
            return full_script_text

    def _summarize_interactions(self, history: List[Dict[str, Any]]) -> str:
        """상호작용 이력 요약"""

        if not history:
            return "No previous interactions"

        # 최근 5개만 요약
        recent = history[-5:]

        topics = set()
        emotions = set()

        for interaction in recent:
            if "topic" in interaction:
                topics.add(interaction["topic"])
            if "emotion" in interaction:
                emotions.add(interaction["emotion"])

        return f"Topics: {', '.join(topics) if topics else 'various'}; Emotions: {', '.join(emotions) if emotions else 'mixed'}"

    # =========================================================================
    # STEP 4: 최종 스크립트 구성
    # =========================================================================

    def _finalize_script(
        self,
        episode_id: str,
        adjusted_script: ValidatedScript,
        strategy: Dict[str, Any],
        user_profile: UserProfile,
        adjusted_segments: List[str],
    ) -> PersonalizedScript:
        """최종 개인화 스크립트 구성"""

        # 주제 추출 (간단한 구현)
        themes = self._extract_themes(adjusted_script)

        personalization_meta = PersonalizationMeta(
            applied_style=strategy,
            adjusted_segments=adjusted_segments,
            attitude_applied=strategy.get("attitude", DEFAULT_ATTITUDE),
        )

        return PersonalizedScript(
            episode_id=episode_id,
            episode_title=adjusted_script.episode_title,
            total_duration=adjusted_script.total_duration,
            segments=adjusted_script.segments,
            key_insights=adjusted_script.key_insights,
            themes=themes,
            personalization_meta=personalization_meta,
        )

    def _extract_themes(self, script: ValidatedScript) -> List[str]:
        """스크립트에서 주제 추출"""

        themes = []

        # 기존 themes 사용
        if script.themes:
            themes.extend(script.themes[:3])

        # 제목에서 추출
        if script.episode_title and len(themes) < 3:
            themes.append(script.episode_title)

        # key_insights에서 추출
        if script.key_insights and len(themes) < 3:
            themes.extend(script.key_insights[:2])

        return themes[:3]  # 최대 3개

    # =========================================================================
    # STEP 5: Learning Event 생성
    # =========================================================================

    def _create_learning_event(
        self, user_id: str, episode_id: str, strategy: Dict[str, Any]
    ) -> LearningEvent:
        """Learning Agent로 보낼 학습 이벤트 생성"""

        return LearningEvent(
            event_type="podcast_episode_personalization",
            user_id=user_id,
            episode_id=episode_id,
            personalization_effectiveness=0.0,  # 나중에 피드백으로 업데이트
            applied_settings={
                "formality": strategy.get("formality"),
                "attitude": strategy.get("attitude"),
                "emoji_usage": strategy.get("emoji_usage"),
                "explanation_depth": strategy.get("explanation_depth"),
            },
        )

    # =========================================================================
    # 폴백 처리
    # =========================================================================

    def _create_fallback_script(
        self, validated_script: ValidatedScript, user_id: str
    ) -> PersonalizedScript:
        """에러 시 폴백 스크립트 생성 (원본 그대로)"""

        return PersonalizedScript(
            episode_id=f"ep_fallback_{uuid.uuid4().hex[:8]}",
            episode_title=validated_script.episode_title,
            total_duration=validated_script.total_duration,
            segments=validated_script.segments,
            key_insights=validated_script.key_insights,
            themes=validated_script.themes if validated_script.themes else [],
            personalization_meta=PersonalizationMeta(
                applied_style={"fallback": True}, adjusted_segments=[], attitude_applied="balanced"
            ),
        )


# =============================================================================
# LangGraph 노드 함수 (외부에서 사용)
# =============================================================================


async def create_script_personalizer_node(
    db_client: Optional[Any] = None, enable_deep_personalization: bool = False
):
    """
    LangGraph에서 사용할 노드 함수 생성
    """
    agent = ScriptPersonalizerAgent(
        db_client=db_client, enable_deep_personalization=enable_deep_personalization
    )

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

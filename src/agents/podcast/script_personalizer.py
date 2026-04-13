# agents/podcast/script_personalizer.py
"""
Script Personalizer Agent
검증된 스크립트에 사용자 맞춤 스타일을 적용합니다.

TIER 4 에이전트: 팟캐스트 모드의 마지막 처리 단계
- 배치 전체 스타일 조정
- Learning Agent로 학습 이벤트 전송
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from config.app_config import (
    AGE_GROUP_STYLE_DEFAULTS,
    ATTITUDE_SETTINGS,
    DEFAULT_ATTITUDE,
    FORMALITY_REPLACEMENTS,
    STYLE_MAPPINGS,
)
from src.api.client import BackendClient
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.models.schemas import (
    EmotionalJourney,
    LearningEvent,
    PersonalizationMeta,
    PersonalizedScript,
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
        backend_client: BackendClient | None = None,
        enable_deep_personalization: bool | None = None,
    ):
        """
        Args:
            backend_client: 백엔드 API 클라이언트 (사용자 프로필 조회용)
            enable_deep_personalization: 심화 개인화 활성화 여부.
                None이면 settings.yaml의
                agents.script_personalizer.deep_personalization
                값을 사용한다.
        """
        super().__init__(name="script_personalizer", tier=4)

        if enable_deep_personalization is None:
            from config.loader import get_settings

            agent_cfg = get_settings().get_agent_config("script_personalizer")
            enable_deep_personalization = agent_cfg.get("deep_personalization", False)
        self.enable_deep_personalization = enable_deep_personalization

        self.backend_client = backend_client

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
            validated_script: ValidatedScript | None = None
            if script_data:
                try:
                    # v3.1 평탄화된 스키마 (script_text) 우선 시도
                    if "script_text" in script_data:
                        validated_script = ValidatedScript(**script_data)
                    else:
                        # 레거시 segments가 있는 경우 평탄화
                        raw_segments = script_data.get("segments", [])
                        full_text = "\n\n".join(
                            [s.get("script_text", "") for s in raw_segments if isinstance(s, dict)]
                        )
                        validated_script = ValidatedScript(
                            episode_title=script_data.get("episode_title", "마음 이야기"),
                            total_duration=script_data.get("total_duration", 5),
                            script_text=full_text,
                            tts_markers=[],
                            key_insights=script_data.get("key_insights", []),
                            themes=script_data.get("themes", []),
                        )
                except Exception as pydantic_err:
                    self.logger.warning("[ScriptPersonalizer] Pydantic 실패: %s", pydantic_err)

            # AgentState에서 감정적 여정 정보 추출
            # SP-1: AgentState 미정의 키 폴백 제거 (최상위 emotional_journey 참조 없음)
            content_analysis = state.get("content_analysis", {})
            emotional_journey_data = content_analysis.get("emotional_journey")

            emotional_journey = None
            if emotional_journey_data and isinstance(emotional_journey_data, dict):
                try:
                    emotional_journey = EmotionalJourney(
                        opening=emotional_journey_data.get("opening", "차분함"),
                        development=emotional_journey_data.get("development", "공감"),
                        climax=emotional_journey_data.get("climax", ""),  # v2.2.0: 핵심 전환점
                        closing=emotional_journey_data.get(
                            "closing", "따뜻함"
                        ),  # v2.2.0: resolution 대체
                        # SP-2: start_emotion/resolution_emotion/resolution 레거시 폴백 전부 제거
                        journey_type=emotional_journey_data.get("journey_type", "healing"),
                    )
                except Exception as e:
                    self.logger.warning("[ScriptPersonalizer] EmotionalJourney 생성 실패: %s", e)

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

            self.logger.info("[ScriptPersonalizer] Strategy: %s", personalization_strategy)

            # STEP 2: 규칙 기반 스타일 조정
            adjusted_script, was_adjusted = self._apply_rule_based_adjustments(
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
                was_adjusted=was_adjusted,
            )

            # 처리 시간 로깅
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.info("[ScriptPersonalizer] Completed in %.2fms", processing_time)

            # 메모리 저장용 에피소드 텍스트 추출
            memory_text = personalized_script.script_text or ""

            return {
                "final_output": personalized_script.model_dump_json(),
                "memory_write": True,
                "memory_text": memory_text,
                "memory_metadata": {
                    "user_id": state.get("user_id", ""),
                    "session_id": state.get("session_id", ""),
                    "episode_id": personalized_script.episode_id,
                    "episode_title": personalized_script.episode_title,
                },
            }

        except Exception as e:
            self.logger.error("[ScriptPersonalizer] Error: %s", e)

            # 에러 시 원본 스크립트 그대로 반환
            fallback = ""
            fallback_memory_text = ""
            fallback_metadata: dict[str, Any] = {
                "user_id": state.get("user_id", ""),
                "session_id": state.get("session_id", ""),
            }
            if "validated_script" in locals() and validated_script:
                fallback_script = self._create_fallback_script(
                    validated_script=validated_script, user_id=user_id
                )
                fallback = fallback_script.model_dump_json()
                try:
                    fallback_memory_text = validated_script.script_text or ""
                    fallback_metadata["episode_id"] = fallback_script.episode_id
                    fallback_metadata["episode_title"] = fallback_script.episode_title
                except Exception:
                    fallback_memory_text = ""

            return {
                "final_output": fallback,
                "memory_write": False,
                "memory_text": fallback_memory_text,
                "memory_metadata": fallback_metadata,
            }

    # =========================================================================
    # STEP 1: 사용자 프로필 조회 및 스타일 전략 결정
    # =========================================================================

    def _get_user_profile(self, user_id: str) -> UserProfile:
        """
        사용자 프로필 조회 (Backend API 연동)
        """

        if self.backend_client:
            try:
                profile = self.backend_client.get_user_profile(user_id)
                if profile:
                    return profile
            except Exception as e:
                self.logger.warning(
                    "[ScriptPersonalizer] Failed to fetch user profile via API: %s", e
                )

        # 기본 프로필 반환
        self.logger.info("[ScriptPersonalizer] Using default profile for user=%s", user_id)
        return UserProfile(
            user_id=user_id,
            age_group="30s",
            preferred_style="neutral",
            interaction_history=[],
            preferred_attitude=DEFAULT_ATTITUDE,
        )

    def _query_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """(Deprecated) Backend API 사용으로 전환됨."""
        return None

    def _determine_strategy(self, user_profile: UserProfile) -> dict[str, Any]:
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
        if len(user_profile.interaction_history) >= 3:
            # 더 자세한 설명 제공
            strategy["explanation_depth"] = "detailed"

        return strategy

    # =========================================================================
    # STEP 2: 규칙 기반 스타일 조정
    # =========================================================================

    def _apply_rule_based_adjustments(
        self, script: ValidatedScript, strategy: dict[str, Any], user_profile: UserProfile
    ) -> tuple:
        """
        규칙 기반 스타일 조정 적용 (평탄화된 텍스트 처리)

        Returns:
            tuple: (조정된 스크립트, 변경 여부 bool)
        """

        formality = strategy.get("formality", "medium")
        replacements = FORMALITY_REPLACEMENTS.get(formality, {})
        attitude = strategy.get("attitude", DEFAULT_ATTITUDE)

        script_text = script.script_text
        original_text = script_text

        # 2-1: 호칭/격식 조정 (단어 치환)
        for old_word, new_word in replacements.items():
            script_text = script_text.replace(old_word, new_word)

        # 2-2: 태도 기반 조정
        script_text = self._apply_attitude_adjustment(script_text, attitude)

        # 2-3: 이모지 처리
        if not strategy.get("emoji_usage", False):
            script_text = self._remove_emojis(script_text)

        # 조정된 스크립트 생성
        adjusted_script = ValidatedScript(
            episode_title=script.episode_title,
            total_duration=script.total_duration,
            script_text=script_text,
            tts_markers=script.tts_markers.copy(),
            key_insights=script.key_insights,
            themes=script.themes,
        )

        return adjusted_script, (script_text != original_text)

    def _apply_attitude_adjustment(self, text: str, attitude: str) -> str:
        """태도 기반 텍스트 조정"""

        if attitude not in ATTITUDE_SETTINGS:
            return text

        _settings = ATTITUDE_SETTINGS[attitude]  # noqa: F841 — 향후 규칙 확장 시 사용

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

    # =========================================================================
    # STEP 3: 심화 개인화 (LLM 사용, 선택적)
    # =========================================================================

    def _should_deep_personalize(self, user_profile: UserProfile) -> bool:
        """심화 개인화 적용 여부 결정"""

        # 상호작용 이력이 3회 이상인 경우 LLM 호출
        # TODO: 추후 개인화 맥락 수신 API(/api/sessions/{session_id}/personalization-context)에서
        #       받은 데이터를 state 또는 캐시에서 읽어 개인화에 활용 예정
        return len(user_profile.interaction_history) >= 3

    async def _apply_deep_personalization(
        self,
        script: ValidatedScript,
        user_profile: UserProfile,
        strategy: dict[str, Any],
        emotional_journey: EmotionalJourney | None,
    ) -> ValidatedScript:
        """LLM을 사용한 심화 개인화 (평탄화된 텍스트 처리)"""

        if not self.llm_client:
            return script

        self.logger.info("[ScriptPersonalizer] Applying deep personalization with LLM")

        try:
            personalized_text = await self._personalize_integrated_script_with_llm(
                full_script_text=script.script_text,
                user_profile=user_profile,
                strategy=strategy,
                emotional_journey=emotional_journey,
            )

            return ValidatedScript(
                episode_title=script.episode_title,
                total_duration=script.total_duration,
                script_text=personalized_text,
                tts_markers=script.tts_markers.copy(),
                key_insights=script.key_insights,
                themes=script.themes,
            )

        except Exception as e:
            self.logger.warning(f"[ScriptPersonalizer] LLM personalization failed: {str(e)}")
            return script

    async def _personalize_integrated_script_with_llm(
        self,
        full_script_text: str,
        user_profile: UserProfile,
        strategy: dict[str, Any],
        emotional_journey: EmotionalJourney | None,
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
- Climax: {emotional_journey.climax}
- Closing: {emotional_journey.closing}
- Type: {emotional_journey.journey_type}
"""

        user_prompt = self._prompt_loader.load_user_prompt("podcast", "script_personalizer")
        prompt = user_prompt.format(
            full_script_text=full_script_text,
            age_group=user_profile.age_group,
            preferred_style=user_profile.preferred_style,
            preferred_attitude=user_profile.preferred_attitude,
            interaction_summary=interaction_summary,
            emotional_context=emotional_context,
            formality=strategy.get("formality", "medium"),
            attitude=strategy.get("attitude", "balanced"),
            explanation_depth=strategy.get("explanation_depth", "moderate"),
        )

        try:
            response = await self.call_llm(
                system_prompt=self.get_prompt("system_prompt"), user_message=prompt
            )
            return response.strip()
        except Exception as e:
            self.logger.error("[ScriptPersonalizer] LLM call failed: %s", e)
            return full_script_text

    def _summarize_interactions(self, history: list[dict[str, Any]]) -> str:
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

        topics_str = ", ".join(topics) if topics else "various"
        emotions_str = ", ".join(emotions) if emotions else "mixed"
        return f"Topics: {topics_str}; " f"Emotions: {emotions_str}"

    # =========================================================================
    # STEP 4: 최종 스크립트 구성
    # =========================================================================

    def _finalize_script(
        self,
        episode_id: str,
        adjusted_script: ValidatedScript,
        strategy: dict[str, Any],
        user_profile: UserProfile,
        was_adjusted: bool,
    ) -> PersonalizedScript:
        """최종 개인화 스크립트 구성"""

        # 주제 추출 (간단한 구현)
        themes = self._extract_themes(adjusted_script)

        personalization_meta = PersonalizationMeta(
            applied_style=strategy,
            adjusted_segments=["full_episode"] if was_adjusted else [],
            attitude_applied=strategy.get("attitude", DEFAULT_ATTITUDE),
        )

        return PersonalizedScript(
            episode_id=episode_id,
            episode_title=adjusted_script.episode_title,
            total_duration=adjusted_script.total_duration,
            script_text=adjusted_script.script_text,
            tts_markers=adjusted_script.tts_markers,
            key_insights=adjusted_script.key_insights,
            themes=themes,
            personalization_meta=personalization_meta,
        )

    def _extract_themes(self, script: ValidatedScript) -> list[str]:
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
        self, user_id: str, episode_id: str, strategy: dict[str, Any]
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
            script_text=validated_script.script_text,
            tts_markers=validated_script.tts_markers,
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
    backend_client: BackendClient | None = None, enable_deep_personalization: bool | None = None
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    """
    LangGraph에서 사용할 노드 함수 생성
    """
    agent = ScriptPersonalizerAgent(
        backend_client=backend_client, enable_deep_personalization=enable_deep_personalization
    )

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

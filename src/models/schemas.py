"""
공통 데이터 구조 정의 (Pydantic 모델).

에이전트 간 데이터 전달에 사용되는 스키마를 정의한다.
Intent Classifier, Script Personalizer 등 에이전트 전용 모델을 포함한다.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Intent Classifier 관련 스키마
# =============================================================================


class DetectedEntities(BaseModel):
    """감지된 엔티티"""

    emotions: list[str] = Field(default_factory=list, description="감지된 감정들")
    topics: list[str] = Field(default_factory=list, description="감지된 주제들")
    persons: list[str] = Field(default_factory=list, description="언급된 인물들")


class IntentFlags(BaseModel):
    """Intent 관련 플래그"""

    requires_memory: bool = Field(default=False, description="Memory Agent 호출 필요 여부")
    requires_knowledge: bool = Field(default=False, description="Knowledge Agent 호출 필요 여부")
    visualization_hint: bool = Field(default=False, description="시각화 힌트 여부")
    urgency_level: int = Field(default=0, ge=0, le=3, description="긴급도 (0-3)")
    risk_flag: bool = Field(default=False, description="위기 감지 플래그")


class IntentClassifierOutput(BaseModel):
    """Intent Classifier 출력"""

    intent_type: str = Field(..., description="분류된 의도 타입")
    complexity_score: float = Field(..., ge=0.0, le=1.0, description="복잡도 점수")
    detected_entities: DetectedEntities = Field(default_factory=DetectedEntities)
    flags: IntentFlags = Field(default_factory=IntentFlags)
    reasoning: Optional[str] = Field(default=None, description="분류 근거 설명")
    trace_id: str = Field(..., description="추적 ID")
    classified_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Script Personalizer 관련 스키마 (팟캐스트 모드)
# =============================================================================


class EmotionalJourney(BaseModel):
    """감정적 여정 구조 (Content Analyzer에서 생성).

    Content Analyzer 실제 출력 키:
        { "opening": "도입 감정", "development": "전개 감정", "resolution": "해소 감정" }

    Note:
        - Podcast Reasoning은 emotional_journey를 list[str]로 출력하므로
          이 모델은 Content Analyzer의 dict 출력에만 해당한다.
        - Script Generator는 opening/start_emotion 양쪽 키를 fallback으로 처리.
    """

    opening: str = Field(..., description="도입 감정")
    development: str = Field(..., description="전개 감정")
    resolution: str = Field(..., description="해소 감정")
    journey_type: str = Field(default="healing", description="여정 유형")


class UserProfile(BaseModel):
    """사용자 프로필"""

    user_id: str = Field(..., description="사용자 ID")
    age_group: str = Field(default="30s", description="연령대")
    preferred_style: str = Field(default="neutral", description="선호 스타일")
    interaction_history: list[dict[str, Any]] = Field(
        default_factory=list, description="상호작용 이력"
    )
    preferred_attitude: str = Field(default="balanced", description="선호 태도")


class TTSMarker(BaseModel):
    """TTS 마커"""

    position: int = Field(..., description="위치")
    instruction: str = Field(..., description="TTS 지시사항")


class ScriptSegment(BaseModel):
    """스크립트 세그먼트"""

    segment_id: str = Field(..., description="세그먼트 ID")
    segment_type: str = Field(
        ..., description="세그먼트 타입 (opening, education, practical, closing 등)"
    )
    duration_minutes: int = Field(..., description="예상 길이(분)")
    script_text: str = Field(..., description="스크립트 텍스트")
    word_count: int = Field(default=0, description="단어 수")
    emotional_tone: str = Field(default="neutral", description="감정 톤")
    tts_markers: list[TTSMarker] = Field(default_factory=list, description="TTS 마커 목록")


class ValidatedScript(BaseModel):
    """검증된 스크립트 (Batch Validator에서 전달)"""

    episode_title: str = Field(..., description="에피소드 제목")
    total_duration: int = Field(..., description="총 시간(분)")
    script_text: str = Field(..., description="전체 스크립트 텍스트")
    tts_markers: list[TTSMarker] = Field(default_factory=list, description="TTS 마커 목록")
    key_insights: list[str] = Field(default_factory=list, description="핵심 인사이트")
    themes: list[str] = Field(default_factory=list, description="주제 리스트")


class PersonalizationMeta(BaseModel):
    """개인화 메타데이터"""

    applied_style: dict[str, Any] = Field(default_factory=dict, description="적용된 스타일")
    adjusted_segments: list[str] = Field(
        default_factory=list, description="조정된 세그먼트 ID 목록"
    )
    attitude_applied: str = Field(default="balanced", description="적용된 태도")


class PersonalizedScript(BaseModel):
    """개인화된 스크립트 (Script Personalizer 출력)"""

    episode_id: str = Field(..., description="에피소드 ID")
    episode_title: str = Field(..., description="개인화된 제목")
    total_duration: int = Field(..., description="총 시간")
    script_text: str = Field(..., description="개인화된 전체 스크립트 텍스트")
    tts_markers: list[TTSMarker] = Field(default_factory=list, description="개인화된 TTS 마커 목록")
    key_insights: list[str] = Field(default_factory=list, description="핵심 인사이트")
    themes: list[str] = Field(default_factory=list, description="주제 리스트")
    personalization_meta: PersonalizationMeta = Field(default_factory=PersonalizationMeta)


class LearningEvent(BaseModel):
    """Learning Agent로 보내는 학습 이벤트"""

    event_type: str = Field(default="podcast_episode_learning", description="이벤트 타입")
    user_id: str = Field(..., description="사용자 ID")
    episode_id: str = Field(..., description="에피소드 ID")
    personalization_effectiveness: float = Field(default=0.0, description="개인화 효과성")
    applied_settings: dict[str, Any] = Field(default_factory=dict, description="적용된 설정")

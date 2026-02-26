# agents/common/__init__.py
"""
공통 모듈: 스키마, 설정, 프로토콜
모든 에이전트에서 공유하는 요소들
"""

# 스키마 (데이터 구조)
from src.agents.common.schemas import (
    # Intent Classifier 관련
    IntentClassifierInput,
    IntentClassifierOutput,
    DetectedEntities,
    IntentFlags,
    
    # Script Personalizer 관련
    UserProfile,
    ValidatedScript,
    PersonalizedScript,
    ScriptSegment,
    EmotionalJourney,
    PersonalizationMeta,
    LearningEvent,
    
    # LangGraph State
    ConversationState,
    PodcastState,
    
    # Enum
    IntentType,
    AttitudeType,
)

# 설정값
from src.agents.common.config import (
    INTENT_TYPES,
    CRISIS_KEYWORDS,
    PODCAST_KEYWORDS,
    DEFAULT_INTENT,
    FORMALITY_REPLACEMENTS,
    AGE_GROUP_STYLE_DEFAULTS,
    STYLE_MAPPINGS,
    ATTITUDE_SETTINGS,
)

# 프로토콜
from src.agents.common.protocols import (
    AgentMessage,
    MessageMetadata,
    create_message,
)

__all__ = [
    # 스키마
    "IntentClassifierInput",
    "IntentClassifierOutput",
    "DetectedEntities",
    "IntentFlags",
    "UserProfile",
    "ValidatedScript",
    "PersonalizedScript",
    "ScriptSegment",
    "EmotionalJourney",
    "PersonalizationMeta",
    "LearningEvent",
    "ConversationState",
    "PodcastState",
    "IntentType",
    "AttitudeType",
    
    # 설정
    "INTENT_TYPES",
    "CRISIS_KEYWORDS",
    "PODCAST_KEYWORDS",
    "DEFAULT_INTENT",
    "FORMALITY_REPLACEMENTS",
    "AGE_GROUP_STYLE_DEFAULTS",
    "STYLE_MAPPINGS",
    "ATTITUDE_SETTINGS",
    
    # 프로토콜
    "AgentMessage",
    "MessageMetadata",
    "create_message",
]
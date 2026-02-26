# agents/common/config.py
"""
수정 가능한 설정값들을 모아둔 파일
팀원들이 쉽게 수정할 수 있도록 한 곳에 모았습니다.
"""

# =============================================================================
# Intent Classifier 설정
# =============================================================================

# Intent 타입 목록 (필요시 추가/삭제 가능)
INTENT_TYPES = [
    "casual_chat",  # 일상대화
    "emotional_support",  # 감정 표현/지지 요청
    "counseling",  # 고민상담
    "crisis",  # 위기상황 (자해/자살 언급 등)
    "information",  # 정보 요청
    "podcast_request",  # 팟캐스트 생성 요청
]

# 위기 감지 키워드 (1차 필터링용, 필요시 추가/삭제 가능)
# 주의: 이 키워드가 감지되면 무조건 crisis로 분류하여 안전 우선
CRISIS_KEYWORDS = [
    "죽고싶",
    "죽고 싶",
    "자살",
    "자해",
    "끝내고 싶",
    "끝내고싶",
    "살고싶지않",
    "살고 싶지 않",
    "죽어버리고",
    "목숨",
    "극단적",
]

# 팟캐스트 요청 감지 키워드
PODCAST_KEYWORDS = [
    "팟캐스트",
    "에피소드",
    "방송",
    "라디오",
    "만들어줘",
    "제작",
]

# 기본 Intent (분류 실패 시 사용)
DEFAULT_INTENT = "casual_chat"

# 기본 복잡도 점수
DEFAULT_COMPLEXITY_SCORE = 0.5

# =============================================================================
# Script Personalizer 설정
# =============================================================================

# 격식체 수준별 단어 치환 규칙
FORMALITY_REPLACEMENTS = {
    "high": {
        "여러분": "여러분",
        "우리": "우리 모두",
        "해요": "합니다",
        "거예요": "것입니다",
        "같아요": "같습니다",
    },
    "medium": {
        # 변경 없음 (기본 스타일)
    },
    "low": {
        "합니다": "해요",
        "입니다": "이에요",
        "여러분": "다들",
        "것입니다": "거예요",
    },
}

# 연령대별 기본 스타일 매핑
AGE_GROUP_STYLE_DEFAULTS = {
    "10s": {"formality": "low", "emoji_usage": True, "sentence_length": "short"},
    "20s": {"formality": "low", "emoji_usage": True, "sentence_length": "medium"},
    "30s": {"formality": "medium", "emoji_usage": False, "sentence_length": "medium"},
    "40s": {"formality": "medium", "emoji_usage": False, "sentence_length": "medium"},
    "50s": {"formality": "high", "emoji_usage": False, "sentence_length": "long"},
    "60s+": {"formality": "high", "emoji_usage": False, "sentence_length": "long"},
}

# preferred_style 매핑
STYLE_MAPPINGS = {
    "formal": {"formality": "high", "emoji_usage": False},
    "casual": {"formality": "low", "emoji_usage": True},
    "neutral": {"formality": "medium", "emoji_usage": False},
}

# 태도 설정 (Q4에서 추가 요청)
ATTITUDE_SETTINGS = {
    "empathetic": {
        "description": "공감을 우선적으로",
        "tone_keywords": ["힘드셨겠어요", "그런 마음이 드셨군요", "충분히 이해해요"],
        "avoid_keywords": ["해결책은", "방법은", "~해야 합니다"],
    },
    "rational": {
        "description": "이성적인 해결을 우선적으로",
        "tone_keywords": ["해결 방법", "구체적으로", "단계별로"],
        "avoid_keywords": [],
    },
    "balanced": {
        "description": "공감과 해결의 균형",
        "tone_keywords": [],
        "avoid_keywords": [],
    },
}

# 기본 태도
DEFAULT_ATTITUDE = "balanced"

# 문장 길이 설정 (대략적인 가이드)
SENTENCE_LENGTH_GUIDE = {
    "short": {"max_chars_per_sentence": 30, "description": "간결하게"},
    "medium": {"max_chars_per_sentence": 50, "description": "보통"},
    "long": {"max_chars_per_sentence": 80, "description": "자세하게"},
}

# 설명 깊이 설정
EXPLANATION_DEPTH = {
    "simple": {"description": "핵심만 간단히"},
    "moderate": {"description": "적당한 설명 포함"},
    "detailed": {"description": "배경과 예시 포함"},
}

# =============================================================================
# Redis 설정 (나중에 사용)
# =============================================================================

REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "intent_cache_ttl": 3600,  # 1시간
}

# =============================================================================
# 기본값 모음 (에러 시 사용)
# =============================================================================

FALLBACK_VALUES = {
    "intent_type": DEFAULT_INTENT,
    "complexity_score": DEFAULT_COMPLEXITY_SCORE,
    "detected_entities": {
        "emotions": [],
        "topics": [],
        "persons": [],
    },
    "flags": {
        "requires_memory": False,
        "requires_knowledge": False,
        "visualization_hint": False,
        "urgency_level": 0,
    },
}

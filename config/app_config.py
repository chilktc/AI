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

# =============================================================================
# Podcast Host Persona 설정 (8종)
# =============================================================================

# 백엔드/프론트엔드 라벨(title)과 시스템 파라미터 매핑
PERSONA_STRATEGY_MAP = {
    "따뜻한 공감자": {
        "description": "부드러운 목소리로 마음을 안아주며 위로를 전하는 스타일",
        "keywords": ["#위로", "#따뜻함", "#공감"],
        "formality": "medium",
        "attitude": "empathetic",
    },
    "이성적인 분석가": {
        "description": "복잡한 상황을 논리적으로 분석해 명확한 해법을 제시하는 스타일",
        "keywords": ["#논리", "#해결책", "#정리"],
        "formality": "high",
        "attitude": "rational",
    },
    "열정적인 코치": {
        "description": "에너지가 넘치고 동기부여를 주며 강력하게 응원하는 스타일",
        "keywords": ["#응원", "#변화", "#열정"],
        "formality": "low",
        "attitude": "energetic",
    },
    "고요한 새벽지기": {
        "description": "명상하듯 차분하고 깊이 있는 통찰을 나누는 스타일",
        "keywords": ["#통찰", "#차분함", "#깊이"],
        "formality": "medium",
        "attitude": "calm",
    },
    "유쾌한 팩트폭격기": {
        "description": "재치 있는 농담과 함께 현실적인 조언을 건네는 스타일",
        "keywords": ["#재치", "#솔직함", "#유머"],
        "formality": "low",
        "attitude": "witty",
    },
    "몰입형 이야기꾼": {
        "description": "은유와 비유를 활용해 영화 같은 서사를 들려주는 스타일",
        "keywords": ["#기승전결", "#몰입", "#비유"],
        "formality": "medium",
        "attitude": "narrative",
    },
    "신뢰의 전문가": {
        "description": "격식과 권위 있는 말투로 신뢰감 있는 조언을 하는 스타일",
        "keywords": ["#전문성", "#신뢰", "#가이드"],
        "formality": "high",
        "attitude": "professional",
    },
    "편안한 동네 친구": {
        "description": "친한 선후배나 친구처럼 다정하고 소탈하게 이야기하는 스타일",
        "keywords": ["#친근함", "#소탈함", "#편안함"],
        "formality": "low",
        "attitude": "casual",
    },
}

# =============================================================================
# Redis 설정 (Intent Classifier 캐시)
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

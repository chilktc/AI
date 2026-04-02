"""중앙화된 Mock 데이터.

tests/graph/test_e2e_mock_pipeline.py와 tests/integration/conftest.py에서
중복 정의되던 모의 에이전트 결과를 한 곳에서 관리한다.

명명 규칙:
    MOCK_{에이전트}_{변형}   예) MOCK_SAFETY_SAFE, MOCK_SAFETY_CRISIS
"""

from __future__ import annotations

from typing import Any

# ====================================================================
# TIER 0: Intent Classifier (개발자1)
# ====================================================================

MOCK_INTENT_PODCAST: dict[str, Any] = {
    "intent": {
        "mode": "podcast",
        "category": "stress_management",
        "complexity_score": 0.65,
        "topic_hint": "직장 스트레스와 뒷담화",
        "risk_flag": False,
    },
    "mode": "podcast",
    "risk_level": 0,
    "risk_score": 0.1,
}

MOCK_INTENT_CRISIS: dict[str, Any] = {
    "intent": {
        "mode": "podcast",
        "category": "crisis",
        "complexity_score": 0.9,
        "topic_hint": "위기 상황",
        "risk_flag": True,
    },
    "mode": "podcast",
    "risk_level": 3,
    "risk_score": 0.85,
}

# ====================================================================
# TIER 1: Safety Agent (개발자2)
# ====================================================================

MOCK_SAFETY_SAFE: dict[str, Any] = {
    "safety_flags": {
        "status": "safe",
        "reasons": [],
        "forbidden_topics": [],
        "required_in_script": [],
        "tone_guidelines": "supportive",
    },
}

MOCK_SAFETY_CRISIS: dict[str, Any] = {
    "safety_flags": {
        "status": "crisis",
        "reasons": ["suicide_risk"],
        "forbidden_topics": ["self_harm_methods"],
        "required_in_script": ["crisis_hotline"],
        "tone_guidelines": "urgent_supportive",
    },
    "risk_level": 4,
    "risk_score": 0.95,
    "crisis_response": (
        "지금 많이 힘드시군요. 전문 상담사와 바로 연결해 드리겠습니다. "
        "자살예방상담전화 1393으로 연락해 주세요."
    ),
}

# ====================================================================
# TIER 1: Emotion Agent (개발자2)
# ====================================================================

MOCK_EMOTION: dict[str, Any] = {
    "emotion_vectors": {
        "primary_emotion": "frustration",
        "intensity": 0.7,
        "valence": -0.4,
        "arousal": 0.6,
        "secondary_emotions": ["disappointment", "anxiety"],
        "tone_recommendation": "empathetic_supportive",
        "emotional_journey_hint": "공감 → 이해 → 전환 → 희망",
    },
}

# ====================================================================
# TIER 1: Content Analyzer (개발자3) — 팟캐스트모드
# ====================================================================

MOCK_CONTENT_ANALYSIS: dict[str, Any] = {
    "content_analysis": {
        "main_theme": "직장 내 뒷담화와 인간관계 갈등",
        "sub_themes": ["신뢰 훼손", "감정 관리", "갈등 해결 전략"],
        "target_duration": 4,
        "narrative_structure": "problem_solution",
        "depth_level": "moderate",
        "episode_type": "상담",
        "target_audience": "직장인",
        "keywords": ["뒷담화", "인간관계", "갈등", "직장"],
        "complexity_score": 0.65,
    },
}

# ====================================================================
# TIER 1: Reasoning (개발자3)
# ====================================================================

MOCK_REASONING_PODCAST: dict[str, Any] = {
    "reasoning_result": {
        "episode_structure": [
            {
                "segment": "intro",
                "duration_seconds": 30,
                "description": "직장 내 인간관계의 어려움 공감",
            },
            {
                "segment": "body_1",
                "duration_seconds": 90,
                "description": "뒷담화의 심리적 원인 분석",
            },
            {
                "segment": "body_2",
                "duration_seconds": 90,
                "description": "건강한 대처 전략과 소통법",
            },
            {
                "segment": "outro",
                "duration_seconds": 30,
                "description": "실천 가능한 행동 제안",
            },
        ],
        "narrative_flow": "공감 → 분석 → 전략 → 실천",
        "key_points": ["감정 인정하기", "직접 대화 시도", "경계 설정"],
        "emotional_journey": [
            {"phase": "opening", "emotion": "공감"},
            {"phase": "exploration", "emotion": "이해"},
            {"phase": "resolution", "emotion": "희망"},
        ],
        "confidence": 0.85,
        "reasoning_strategy": "ToT",
    },
}

# ====================================================================
# TIER 2: Script Generator (개발자1)
# ====================================================================

MOCK_SCRIPT_DRAFT: dict[str, Any] = {
    "script_draft": {
        "episode_title": "직장 뒷담화, 상처받은 마음 다스리기",
        "total_duration": 240,
        "segments": [
            {
                "type": "intro",
                "content": (
                    "안녕하세요, Mind-Log 팟캐스트입니다. "
                    "오늘은 직장에서 겪는 뒷담화와 인간관계 갈등에 대해 이야기합니다."
                ),
                "duration": 30,
                "speaker": "host",
            },
            {
                "type": "body",
                "content": (
                    "직장에서 친하게 지내던 동료의 뒷담화를 듣게 되면 "
                    "큰 충격과 실망감을 느끼게 됩니다. "
                    "이런 상황에서 가장 중요한 것은 "
                    "자신의 감정을 먼저 인정하는 것입니다."
                ),
                "duration": 180,
                "speaker": "host",
            },
            {
                "type": "outro",
                "content": (
                    "오늘 이야기가 도움이 되셨기를 바랍니다. "
                    "작은 변화가 큰 차이를 만들 수 있습니다."
                ),
                "duration": 30,
                "speaker": "host",
            },
        ],
        "key_insights": ["감정 인정의 중요성", "I-message 소통법", "건강한 경계 설정"],
        "themes": {"main": "인간관계 갈등", "sub": ["뒷담화", "감정 관리"]},
        "metadata": {"model": "mock", "generated_at": "2026-02-27T10:00:00Z"},
    },
}

# ====================================================================
# TIER 3: Batch Validator (개발자3)
# ====================================================================

MOCK_BV_PASS: dict[str, Any] = {
    "validation_result": {
        "verdict": "PASS",
        "overall_score": 0.88,
        "checks": {
            "structure_completeness": {"passed": True, "score": 0.9},
            "safety_compliance": {"passed": True, "score": 1.0},
            "tone_consistency": {"passed": True, "score": 0.85},
            "timing_appropriateness": {"passed": True, "score": 0.9},
            "harmful_content_check": {"passed": True, "score": 1.0},
        },
        "feedback": "스크립트 품질 양호",
        "critical_issues": [],
    },
}

MOCK_BV_FAIL: dict[str, Any] = {
    "validation_result": {
        "verdict": "FAIL",
        "overall_score": 0.55,
        "checks": {
            "structure_completeness": {"passed": True, "score": 0.7},
            "safety_compliance": {"passed": True, "score": 1.0},
            "tone_consistency": {"passed": False, "score": 0.4},
            "timing_appropriateness": {"passed": True, "score": 0.6},
            "harmful_content_check": {"passed": True, "score": 1.0},
        },
        "feedback": "톤 일관성 부족 — 공감적 표현 강화 필요",
        "critical_issues": [],
    },
}

# ====================================================================
# TIER 3: Validator (개발자3) — 대화모드
# ====================================================================

MOCK_VALIDATOR_PASS: dict[str, Any] = {
    "validation_result": {
        "validation": {
            "approved": True,
            "safety_check": {"passed": True, "issues": []},
            "quality_check": {"score": 0.85, "issues": [], "suggestions": []},
        },
        "action": {
            "decision": "approve",
            "revision_instructions": None,
            "max_iterations_remaining": 2,
        },
    },
}

# ====================================================================
# TIER 4: Script Personalizer / Personalization (개발자1)
# ====================================================================

MOCK_FINAL_OUTPUT_PODCAST: dict[str, Any] = {
    "final_output": (
        '{"episode_title": "직장 뒷담화, 상처받은 마음 다스리기", '
        '"segments": [{"type": "intro", "content": "안녕하세요, Mind-Log입니다."}, '
        '{"type": "body", "content": "직장에서의 인간관계는 우리 삶에서 큰 비중을 차지합니다."}, '
        '{"type": "outro", "content": "오늘도 수고하셨습니다."}], '
        '"personalization_applied": true, "tone": "warm_empathetic"}'
    ),
}

# ====================================================================
# 비동기: Visualization (개발자2)
# ====================================================================

MOCK_VISUALIZATION: dict[str, Any] = {
    "visualization_result": {
        "mode": "podcast",
        "image_url": "mock://visualization/frustration_workplace.png",
        "interpretation_text": "직장 내 갈등과 좌절감을 표현한 따뜻한 톤의 시각화",
        "style_info": {"palette": "warm", "mood": "empathetic"},
    },
}

# ====================================================================
# 검증용 필드 목록
# ====================================================================

EXPECTED_PODCAST_FIELDS: list[str] = [
    "intent",
    "safety_flags",
    "emotion_vectors",
    "content_analysis",
    "reasoning_result",
    "script_draft",
    "validation_result",
    "final_output",
]

DEVELOPER_FIELDS_PODCAST: dict[str, list[str]] = {
    "개발자1": ["intent", "script_draft", "final_output"],
    "개발자2": ["safety_flags", "emotion_vectors"],
    "개발자3": ["content_analysis", "reasoning_result", "validation_result"],
}

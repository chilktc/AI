"""
통합 테스트 공용 Fixture.

대화모드/팟캐스트모드 파이프라인 통합 테스트에서 사용하는
AgentState fixture, LLM mock, 그래프 빌더를 제공한다.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.models.agent_state import AgentState


# ===================================================================
# AgentState Fixture
# ===================================================================
@pytest.fixture
def conversation_state() -> AgentState:
    """대화모드 기본 AgentState."""
    return AgentState(
        user_input="요즘 직장에서 스트레스를 많이 받아요.",
        user_id="test_user_001",
        session_id="sess_integration_001",
        mode="conversation",
    )


@pytest.fixture
def podcast_state() -> AgentState:
    """팟캐스트모드 기본 AgentState."""
    return AgentState(
        user_input="이번 주 감정 일기를 팟캐스트로 만들어 주세요.",
        user_id="test_user_001",
        session_id="sess_integration_002",
        mode="podcast",
    )


@pytest.fixture
def crisis_state() -> AgentState:
    """위기 감지 시나리오 AgentState."""
    return AgentState(
        user_input="더 이상 살고 싶지 않아요.",
        user_id="test_user_crisis",
        session_id="sess_integration_crisis",
        mode="conversation",
    )


@pytest.fixture
def podcast_crisis_state() -> AgentState:
    """팟캐스트모드 위기 감지 시나리오 AgentState."""
    return AgentState(
        user_input="자해에 대한 이야기를 팟캐스트로 만들어 주세요.",
        user_id="test_user_crisis",
        session_id="sess_integration_crisis_pod",
        mode="podcast",
    )


# ===================================================================
# 모의 에이전트 결과 Fixture
# ===================================================================
@pytest.fixture
def mock_safety_safe_result() -> dict[str, Any]:
    """Safety Agent 모의 결과 — safe."""
    return {
        "safety_flags": {"status": "safe", "categories": []},
        "risk_level": 0,
        "risk_score": 0.05,
    }


@pytest.fixture
def mock_safety_crisis_result() -> dict[str, Any]:
    """Safety Agent 모의 결과 — crisis."""
    return {
        "safety_flags": {"status": "crisis", "categories": ["suicide_risk"]},
        "risk_level": 4,
        "risk_score": 0.95,
        "crisis_response": "지금 많이 힘드시군요. 전문 상담사와 바로 연결해 드리겠습니다.",
    }


@pytest.fixture
def mock_emotion_result() -> dict[str, Any]:
    """Emotion Agent 모의 결과."""
    return {
        "emotion_vectors": {
            "primary": "stress",
            "secondary": "anxiety",
            "intensity": 0.7,
        },
    }


@pytest.fixture
def mock_context_result() -> dict[str, Any]:
    """Context Agent 모의 결과."""
    return {
        "context": {
            "current_topic": "직장 스트레스",
            "topic_continuity": "same",
            "conversation_phase": "exploration",
            "user_engagement": "medium",
        },
    }


@pytest.fixture
def mock_reasoning_result() -> dict[str, Any]:
    """Reasoning Agent 모의 결과."""
    return {
        "reasoning_result": {
            "cot_result": {
                "reasoning_steps": [
                    "Step 1: 사용자의 스트레스를 공감적으로 인정",
                    "Step 2: 상황의 어려움을 타당화",
                    "Step 3: 구체적인 대처 방법 탐색",
                ],
                "conclusion": "공감 + 탐색적 질문",
                "confidence": 0.8,
            },
            "synthesis_guidance": {
                "key_points": ["공감", "타당화"],
                "elements_to_include": ["감정 반영"],
                "elements_to_avoid": ["독성 긍정성"],
            },
        },
    }


# ===================================================================
# 팟캐스트모드 모의 결과
# ===================================================================
@pytest.fixture
def mock_content_analysis_result() -> dict[str, Any]:
    """Content Analyzer 모의 결과."""
    return {
        "content_analysis": {
            "main_theme": "감정 일기와 자기 돌봄",
            "sub_themes": ["스트레스", "일상 기록", "감정 인식"],
            "emotional_journey": {
                "opening": "공감",
                "development": "탐색",
                "resolution": "위로",
            },
            "target_duration": 5,
            "narrative_structure": "reflection",
        },
    }


@pytest.fixture
def mock_podcast_reasoning_result() -> dict[str, Any]:
    """Podcast Reasoning 모의 결과."""
    return {
        "reasoning_result": {
            "core_pattern": "감정 인식과 자기 돌봄",
            "episode_structure": [
                {"section": "도입", "duration_ratio": 0.2},
                {"section": "본론", "duration_ratio": 0.6},
                {"section": "마무리", "duration_ratio": 0.2},
            ],
        },
    }



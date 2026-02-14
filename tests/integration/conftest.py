"""
통합 테스트 공용 Fixture.

대화모드/팟캐스트모드 파이프라인 통합 테스트에서 사용하는
AgentState fixture, LLM mock, 그래프 빌더를 제공한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

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
def mock_intent_result() -> dict[str, Any]:
    """Intent Classifier 모의 결과."""
    return {
        "intent": {
            "primary_intent": "emotional_support",
            "complexity_score": 0.6,
            "risk_flag": False,
        },
        "mode": "conversation",
        "execution_plan": {"tier1_agents": ["safety", "emotion", "context", "reasoning"]},
    }


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


@pytest.fixture
def mock_synthesis_result() -> dict[str, Any]:
    """Synthesis Agent 모의 결과."""
    return {
        "response_draft": "직장에서 스트레스를 많이 받고 계시군요. "
        "그 상황이 얼마나 힘드실지 충분히 이해합니다.",
    }


@pytest.fixture
def mock_validation_pass_result() -> dict[str, Any]:
    """Validator Agent 모의 결과 — 통과."""
    return {
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
        "next_step": "personalization",
    }


@pytest.fixture
def mock_validation_fail_result() -> dict[str, Any]:
    """Validator Agent 모의 결과 — 실패 (재시도 필요)."""
    return {
        "validation_result": {
            "validation": {
                "approved": False,
                "safety_check": {"passed": True, "issues": []},
                "quality_check": {
                    "score": 0.45,
                    "issues": ["응답이 너무 짧음"],
                    "suggestions": ["구체적인 공감 표현 추가"],
                },
            },
            "action": {
                "decision": "revise",
                "revision_instructions": "응답에 구체적인 공감 표현을 추가하세요.",
                "max_iterations_remaining": 1,
            },
        },
    }


@pytest.fixture
def mock_personalization_result() -> dict[str, Any]:
    """Personalization Agent 모의 결과."""
    return {
        "final_output": "직장에서 많은 스트레스를 받고 계시는군요. "
        "그 마음이 얼마나 무거우실지 저도 느껴져요.",
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


@pytest.fixture
def mock_script_draft_result() -> dict[str, Any]:
    """Script Generator 모의 결과."""
    return {
        "script_draft": {
            "title": "나를 돌보는 시간",
            "sections": [
                {"type": "intro", "content": "안녕하세요, 오늘의 에피소드입니다."},
                {"type": "body", "content": "이번 주 여러분의 감정을 돌아볼까요."},
                {"type": "outro", "content": "오늘도 수고하셨습니다."},
            ],
        },
    }


@pytest.fixture
def mock_batch_validation_pass() -> dict[str, Any]:
    """Batch Validator 모의 결과 — 통과."""
    return {
        "validation_result": {
            "scores": {
                "content_quality": 0.85,
                "safety_compliance": 0.95,
                "emotional_alignment": 0.80,
                "structure_coherence": 0.75,
                "engagement_potential": 0.70,
            },
            "overall_score": 0.81,
            "verdict": "PASS",
            "feedback": "",
            "critical_issues": [],
        },
    }


@pytest.fixture
def mock_batch_validation_fail() -> dict[str, Any]:
    """Batch Validator 모의 결과 — 실패."""
    return {
        "validation_result": {
            "scores": {
                "content_quality": 0.60,
                "safety_compliance": 0.90,
                "emotional_alignment": 0.50,
                "structure_coherence": 0.65,
                "engagement_potential": 0.55,
            },
            "overall_score": 0.64,
            "verdict": "FAIL",
            "feedback": "감정 정렬과 참여도 개선 필요",
            "critical_issues": [],
        },
    }


# ===================================================================
# 전역 LLM Mock
# ===================================================================
@pytest.fixture
def mock_all_llm_calls():
    """
    모든 LLM 호출을 전역으로 mock하는 fixture.

    사용법:
        def test_something(mock_all_llm_calls):
            mock_all_llm_calls.return_value = {"key": "value"}
            # ... 테스트
    """
    with patch(
        "src.agents.shared.base_agent.BaseAgent.call_llm_json",
        new_callable=AsyncMock,
        return_value={},
    ) as mock_json, patch(
        "src.agents.shared.base_agent.BaseAgent.call_llm",
        new_callable=AsyncMock,
        return_value="",
    ) as mock_text:
        mock_json.text_mock = mock_text  # type: ignore[attr-defined]
        yield mock_json

"""
Mock 기반 전체 파이프라인 E2E 테스트.

test_e2e_multi_provider와 동일한 구조로 전체 LangGraph 파이프라인을 실행하되,
실제 LLM 호출 대신 mock 데이터를 사용한다.

모든 개발자의 에이전트가 참여:
    - 개발자1: IntentClassifier, ScriptGenerator, ScriptPersonalizer
    - 개발자2: Safety, Emotion, Visualization
    - 개발자3: ContentAnalyzer, PodcastReasoning, BatchValidator, Learning

검증 흐름 (팟캐스트모드):
    TIER 0: IntentClassifier → intent 분류 (mock)
    TIER 1 (병렬 Fan-out): Safety + Emotion + ContentAnalyzer + PodcastReasoning (mock)
    TIER 2: ScriptGenerator (mock)
    TIER 3: BatchValidator (mock)
    TIER 4: ScriptPersonalizer (mock)
    비동기: Visualization + Telemetry(stub) + Learning (mock)

검증 흐름 (대화모드):
    TIER 0: IntentClassifier → intent 분류 (mock)
    TIER 1 (병렬 Fan-out): Safety + Emotion + Context + Reasoning (mock)
    TIER 2: Synthesis (mock)
    TIER 3: Validator (mock)
    TIER 4: Personalization (mock)
    비동기: Visualization + Telemetry(stub) + Learning (mock)

사용법:
    pytest tests/graph/test_e2e_mock_pipeline.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

# ────────────────────────────────────────
# 검증할 상태 필드 (test_e2e_multi_provider.EXPECTED_FIELDS와 동일 구조)
# ────────────────────────────────────────

# 팟캐스트모드 — 8개 필드 (3개 개발자 전원 참여)
EXPECTED_PODCAST_FIELDS = [
    "intent",             # TIER 0: IntentClassifier (개발자1)
    "safety_flags",       # TIER 1: Safety (개발자2)
    "emotion_vectors",    # TIER 1: Emotion (개발자2)
    "content_analysis",   # TIER 1: ContentAnalyzer (개발자3)
    "reasoning_result",   # TIER 1: PodcastReasoning (개발자3)
    "script_draft",       # TIER 2: ScriptGenerator (개발자1)
    "validation_result",  # TIER 3: BatchValidator (개발자3)
    "final_output",       # TIER 4: ScriptPersonalizer (개발자1)
]

# 대화모드 — 8개 필드 (3개 개발자 전원 참여)
EXPECTED_CONVERSATION_FIELDS = [
    "intent",             # TIER 0: IntentClassifier (개발자1)
    "safety_flags",       # TIER 1: Safety (개발자2)
    "emotion_vectors",    # TIER 1: Emotion (개발자2)
    "context",            # TIER 1: Context (개발자3)
    "reasoning_result",   # TIER 1: Reasoning (개발자3)
    "response_draft",     # TIER 2: Synthesis (개발자1)
    "validation_result",  # TIER 3: Validator (개발자3)
    "final_output",       # TIER 4: Personalization (개발자1)
]

# 개발자별 필드 맵 (팟캐스트모드)
DEVELOPER_FIELDS_PODCAST = {
    "개발자1": ["intent", "script_draft", "final_output"],
    "개발자2": ["safety_flags", "emotion_vectors"],
    "개발자3": ["content_analysis", "reasoning_result", "validation_result"],
}

# 개발자별 필드 맵 (대화모드)
DEVELOPER_FIELDS_CONVERSATION = {
    "개발자1": ["intent", "response_draft", "final_output"],
    "개발자2": ["safety_flags", "emotion_vectors"],
    "개발자3": ["context", "reasoning_result", "validation_result"],
}


# ────────────────────────────────────────
# Mock 데이터 — 현실적인 한국어 콘텐츠
# ────────────────────────────────────────

# --- TIER 0: Intent Classifier (개발자1) ---
MOCK_INTENT_PODCAST = {
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

MOCK_INTENT_CONVERSATION = {
    "intent": {
        "mode": "conversation",
        "category": "emotional_support",
        "complexity_score": 0.6,
        "topic_hint": "직장 스트레스",
        "risk_flag": False,
    },
    "mode": "conversation",
    "risk_level": 0,
    "risk_score": 0.05,
}

MOCK_INTENT_CRISIS = {
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

# --- TIER 1: Safety (개발자2) ---
MOCK_SAFETY_SAFE = {
    "safety_flags": {
        "status": "safe",
        "reasons": [],
        "forbidden_topics": [],
        "required_in_script": [],
        "tone_guidelines": "supportive",
    },
}

MOCK_SAFETY_CRISIS = {
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

# --- TIER 1: Emotion (개발자2) ---
MOCK_EMOTION = {
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

# --- TIER 1: ContentAnalyzer (개발자3) ---
MOCK_CONTENT_ANALYSIS = {
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

# --- TIER 1: PodcastReasoning (개발자3) ---
MOCK_REASONING_PODCAST = {
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

# --- TIER 1: Context (개발자3) — 대화모드 ---
MOCK_CONTEXT = {
    "context": {
        "current_topic": "직장 스트레스",
        "topic_continuity": "new",
        "conversation_phase": "exploration",
        "user_engagement": "high",
        "prior_sessions_summary": "첫 세션",
    },
}

# --- TIER 1: Reasoning (개발자3) — 대화모드 ---
MOCK_REASONING_CONVERSATION = {
    "reasoning_result": {
        "reasoning_steps": [
            "사용자의 직장 스트레스를 공감적으로 인정",
            "뒷담화로 인한 감정(배신감, 실망)을 타당화",
            "구체적인 대처 방법(직접 대화, 경계 설정) 탐색",
        ],
        "conclusion": "공감 + 실용적 조언",
        "confidence": 0.8,
        "synthesis_guidance": {
            "key_points": ["공감", "감정 타당화", "대처 전략"],
            "elements_to_include": ["감정 반영", "구체적 행동 제안"],
            "elements_to_avoid": ["독성 긍정성", "비난"],
        },
    },
}

# --- TIER 2: ScriptGenerator (개발자1) ---
MOCK_SCRIPT_DRAFT = {
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

# --- TIER 2: Synthesis (개발자1) — 대화모드 ---
MOCK_SYNTHESIS = {
    "response_draft": (
        "직장에서 친하게 지내던 후배의 뒷담화를 들으셨군요. "
        "그 상황에서 느끼시는 배신감과 실망감이 충분히 이해됩니다. "
        "중간 관리자로서 위아래 사이에서 조율하려 노력하신 것도 "
        "인정받아야 할 부분입니다."
    ),
}

# --- TIER 3: BatchValidator (개발자3) ---
MOCK_BV_PASS = {
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

MOCK_BV_FAIL = {
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

# --- TIER 3: Validator (개발자3) — 대화모드 ---
MOCK_VALIDATOR_PASS = {
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

# --- TIER 4: ScriptPersonalizer (개발자1) ---
MOCK_FINAL_OUTPUT_PODCAST = {
    "final_output": (
        '{"episode_title": "직장 뒷담화, 상처받은 마음 다스리기", '
        '"segments": [{"type": "intro", "content": "안녕하세요, Mind-Log입니다."}, '
        '{"type": "body", "content": "직장에서의 인간관계는 우리 삶에서 큰 비중을 차지합니다."}, '
        '{"type": "outro", "content": "오늘도 수고하셨습니다."}], '
        '"personalization_applied": true, "tone": "warm_empathetic"}'
    ),
}

# --- TIER 4: Personalization (개발자1) — 대화모드 ---
MOCK_FINAL_OUTPUT_CONVERSATION = {
    "final_output": (
        "직장에서 친하게 지내던 후배의 뒷담화를 듣게 되셨군요. "
        "중간 관리자로서 위아래 사이에서 조율하려 애쓰신 노력이 느껴집니다. "
        "그 상황에서 느끼시는 배신감과 실망감은 자연스러운 감정이에요."
    ),
}

# --- 비동기: Visualization (개발자2) ---
MOCK_VISUALIZATION = {
    "visualization_result": {
        "mode": "podcast",
        "image_url": "mock://visualization/frustration_workplace.png",
        "interpretation_text": "직장 내 갈등과 좌절감을 표현한 따뜻한 톤의 시각화",
        "style_info": {"palette": "warm", "mood": "empathetic"},
    },
}


# ────────────────────────────────────────
# 결과 검증 함수 (test_e2e_multi_provider._validate_result 호환)
# ────────────────────────────────────────


def _validate_result(
    state: dict[str, Any],
    expected_fields: list[str],
) -> dict[str, Any]:
    """ainvoke 결과의 주요 필드를 검증한다."""
    present = sum(1 for f in expected_fields if state.get(f))
    total = len(expected_fields)

    field_details: dict[str, str] = {}
    for field in expected_fields:
        val = state.get(field)
        if val:
            if isinstance(val, dict):
                field_details[field] = f"dict({len(val)} keys)"
            elif isinstance(val, str):
                field_details[field] = f"str({len(val)}자)"
            else:
                field_details[field] = type(val).__name__
        else:
            field_details[field] = "MISSING"

    # 팟캐스트 필드 검증 (test_e2e_multi_provider 호환)
    ca = state.get("content_analysis", {})
    main_theme = ca.get("main_theme", "N/A") if isinstance(ca, dict) else "N/A"

    rr = state.get("reasoning_result", {})
    confidence = rr.get("confidence", "N/A") if isinstance(rr, dict) else "N/A"
    strategy = rr.get("reasoning_strategy", "N/A") if isinstance(rr, dict) else "N/A"

    vr = state.get("validation_result", {})
    bv_score = "N/A"
    if isinstance(vr, dict):
        bv_score = vr.get("overall_score", vr.get("score", "N/A"))

    final_output = state.get("final_output", "")
    final_output_len = len(final_output) if isinstance(final_output, str) else 0

    return {
        "fields_present": present,
        "fields_total": total,
        "field_details": field_details,
        "main_theme": main_theme,
        "confidence": confidence,
        "bv_score": bv_score,
        "strategy": strategy,
        "final_output_len": final_output_len,
    }


# ────────────────────────────────────────
# Fixtures — 초기 상태
# ────────────────────────────────────────


@pytest.fixture
def podcast_initial_state() -> dict[str, Any]:
    """팟캐스트모드 초기 상태 (test_e2e_multi_provider.make_e2e_state와 동일 시나리오)."""
    return {
        "user_input": (
            "아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어. "
            "내가 과장 진급하고 위에서 하도 성과를 가지고 압박하길래 "
            "나도 나름대로 할 수 있을 수준으로 힘들게 네고하고, "
            "후배한테도 최대한 좋게 전달하려고 했던 건데 "
            "이렇게 뒷담을 들어야 한다는게 너무 짜증난다."
        ),
        "user_id": "user_mock_e2e_001",
        "session_id": "sess_mock_e2e_001",
        "mode": "podcast",
    }


@pytest.fixture
def conversation_initial_state() -> dict[str, Any]:
    """대화모드 초기 상태."""
    return {
        "user_input": "요즘 직장에서 스트레스를 많이 받아요. 어떻게 해야 할까요?",
        "user_id": "user_mock_e2e_002",
        "session_id": "sess_mock_e2e_002",
        "mode": "conversation",
    }


@pytest.fixture
def crisis_initial_state() -> dict[str, Any]:
    """위기 상황 초기 상태."""
    return {
        "user_input": "더 이상 살고 싶지 않아요. 모든 게 의미 없어요.",
        "user_id": "user_mock_e2e_crisis",
        "session_id": "sess_mock_e2e_crisis",
        "mode": "podcast",
    }


# ────────────────────────────────────────
# Fixtures — 파이프라인 mock
# ────────────────────────────────────────


@pytest.fixture
def mock_podcast_nodes(monkeypatch):
    """팟캐스트 모드 전체 파이프라인 노드를 mock 데이터로 패치.

    모든 에이전트의 LLM 호출을 mock으로 대체하면서도
    LangGraph의 라우팅, 상태 병합, TIER 흐름은 실제로 실행된다.

    패치 대상 (개발자별):
        개발자1: _intent_classifier.process, _script_generator.process,
                 _script_personalizer.process
        개발자2: safety_node, emotion_node, visualization_node
        개발자3: content_analyzer_node, podcast_reasoning_node,
                 batch_validator_node, learning_node
    """
    import src.graph.workflow as wf

    # --- TIER 0: IntentClassifier (개발자1) ---
    monkeypatch.setattr(
        wf._intent_classifier,
        "process",
        AsyncMock(return_value=MOCK_INTENT_PODCAST),
    )

    # --- TIER 1 (개발자2): Safety, Emotion ---
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))

    # --- TIER 1 (개발자3): ContentAnalyzer, PodcastReasoning ---
    monkeypatch.setattr(
        wf,
        "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf,
        "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )

    # --- TIER 2: ScriptGenerator (개발자1) ---
    monkeypatch.setattr(
        wf._script_generator,
        "process",
        AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
    )

    # --- TIER 3: BatchValidator (개발자3) ---
    monkeypatch.setattr(
        wf, "batch_validator_node", AsyncMock(return_value=MOCK_BV_PASS)
    )

    # --- TIER 4: ScriptPersonalizer (개발자1) ---
    monkeypatch.setattr(
        wf._script_personalizer,
        "process",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
    )

    # --- 비동기 (개발자2, 개발자3) ---
    monkeypatch.setattr(
        wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
    )
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))
    # telemetry_node은 이미 스텁이므로 패치 불필요


@pytest.fixture
def mock_conversation_nodes(monkeypatch):
    """대화 모드 전체 파이프라인 노드를 mock 데이터로 패치.

    패치 대상 (개발자별):
        개발자1: _intent_classifier.process, synthesis_node, personalization_node
        개발자2: safety_node, emotion_node, visualization_node
        개발자3: context_node, reasoning_node, validator_node, learning_node
    """
    import src.graph.workflow as wf

    # --- TIER 0: IntentClassifier (개발자1) ---
    monkeypatch.setattr(
        wf._intent_classifier,
        "process",
        AsyncMock(return_value=MOCK_INTENT_CONVERSATION),
    )

    # --- TIER 1 (개발자2): Safety, Emotion ---
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))

    # --- TIER 1 (개발자3): Context, Reasoning ---
    monkeypatch.setattr(wf, "context_node", AsyncMock(return_value=MOCK_CONTEXT))
    monkeypatch.setattr(
        wf, "reasoning_node", AsyncMock(return_value=MOCK_REASONING_CONVERSATION)
    )

    # --- TIER 2: Synthesis (개발자1) ---
    monkeypatch.setattr(wf, "synthesis_node", AsyncMock(return_value=MOCK_SYNTHESIS))

    # --- TIER 3: Validator (개발자3) ---
    monkeypatch.setattr(
        wf, "validator_node", AsyncMock(return_value=MOCK_VALIDATOR_PASS)
    )

    # --- TIER 4: Personalization (개발자1) ---
    monkeypatch.setattr(
        wf,
        "personalization_node",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_CONVERSATION),
    )

    # --- 비동기 (개발자2, 개발자3) ---
    monkeypatch.setattr(
        wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
    )
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))


@pytest.fixture
def mock_crisis_nodes(monkeypatch):
    """CRISIS 시나리오 노드 mock.

    Safety Agent가 crisis를 반환하여 TIER 1 병렬 작업이 취소되고
    즉시 위기 응답을 반환하는 흐름을 테스트한다.
    """
    import src.graph.workflow as wf

    # --- TIER 0: IntentClassifier (개발자1) ---
    monkeypatch.setattr(
        wf._intent_classifier,
        "process",
        AsyncMock(return_value=MOCK_INTENT_CRISIS),
    )

    # --- TIER 1: Safety → CRISIS (개발자2) ---
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_CRISIS))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf,
        "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf,
        "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )

    # TIER 2~4는 CRISIS 시 실행되지 않으므로 패치 불필요하지만
    # 만약 실행되면 에러를 발생시키도록 설정 (안전장치)
    monkeypatch.setattr(
        wf._script_generator,
        "process",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 2는 실행되면 안 됨")),
    )
    monkeypatch.setattr(
        wf,
        "batch_validator_node",
        AsyncMock(
            side_effect=AssertionError("CRISIS 시 TIER 3는 실행되면 안 됨")
        ),
    )
    monkeypatch.setattr(
        wf._script_personalizer,
        "process",
        AsyncMock(
            side_effect=AssertionError("CRISIS 시 TIER 4는 실행되면 안 됨")
        ),
    )

    # 비동기 후처리도 CRISIS 시 실행되지 않음
    monkeypatch.setattr(
        wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
    )
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))


# ====================================================================
# 테스트 클래스 1: 팟캐스트 모드 전체 파이프라인
# ====================================================================


class TestPodcastPipelineE2E:
    """팟캐스트 모드 전체 파이프라인 E2E 테스트.

    test_e2e_multi_provider와 동일한 흐름:
        TIER 0 → TIER 1 (병렬) → TIER 2 → TIER 3 → TIER 4 → 비동기 → END

    모든 개발자(1, 2, 3)의 에이전트가 참여하며,
    각 에이전트의 출력 필드가 최종 상태에 존재하는지 검증한다.
    """

    @pytest.mark.asyncio
    async def test_full_pipeline(self, mock_podcast_nodes, podcast_initial_state):
        """전체 파이프라인이 TIER 0부터 END까지 정상 실행된다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        # 모든 expected 필드가 존재해야 함
        validation = _validate_result(final_state, EXPECTED_PODCAST_FIELDS)
        assert validation["fields_present"] == validation["fields_total"], (
            f"Missing fields: "
            f"{[k for k, v in validation['field_details'].items() if v == 'MISSING']}"
        )

    @pytest.mark.asyncio
    async def test_all_developers_contribute(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """3명의 개발자 모두의 에이전트가 최종 상태에 기여한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        for developer, fields in DEVELOPER_FIELDS_PODCAST.items():
            for field in fields:
                assert final_state.get(field), (
                    f"{developer}의 {field} 필드가 최종 상태에 없음"
                )

    @pytest.mark.asyncio
    async def test_intent_classification(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """TIER 0 IntentClassifier가 mode=podcast로 분류한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        intent = final_state.get("intent", {})
        assert intent.get("mode") == "podcast"
        assert intent.get("category") == "stress_management"
        assert isinstance(intent.get("complexity_score"), float)

    @pytest.mark.asyncio
    async def test_content_analysis_detail(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """TIER 1 ContentAnalyzer 결과의 상세 필드를 검증한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        ca = final_state.get("content_analysis", {})
        assert ca.get("main_theme"), "main_theme이 없음"
        assert isinstance(ca.get("sub_themes"), list), "sub_themes가 list가 아님"
        assert ca.get("narrative_structure"), "narrative_structure가 없음"

    @pytest.mark.asyncio
    async def test_reasoning_result_detail(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """TIER 1 PodcastReasoning 결과의 상세 필드를 검증한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        rr = final_state.get("reasoning_result", {})
        assert isinstance(rr.get("confidence"), float), "confidence가 float가 아님"
        assert rr.get("reasoning_strategy"), "reasoning_strategy가 없음"
        assert isinstance(rr.get("key_points"), list), "key_points가 list가 아님"

    @pytest.mark.asyncio
    async def test_validation_pass(self, mock_podcast_nodes, podcast_initial_state):
        """TIER 3 BatchValidator가 PASS → TIER 4로 진행한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        vr = final_state.get("validation_result", {})
        assert vr.get("verdict") == "PASS"
        assert isinstance(vr.get("overall_score"), float)
        assert vr["overall_score"] >= 0.7

    @pytest.mark.asyncio
    async def test_final_output_present(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """TIER 4 ScriptPersonalizer가 final_output을 생성한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        final_output = final_state.get("final_output", "")
        assert isinstance(final_output, str)
        assert len(final_output) > 50, f"final_output이 너무 짧음: {len(final_output)}자"

    @pytest.mark.asyncio
    async def test_validate_result_compat(
        self, mock_podcast_nodes, podcast_initial_state
    ):
        """test_e2e_multi_provider._validate_result 호환 검증."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        validation = _validate_result(final_state, EXPECTED_PODCAST_FIELDS)

        # 필드 전부 존재
        assert validation["fields_present"] == 8
        assert validation["fields_total"] == 8

        # 팟캐스트 세부 검증
        assert validation["main_theme"] != "N/A"
        assert isinstance(validation["confidence"], float)
        assert isinstance(validation["bv_score"], float)
        assert validation["strategy"] != "N/A"
        assert validation["final_output_len"] > 0


# ====================================================================
# 테스트 클래스 2: 대화 모드 전체 파이프라인
# ====================================================================


class TestConversationPipelineE2E:
    """대화 모드 전체 파이프라인 E2E 테스트.

    실행 흐름:
        TIER 0 → TIER 1 (Safety + Emotion + Context + Reasoning)
        → TIER 2 (Synthesis) → TIER 3 (Validator) → TIER 4 (Personalization)
        → 비동기 → END
    """

    @pytest.mark.asyncio
    async def test_full_pipeline(
        self, mock_conversation_nodes, conversation_initial_state
    ):
        """대화모드 전체 파이프라인이 정상 실행된다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(conversation_initial_state)

        validation = _validate_result(final_state, EXPECTED_CONVERSATION_FIELDS)
        assert validation["fields_present"] == validation["fields_total"], (
            f"Missing fields: "
            f"{[k for k, v in validation['field_details'].items() if v == 'MISSING']}"
        )

    @pytest.mark.asyncio
    async def test_all_developers_contribute(
        self, mock_conversation_nodes, conversation_initial_state
    ):
        """대화모드에서도 3명의 개발자 모두의 에이전트가 기여한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(conversation_initial_state)

        for developer, fields in DEVELOPER_FIELDS_CONVERSATION.items():
            for field in fields:
                assert final_state.get(field), (
                    f"{developer}의 {field} 필드가 최종 상태에 없음"
                )

    @pytest.mark.asyncio
    async def test_mode_routing(
        self, mock_conversation_nodes, conversation_initial_state
    ):
        """TIER 0에서 mode=conversation으로 라우팅된다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(conversation_initial_state)

        # 대화모드 필드가 있고, 팟캐스트 전용 필드는 없어야 함
        assert final_state.get("context"), "대화모드 context 필드 없음"
        assert final_state.get("response_draft"), "대화모드 response_draft 필드 없음"
        assert not final_state.get("content_analysis"), (
            "대화모드인데 content_analysis(팟캐스트 전용)가 존재"
        )
        assert not final_state.get("script_draft"), (
            "대화모드인데 script_draft(팟캐스트 전용)가 존재"
        )

    @pytest.mark.asyncio
    async def test_final_output_present(
        self, mock_conversation_nodes, conversation_initial_state
    ):
        """대화모드 TIER 4 Personalization이 final_output을 생성한다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(conversation_initial_state)

        final_output = final_state.get("final_output", "")
        assert isinstance(final_output, str)
        assert len(final_output) > 30


# ====================================================================
# 테스트 클래스 3: CRISIS 선점 메커니즘
# ====================================================================


class TestCrisisPreemption:
    """Safety CRISIS 선점 메커니즘 테스트.

    Safety Agent가 crisis 판정 시:
        1. 나머지 TIER 1 병렬 작업 취소
        2. Safety 심화 모드 진입
        3. TIER 2~4 건너뜀
        4. 즉시 위기 응답 반환
    """

    @pytest.mark.asyncio
    async def test_crisis_produces_final_output(
        self, mock_crisis_nodes, crisis_initial_state
    ):
        """CRISIS 시 final_output이 즉시 생성된다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(crisis_initial_state)

        assert final_state.get("final_output"), "CRISIS인데 final_output이 없음"

    @pytest.mark.asyncio
    async def test_crisis_skips_tier2_to_tier4(
        self, mock_crisis_nodes, crisis_initial_state
    ):
        """CRISIS 시 TIER 2~4가 실행되지 않는다.

        mock_crisis_nodes에서 TIER 2~4 mock에 AssertionError를 설정했으므로
        실행되면 테스트가 실패한다.
        """
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()

        # TIER 2~4 mock에 AssertionError가 설정되어 있으므로
        # 실행되면 에러 발생. 정상적으로 완료되면 CRISIS 선점 성공.
        final_state = await compiled.ainvoke(crisis_initial_state)

        # script_draft는 생성되지 않아야 함
        assert not final_state.get("script_draft"), (
            "CRISIS인데 script_draft가 존재 — TIER 2가 실행됨"
        )

    @pytest.mark.asyncio
    async def test_crisis_safety_flags(
        self, mock_crisis_nodes, crisis_initial_state
    ):
        """CRISIS 시 safety_flags에 crisis 상태가 기록된다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(crisis_initial_state)

        sf = final_state.get("safety_flags", {})
        assert sf.get("status") == "crisis"
        assert final_state.get("risk_level", 0) >= 4


# ====================================================================
# 테스트 클래스 4: 재시도 루프
# ====================================================================


class TestRetryLoop:
    """BatchValidator FAIL → TIER 2 재시도 루프 테스트.

    BatchValidator가 FAIL 반환 시:
        1. iteration_count 증가
        2. TIER 2 (ScriptGenerator) 재실행
        3. TIER 3 (BatchValidator) 재실행
        4. PASS 시 TIER 4로 진행
    """

    @pytest.mark.asyncio
    async def test_retry_then_pass(self, monkeypatch, podcast_initial_state):
        """1회 재시도 후 PASS → 정상 완료."""
        import src.graph.workflow as wf

        # TIER 0
        monkeypatch.setattr(
            wf._intent_classifier,
            "process",
            AsyncMock(return_value=MOCK_INTENT_PODCAST),
        )

        # TIER 1
        monkeypatch.setattr(
            wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE)
        )
        monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
        monkeypatch.setattr(
            wf,
            "content_analyzer_node",
            AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
        )
        monkeypatch.setattr(
            wf,
            "podcast_reasoning_node",
            AsyncMock(return_value=MOCK_REASONING_PODCAST),
        )

        # TIER 2: ScriptGenerator (2번 호출됨)
        monkeypatch.setattr(
            wf._script_generator,
            "process",
            AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
        )

        # TIER 3: BatchValidator — 1회차 FAIL, 2회차 PASS
        bv_mock = AsyncMock(side_effect=[MOCK_BV_FAIL, MOCK_BV_PASS])
        monkeypatch.setattr(wf, "batch_validator_node", bv_mock)

        # TIER 4
        monkeypatch.setattr(
            wf._script_personalizer,
            "process",
            AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
        )

        # 비동기
        monkeypatch.setattr(
            wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
        )
        monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))

        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        # 최종적으로 성공해야 함
        assert final_state.get("final_output"), "재시도 후에도 final_output이 없음"
        assert final_state.get("validation_result", {}).get("verdict") == "PASS"

        # BatchValidator가 2번 호출되었는지 확인
        assert bv_mock.call_count == 2, (
            f"BatchValidator {bv_mock.call_count}번 호출됨 (기대: 2번)"
        )

        # iteration_count가 증가했는지 확인
        assert final_state.get("iteration_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_max_retries_force_pass(self, monkeypatch, podcast_initial_state):
        """최대 재시도(2회) 초과 시 강제 통과."""
        import src.graph.workflow as wf

        # TIER 0
        monkeypatch.setattr(
            wf._intent_classifier,
            "process",
            AsyncMock(return_value=MOCK_INTENT_PODCAST),
        )

        # TIER 1
        monkeypatch.setattr(
            wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE)
        )
        monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
        monkeypatch.setattr(
            wf,
            "content_analyzer_node",
            AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
        )
        monkeypatch.setattr(
            wf,
            "podcast_reasoning_node",
            AsyncMock(return_value=MOCK_REASONING_PODCAST),
        )

        # TIER 2: ScriptGenerator (3번 호출 — 초기 1회 + 재시도 2회)
        monkeypatch.setattr(
            wf._script_generator,
            "process",
            AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
        )

        # TIER 3: BatchValidator — 계속 FAIL (최대 재시도 후 강제 통과)
        monkeypatch.setattr(
            wf, "batch_validator_node", AsyncMock(return_value=MOCK_BV_FAIL)
        )

        # TIER 4 (강제 통과 후 실행됨)
        monkeypatch.setattr(
            wf._script_personalizer,
            "process",
            AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
        )

        # 비동기
        monkeypatch.setattr(
            wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
        )
        monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))

        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        final_state = await compiled.ainvoke(podcast_initial_state)

        # 강제 통과 후 final_output이 있어야 함
        assert final_state.get("final_output"), (
            "최대 재시도 후에도 final_output이 없음"
        )


# ====================================================================
# 테스트 클래스 5: 그래프 구조 검증
# ====================================================================


class TestGraphStructure:
    """LangGraph 그래프 구조 검증."""

    def test_unified_graph_node_count(self):
        """통합 그래프에 모든 노드가 등록되어 있다."""
        from src.graph.workflow import build_unified_graph

        graph = build_unified_graph()
        compiled = graph.compile()
        node_names = [n for n in compiled.nodes.keys() if not n.startswith("__")]

        # 최소 노드 수: intent_classifier, tier1_conv, tier1_pod,
        # synthesis, validator, personalization, script_generator,
        # batch_validator, script_personalizer, crisis_response,
        # async_post, increment_iteration_conv, increment_iteration_pod
        assert len(node_names) >= 13, (
            f"노드 수 부족: {len(node_names)}개 — {node_names}"
        )

    def test_podcast_graph_node_count(self):
        """팟캐스트 그래프에 필수 노드가 등록되어 있다."""
        from src.graph.workflow import build_podcast_graph

        graph = build_podcast_graph()
        compiled = graph.compile()
        node_names = [n for n in compiled.nodes.keys() if not n.startswith("__")]

        expected_nodes = {
            "tier1_podcast",
            "script_generator",
            "batch_validator",
            "script_personalizer",
            "crisis_response",
            "async_post",
            "increment_iteration",
        }
        for node in expected_nodes:
            assert node in node_names, f"팟캐스트 그래프에 {node} 노드가 없음"

    def test_conversation_graph_node_count(self):
        """대화 그래프에 필수 노드가 등록되어 있다."""
        from src.graph.workflow import build_conversation_graph

        graph = build_conversation_graph()
        compiled = graph.compile()
        node_names = [n for n in compiled.nodes.keys() if not n.startswith("__")]

        expected_nodes = {
            "tier1_conversation",
            "synthesis",
            "validator",
            "personalization",
            "crisis_response",
            "async_post",
            "increment_iteration",
        }
        for node in expected_nodes:
            assert node in node_names, f"대화 그래프에 {node} 노드가 없음"

    def test_compile_graph_helper(self):
        """compile_graph() 헬퍼가 올바르게 동작한다."""
        from src.graph.workflow import compile_graph

        for builder in ("unified", "conversation", "podcast"):
            compiled = compile_graph(builder)
            assert compiled is not None, f"{builder} 그래프 컴파일 실패"

    def test_compile_graph_invalid_builder(self):
        """compile_graph()에 잘못된 builder를 전달하면 ValueError."""
        from src.graph.workflow import compile_graph

        with pytest.raises(ValueError, match="Unknown graph builder"):
            compile_graph("invalid_builder")


# ====================================================================
# 테스트 클래스 6: 팟캐스트 전용 그래프 (TIER 0 없이)
# ====================================================================


class TestPodcastGraphDirect:
    """build_podcast_graph()로 TIER 0 없이 팟캐스트 파이프라인을 직접 실행."""

    @pytest.mark.asyncio
    async def test_podcast_graph_direct(self, monkeypatch):
        """팟캐스트 그래프가 tier1_podcast부터 END까지 실행된다."""
        import src.graph.workflow as wf

        # TIER 1
        monkeypatch.setattr(
            wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE)
        )
        monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
        monkeypatch.setattr(
            wf,
            "content_analyzer_node",
            AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
        )
        monkeypatch.setattr(
            wf,
            "podcast_reasoning_node",
            AsyncMock(return_value=MOCK_REASONING_PODCAST),
        )

        # TIER 2
        monkeypatch.setattr(
            wf._script_generator,
            "process",
            AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
        )

        # TIER 3
        monkeypatch.setattr(
            wf, "batch_validator_node", AsyncMock(return_value=MOCK_BV_PASS)
        )

        # TIER 4
        monkeypatch.setattr(
            wf._script_personalizer,
            "process",
            AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
        )

        # 비동기
        monkeypatch.setattr(
            wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION)
        )
        monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))

        from src.graph.workflow import build_podcast_graph

        graph = build_podcast_graph()
        compiled = graph.compile()

        # TIER 0 없이 직접 실행 — intent는 미리 설정
        initial_state = {
            "user_input": "직장 스트레스에 대해 이야기해 주세요.",
            "user_id": "user_podcast_direct",
            "session_id": "sess_podcast_direct",
            "mode": "podcast",
            "intent": {
                "mode": "podcast",
                "category": "stress",
                "complexity_score": 0.6,
            },
        }

        final_state = await compiled.ainvoke(initial_state)

        # TIER 1~4 + 비동기 결과 검증
        assert final_state.get("safety_flags"), "safety_flags 없음"
        assert final_state.get("emotion_vectors"), "emotion_vectors 없음"
        assert final_state.get("content_analysis"), "content_analysis 없음"
        assert final_state.get("reasoning_result"), "reasoning_result 없음"
        assert final_state.get("script_draft"), "script_draft 없음"
        assert final_state.get("validation_result"), "validation_result 없음"
        assert final_state.get("final_output"), "final_output 없음"

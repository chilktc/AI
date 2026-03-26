"""
Mock 기반 전체 파이프라인 E2E 테스트.

모든 개발자의 에이전트가 참여하는 전체 LangGraph 파이프라인을
mock 데이터로 실행하고 결과를 검증한다.

사용법:
    pytest tests/graph/test_e2e_mock_pipeline.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from tests.shared_fixtures.mock_data import (
    DEVELOPER_FIELDS_CONVERSATION,
    DEVELOPER_FIELDS_PODCAST,
    EXPECTED_CONVERSATION_FIELDS,
    EXPECTED_PODCAST_FIELDS,
    MOCK_BV_FAIL,
    MOCK_BV_PASS,
    MOCK_CONTENT_ANALYSIS,
    MOCK_CONTEXT,
    MOCK_EMOTION,
    MOCK_FINAL_OUTPUT_CONVERSATION,
    MOCK_FINAL_OUTPUT_PODCAST,
    MOCK_INTENT_CONVERSATION,
    MOCK_INTENT_CRISIS,
    MOCK_INTENT_PODCAST,
    MOCK_REASONING_CONVERSATION,
    MOCK_REASONING_PODCAST,
    MOCK_SAFETY_CRISIS,
    MOCK_SAFETY_SAFE,
    MOCK_SCRIPT_DRAFT,
    MOCK_SYNTHESIS,
    MOCK_VALIDATOR_PASS,
    MOCK_VISUALIZATION,
)

# ────────────────────────────────────────
# 결과 검증 함수
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

    ca = state.get("content_analysis", {})
    main_theme = ca.get("main_theme", "N/A") if isinstance(ca, dict) else "N/A"
    rr = state.get("reasoning_result", {})
    confidence = rr.get("confidence", "N/A") if isinstance(rr, dict) else "N/A"
    strategy = rr.get("reasoning_strategy", "N/A") if isinstance(rr, dict) else "N/A"
    vr = state.get("validation_result", {})
    bv_score = vr.get("overall_score", vr.get("score", "N/A")) if isinstance(vr, dict) else "N/A"
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
    """팟캐스트모드 초기 상태."""
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
    """팟캐스트 모드 전체 파이프라인 노드를 mock 데이터로 패치."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf._intent_classifier, "process",
        AsyncMock(return_value=MOCK_INTENT_PODCAST),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf, "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf, "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )
    monkeypatch.setattr(
        wf._script_generator, "process",
        AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
    )
    monkeypatch.setattr(wf, "batch_validator_node", AsyncMock(return_value=MOCK_BV_PASS))
    monkeypatch.setattr(
        wf._script_personalizer, "process",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))


@pytest.fixture
def mock_conversation_nodes(monkeypatch):
    """대화 모드 전체 파이프라인 노드를 mock 데이터로 패치."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf._intent_classifier, "process",
        AsyncMock(return_value=MOCK_INTENT_CONVERSATION),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(wf, "context_node", AsyncMock(return_value=MOCK_CONTEXT))
    monkeypatch.setattr(
        wf, "reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_CONVERSATION),
    )
    monkeypatch.setattr(wf, "synthesis_node", AsyncMock(return_value=MOCK_SYNTHESIS))
    monkeypatch.setattr(wf, "validator_node", AsyncMock(return_value=MOCK_VALIDATOR_PASS))
    monkeypatch.setattr(
        wf, "personalization_node",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_CONVERSATION),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))


@pytest.fixture
def mock_crisis_nodes(monkeypatch):
    """CRISIS 시나리오 노드 mock."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf._intent_classifier, "process",
        AsyncMock(return_value=MOCK_INTENT_CRISIS),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_CRISIS))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf, "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf, "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )
    monkeypatch.setattr(
        wf._script_generator, "process",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 2는 실행되면 안 됨")),
    )
    monkeypatch.setattr(
        wf, "batch_validator_node",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 3는 실행되면 안 됨")),
    )
    monkeypatch.setattr(
        wf._script_personalizer, "process",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 4는 실행되면 안 됨")),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))


# ====================================================================
# 팟캐스트 모드 파이프라인 테스트
# ====================================================================


@pytest.mark.asyncio
async def test_podcast_e2e_full(mock_podcast_nodes, podcast_initial_state):
    """팟캐스트 전체 파이프라인: 필드 존재 + TIER 상세 + final_output 통합 검증."""
    from src.graph.workflow import build_unified_graph

    graph = build_unified_graph()
    final_state = await graph.compile().ainvoke(podcast_initial_state)

    # 모든 expected 필드 존재
    validation = _validate_result(final_state, EXPECTED_PODCAST_FIELDS)
    assert validation["fields_present"] == validation["fields_total"], (
        f"Missing: {[k for k, v in validation['field_details'].items() if v == 'MISSING']}"
    )

    # 3명의 개발자 모두 기여
    for developer, fields in DEVELOPER_FIELDS_PODCAST.items():
        for field in fields:
            assert final_state.get(field), f"{developer}의 {field} 필드 없음"

    # _validate_result 호환 검증
    assert validation["main_theme"] != "N/A"
    assert isinstance(validation["confidence"], float)
    assert isinstance(validation["bv_score"], float)
    assert validation["final_output_len"] > 0

    # Intent (TIER 0)
    intent = final_state.get("intent", {})
    assert intent.get("mode") == "podcast"
    assert intent.get("category") == "stress_management"
    assert isinstance(intent.get("complexity_score"), float)

    # ContentAnalysis (TIER 1)
    ca = final_state.get("content_analysis", {})
    assert ca.get("main_theme")
    assert isinstance(ca.get("sub_themes"), list)

    # Reasoning (TIER 1)
    rr = final_state.get("reasoning_result", {})
    assert isinstance(rr.get("confidence"), float)
    assert rr.get("reasoning_strategy")

    # Validation (TIER 3)
    vr = final_state.get("validation_result", {})
    assert vr.get("verdict") == "PASS"
    assert vr["overall_score"] >= 0.7

    # final_output (TIER 4)
    final_output = final_state.get("final_output", "")
    assert isinstance(final_output, str)
    assert len(final_output) > 50


# ====================================================================
# 대화 모드 파이프라인 테스트
# ====================================================================


@pytest.mark.asyncio
async def test_conversation_full_pipeline(mock_conversation_nodes, conversation_initial_state):
    """대화모드 전체 파이프라인이 정상 실행되고 3명 개발자 모두 기여한다."""
    from src.graph.workflow import build_unified_graph

    final_state = await build_unified_graph().compile().ainvoke(conversation_initial_state)

    validation = _validate_result(final_state, EXPECTED_CONVERSATION_FIELDS)
    assert validation["fields_present"] == validation["fields_total"], (
        f"Missing: {[k for k, v in validation['field_details'].items() if v == 'MISSING']}"
    )

    for developer, fields in DEVELOPER_FIELDS_CONVERSATION.items():
        for field in fields:
            assert final_state.get(field), f"{developer}의 {field} 필드 없음"


@pytest.mark.asyncio
async def test_conversation_mode_routing(mock_conversation_nodes, conversation_initial_state):
    """TIER 0에서 mode=conversation으로 라우팅되어 대화모드 전용 필드만 존재한다."""
    from src.graph.workflow import build_unified_graph

    final_state = await build_unified_graph().compile().ainvoke(conversation_initial_state)

    assert final_state.get("context"), "대화모드 context 필드 없음"
    assert final_state.get("response_draft"), "대화모드 response_draft 필드 없음"
    assert not final_state.get("content_analysis"), "대화모드인데 content_analysis 존재"
    assert not final_state.get("script_draft"), "대화모드인데 script_draft 존재"

    final_output = final_state.get("final_output", "")
    assert isinstance(final_output, str) and len(final_output) > 30


# ====================================================================
# CRISIS 선점 메커니즘 테스트
# ====================================================================


@pytest.mark.asyncio
async def test_crisis_e2e_full(mock_crisis_nodes, crisis_initial_state):
    """CRISIS E2E: final_output 즉시 생성 + TIER 2~4 스킵 + safety_flags 통합 검증."""
    from src.graph.workflow import build_unified_graph

    final_state = await build_unified_graph().compile().ainvoke(crisis_initial_state)

    # final_output 즉시 생성
    assert final_state.get("final_output"), "CRISIS인데 final_output 없음"

    # TIER 2~4 스킵 (mock에 AssertionError 설정됨)
    assert not final_state.get("script_draft"), "CRISIS인데 script_draft 존재"

    # safety_flags에 crisis 상태 기록
    sf = final_state.get("safety_flags", {})
    assert sf.get("status") == "crisis"
    assert final_state.get("risk_level", 0) >= 4


# ====================================================================
# 재시도 루프 테스트
# ====================================================================


@pytest.mark.asyncio
async def test_retry_then_pass(monkeypatch, podcast_initial_state):
    """1회 재시도 후 PASS → 정상 완료."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf._intent_classifier, "process",
        AsyncMock(return_value=MOCK_INTENT_PODCAST),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf, "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf, "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )
    monkeypatch.setattr(
        wf._script_generator, "process",
        AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
    )

    bv_mock = AsyncMock(side_effect=[MOCK_BV_FAIL, MOCK_BV_PASS])
    monkeypatch.setattr(wf, "batch_validator_node", bv_mock)
    monkeypatch.setattr(
        wf._script_personalizer, "process",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))

    from src.graph.workflow import build_unified_graph

    final_state = await build_unified_graph().compile().ainvoke(podcast_initial_state)

    assert final_state.get("final_output"), "재시도 후에도 final_output 없음"
    assert final_state.get("validation_result", {}).get("verdict") == "PASS"
    assert bv_mock.call_count == 2
    assert final_state.get("iteration_count", 0) >= 1


# ====================================================================
# 그래프 구조 검증
# ====================================================================


@pytest.mark.parametrize(
    "builder_name, expected_nodes",
    [
        (
            "podcast",
            {"tier1_podcast", "tier2_podcast", "batch_validator",
             "script_personalizer", "crisis_response", "async_post", "increment_iteration"},
        ),
        (
            "conversation",
            {"tier1_conversation", "synthesis", "validator",
             "personalization", "crisis_response", "async_post", "increment_iteration"},
        ),
    ],
    ids=["podcast", "conversation"],
)
def test_mode_graph_required_nodes(builder_name: str, expected_nodes: set[str]):
    """모드별 그래프에 필수 노드가 모두 등록되어 있다."""
    from src.graph.workflow import build_conversation_graph, build_podcast_graph

    builder = build_podcast_graph if builder_name == "podcast" else build_conversation_graph
    compiled = builder().compile()
    node_names = [n for n in compiled.nodes.keys() if not n.startswith("__")]

    for node in expected_nodes:
        assert node in node_names, f"{builder_name} 그래프에 {node} 노드 없음"

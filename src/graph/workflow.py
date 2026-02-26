"""
LangGraph 워크플로우 정의 — 듀얼모드 TIER 기반 파이프라인.

[Protected File] 수정 시 3인 합의 필수.

TIER 기반 파이프라인:
    TIER 0: Intent Classifier → 의도 분류 + 모드 감지
    TIER 1 (병렬 Fan-out): Safety + Emotion + Context/ContentAnalyzer + Reasoning/PodcastReasoning
    TIER 2 (생성): Synthesis / Script Generator (+Visualization 병렬)
    TIER 3 (검증): Validator / Batch Validator (실패 시 TIER 2 재시도, 최대 2회)
    TIER 4 (후처리): Personalization / Script Personalizer
    비동기: Visualization + Telemetry + Learning

Safety CRISIS 선점:
    Safety Agent의 CRISIS 판정 → asyncio.Event로 병렬 작업 취소 → 즉시 위기 응답

참조:
    - ProjectDocs/ARCHITECTURE_v4.0.md line 237-264 — CRISIS 선점 pseudo-code
    - src/models/agent_state.py — AgentState 스키마
    - config/settings.yaml line 155-160 — pipeline 설정
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from config.loader import get_settings
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 설정 로드
# ---------------------------------------------------------------------------
_settings = get_settings()
_pipeline_config = _settings._config.get("pipeline", {})
_MAX_RETRIES: int = _pipeline_config.get("max_retries", 2)
_TIER1_TIMEOUT: int = _pipeline_config.get("tier1_timeout_seconds", 15)

# ---------------------------------------------------------------------------
# 구현된 에이전트 노드 — 실제 import
# ---------------------------------------------------------------------------
from src.agents.shared.learning import learning_node  # noqa: E402


# ---------------------------------------------------------------------------
# 미구현 에이전트 스텁 노드
# ---------------------------------------------------------------------------
async def _stub_node(name: str, state: AgentState) -> dict[str, Any]:
    """미구현 에이전트 임시 스텁 — 빈 dict 반환 + 경고 로그."""
    logger.warning("[STUB] %s 미구현 — 빈 결과 반환", name)
    return {}


# --- TIER 0 (개발자1) ---
from src.agents.conversation.intent_classifier import IntentClassifierAgent
_intent_classifier = IntentClassifierAgent()

async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """Intent Classifier 노드"""
    return await _intent_classifier.process(state)


# --- TIER 1 공용 (개발자2) ---
async def safety_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Safety Agent — 개발자2 구현 예정."""
    return await _stub_node("safety", state)


async def emotion_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Emotion Agent — 개발자2 구현 예정."""
    return await _stub_node("emotion", state)


# --- TIER 1 대화모드 (개발자3) ---
async def context_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Context Agent — 개발자3 구현 예정."""
    return await _stub_node("context", state)


async def reasoning_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Reasoning Agent — 개발자3 구현 예정."""
    return await _stub_node("reasoning", state)


# --- TIER 2 대화모드 (개발자1) ---
async def synthesis_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Synthesis Agent — 개발자1 구현 예정."""
    return await _stub_node("synthesis", state)


# --- TIER 3 대화모드 (개발자3) ---
async def validator_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Validator Agent — 개발자3 구현 예정."""
    return await _stub_node("validator", state)


# --- TIER 4 대화모드 (개발자1) ---
async def personalization_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Personalization Agent — 개발자1 구현 예정."""
    return await _stub_node("personalization", state)


# --- TIER 2 팟캐스트모드 (개발자1) ---
from src.agents.podcast.script_generator import ScriptGeneratorAgent
_script_generator = ScriptGeneratorAgent()

async def script_generator_node(state: AgentState) -> dict[str, Any]:
    """Script Generator 노드"""
    return await _script_generator.process(state)


# --- TIER 4 팟캐스트모드 (개발자1) ---
from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent
_script_personalizer = ScriptPersonalizerAgent()

async def script_personalizer_node(state: AgentState) -> dict[str, Any]:
    """Script Personalizer 노드"""
    return await _script_personalizer.process(state)

# --- 비동기 팟캐스트 스텁 추가 ---
async def content_analyzer_node(state: AgentState) -> dict[str, Any]:
    return await _stub_node("content_analyzer", state)

async def podcast_reasoning_node(state: AgentState) -> dict[str, Any]:
    return await _stub_node("podcast_reasoning", state)

async def batch_validator_node(state: AgentState) -> dict[str, Any]:
    return await _stub_node("batch_validator", state)


# --- 비동기 (개발자2) ---
async def visualization_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Visualization Agent — 개발자2 구현 예정."""
    return await _stub_node("visualization", state)


# --- 비동기 (미정) ---
async def telemetry_node(state: AgentState) -> dict[str, Any]:
    """[STUB] Telemetry Agent — 담당 미정."""
    return await _stub_node("telemetry", state)


# ===================================================================
# 헬퍼: 취소 가능 코루틴 래퍼
# ===================================================================
async def run_with_cancel(
    coro: Any,
    cancel_event: asyncio.Event,
    name: str,
) -> tuple[str, dict[str, Any]]:
    """
    asyncio.Event 기반 취소 가능 코루틴 래퍼.

    cancel_event가 set 되면 진행 중인 코루틴을 취소하고 빈 dict를 반환한다.
    Safety CRISIS 선점 시 나머지 TIER 1 태스크를 취소하는 데 사용.

    Args:
        coro: 실행할 코루틴
        cancel_event: 취소 신호 이벤트
        name: 태스크 식별자 (로깅용)

    Returns:
        (name, result) 튜플
    """
    task = asyncio.ensure_future(coro)
    cancel_waiter = asyncio.ensure_future(cancel_event.wait())

    try:
        done, _ = await asyncio.wait(
            [task, cancel_waiter],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if cancel_waiter in done and task not in done:
            # 취소 신호 수신 → 태스크 취소
            task.cancel()
            logger.info("[CANCEL] %s 취소됨 (CRISIS 선점)", name)
            cancel_waiter = None  # type: ignore[assignment]
            return (name, {})

        result = task.result()
        return (name, result)

    except asyncio.CancelledError:
        logger.info("[CANCEL] %s CancelledError", name)
        return (name, {})
    finally:
        # 정리: 대기 중인 cancel_waiter 취소
        if not cancel_waiter.done():
            cancel_waiter.cancel()


# ===================================================================
# CRISIS 심화 응답 (Safety Agent가 직접 위기 응답 생성)
# ===================================================================
async def _safety_deep_crisis(safety_result: dict[str, Any]) -> dict[str, Any]:
    """
    Safety CRISIS 심화 모드.

    Safety Agent가 CRISIS 판정 시 즉시 위기 응답을 생성한다.
    실제 구현은 Safety Agent(개발자2)가 담당.

    Args:
        safety_result: Safety Agent의 CRISIS 판정 결과

    Returns:
        위기 응답 포함 상태 dict
    """
    logger.critical("[CRISIS] Safety 심화 모드 진입 — 즉시 위기 응답 생성")
    # TODO: 개발자2가 Safety Agent 심화 로직 구현
    return {
        "safety_flags": safety_result.get("safety_flags", {}),
        "risk_level": safety_result.get("risk_level", 4),
        "risk_score": safety_result.get("risk_score", 1.0),
        "final_output": safety_result.get(
            "crisis_response",
            "지금 힘든 상황이시군요. 전문 상담사와 연결해 드리겠습니다.",
        ),
    }


# ===================================================================
# TIER 1 Fan-out 함수
# ===================================================================
async def tier1_conversation_fan_out(state: AgentState) -> dict[str, Any]:
    """
    대화모드 TIER 1: Safety + Emotion + Context + Reasoning 병렬 실행.

    Safety CRISIS 선점 메커니즘:
        Safety가 crisis 반환 시 cancel_event.set() → 나머지 취소 → 즉시 위기 응답
    """
    cancel_event = asyncio.Event()

    tasks = [
        run_with_cancel(safety_node(state), cancel_event, "safety"),
        run_with_cancel(emotion_node(state), cancel_event, "emotion"),
        run_with_cancel(context_node(state), cancel_event, "context"),
        run_with_cancel(reasoning_node(state), cancel_event, "reasoning"),
    ]

    merged: dict[str, Any] = {}
    for coro in asyncio.as_completed(tasks):
        name, result = await coro

        if (
            name == "safety"
            and result.get("safety_flags", {}).get("status") == "crisis"
        ):
            # ■ CRISIS: 나머지 모두 취소 → Safety 심화 → 즉시 응답
            cancel_event.set()
            deep_result = await _safety_deep_crisis(result)
            return {**deep_result, "next_step": "crisis_response"}

        merged.update(result)

    # 정상: 4개 결과 모두 TIER 2로 전달
    return merged


async def tier1_podcast_fan_out(state: AgentState) -> dict[str, Any]:
    """
    팟캐스트모드 TIER 1: Safety + Emotion + ContentAnalyzer + PodcastReasoning 병렬 실행.

    Safety CRISIS 선점 메커니즘은 대화모드와 동일.
    """
    cancel_event = asyncio.Event()

    tasks = [
        run_with_cancel(safety_node(state), cancel_event, "safety"),
        run_with_cancel(emotion_node(state), cancel_event, "emotion"),
        run_with_cancel(content_analyzer_node(state), cancel_event, "content_analyzer"),
        run_with_cancel(
            podcast_reasoning_node(state), cancel_event, "podcast_reasoning"
        ),
    ]

    merged: dict[str, Any] = {}
    for coro in asyncio.as_completed(tasks):
        name, result = await coro

        if (
            name == "safety"
            and result.get("safety_flags", {}).get("status") == "crisis"
        ):
            cancel_event.set()
            deep_result = await _safety_deep_crisis(result)
            return {**deep_result, "next_step": "crisis_response"}

        merged.update(result)

    return merged


# ===================================================================
# 비동기 후처리 (Fire-and-forget)
# ===================================================================
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    """
    비동기 후처리: Visualization + Telemetry + Learning.

    최종 응답 출력 후 백그라운드에서 실행.
    실패해도 파이프라인에 영향 없음.
    """
    tasks = [
        asyncio.create_task(visualization_node(state)),
        asyncio.create_task(telemetry_node(state)),
        asyncio.create_task(learning_node(state)),
    ]

    results: dict[str, Any] = {}
    for task in asyncio.as_completed(tasks):
        try:
            result = await task
            results.update(result)
        except Exception:
            logger.exception("[ASYNC] 비동기 후처리 태스크 실패 — 무시")

    return results


# ===================================================================
# 라우터 함수
# ===================================================================
def route_after_tier0(state: AgentState) -> str:
    """
    TIER 0 이후 라우터: mode 필드 기반 대화/팟캐스트 분기.

    Returns:
        "tier1_conversation" | "tier1_podcast"
    """
    mode = state.get("mode", "conversation")
    if mode == "podcast":
        return "tier1_podcast"
    return "tier1_conversation"


def route_after_tier1(state: AgentState) -> str:
    """
    TIER 1 이후 라우터: CRISIS 여부 확인.

    Returns:
        "crisis_response" | "tier2"
    """
    if state.get("next_step") == "crisis_response":
        return "crisis_response"
    return "tier2"


def route_after_tier3_conversation(state: AgentState) -> str:
    """
    대화모드 TIER 3 이후 라우터: 검증 결과 기반 분기.

    Returns:
        "tier4" — 검증 통과
        "tier2_conversation" — 재시도 필요 (iteration_count < max_retries)
        "crisis_response" — 위기 응답 (safety 에스컬레이션)
    """
    next_step = state.get("next_step", "")

    if next_step == "crisis_response":
        return "crisis_response"

    validation = state.get("validation_result", {})
    action = validation.get("action", {})
    decision = action.get("decision", "approve")

    if decision == "approve":
        return "tier4"

    # revise 또는 escalate
    iteration_count = state.get("iteration_count", 0)
    if decision == "revise" and iteration_count < _MAX_RETRIES:
        return "tier2_conversation"

    # 최대 재시도 초과 또는 escalate → 강제 통과
    logger.warning(
        "[RETRY] 최대 재시도(%d) 도달 — 강제 통과", _MAX_RETRIES
    )
    return "tier4"


def route_after_tier3_podcast(state: AgentState) -> str:
    """
    팟캐스트모드 TIER 3 이후 라우터.

    Returns:
        "tier4_podcast" | "tier2_podcast" | "crisis_response"
    """
    next_step = state.get("next_step", "")

    if next_step == "crisis_response":
        return "crisis_response"

    validation = state.get("validation_result", {})
    verdict = validation.get("verdict", "PASS")

    if verdict == "CRITICAL_FAIL":
        logger.critical("[CRITICAL_FAIL] 팟캐스트 스크립트 치명적 실패 — 즉시 중단")
        return "crisis_response"

    if verdict == "PASS":
        return "tier4_podcast"

    # FAIL → 재시도
    iteration_count = state.get("iteration_count", 0)
    if iteration_count < _MAX_RETRIES:
        return "tier2_podcast"

    logger.warning(
        "[RETRY] 팟캐스트 최대 재시도(%d) 도달 — 강제 통과", _MAX_RETRIES
    )
    return "tier4_podcast"


# ===================================================================
# CRISIS 즉시 응답 노드
# ===================================================================
async def crisis_response_node(state: AgentState) -> dict[str, Any]:
    """
    CRISIS 즉시 응답 노드.

    Safety CRISIS 또는 Validator 에스컬레이션 시 호출.
    final_output이 이미 설정된 경우 그대로 전달.
    """
    if state.get("final_output"):
        return {"next_step": "end"}

    return {
        "final_output": "지금 힘든 상황이시군요. 전문 상담사와 연결해 드리겠습니다.",
        "next_step": "end",
    }


# ===================================================================
# 재시도 카운터 증가 노드
# ===================================================================
async def increment_iteration_node(state: AgentState) -> dict[str, Any]:
    """iteration_count를 1 증가시킨다."""
    current = state.get("iteration_count", 0)
    return {"iteration_count": current + 1}


# ===================================================================
# 그래프 빌더
# ===================================================================
def build_conversation_graph() -> StateGraph:
    """
    대화모드 StateGraph 구축.

    TIER 1(병렬) → TIER 2(생성) → TIER 3(검증) → TIER 4(후처리)
    + CRISIS 선점 + 재시도 루프
    """
    graph = StateGraph(AgentState)

    # --- 노드 등록 ---
    graph.add_node("tier1_conversation", tier1_conversation_fan_out)
    graph.add_node("tier2_conversation", synthesis_node)
    graph.add_node("tier3_conversation", validator_node)
    graph.add_node("tier4_conversation", personalization_node)
    graph.add_node("crisis_response", crisis_response_node)
    graph.add_node("async_post", async_post_processing_node)
    graph.add_node("increment_iteration", increment_iteration_node)

    # --- 엣지 정의 ---
    # TIER 1 → CRISIS 확인
    graph.add_conditional_edges(
        "tier1_conversation",
        route_after_tier1,
        {
            "tier2": "tier2_conversation",
            "crisis_response": "crisis_response",
        },
    )

    # TIER 2 → TIER 3
    graph.add_edge("tier2_conversation", "tier3_conversation")

    # TIER 3 → 분기 (통과/재시도/위기)
    graph.add_conditional_edges(
        "tier3_conversation",
        route_after_tier3_conversation,
        {
            "tier4": "tier4_conversation",
            "tier2_conversation": "increment_iteration",
            "crisis_response": "crisis_response",
        },
    )

    # 재시도 카운터 증가 → TIER 2 재실행
    graph.add_edge("increment_iteration", "tier2_conversation")

    # TIER 4 → 비동기 후처리
    graph.add_edge("tier4_conversation", "async_post")

    # 비동기 후처리 → 종료
    graph.add_edge("async_post", END)

    # CRISIS → 종료
    graph.add_edge("crisis_response", END)

    # 진입점
    graph.set_entry_point("tier1_conversation")

    return graph


def build_podcast_graph() -> StateGraph:
    """
    팟캐스트모드 StateGraph 구축.

    TIER 1(병렬) → TIER 2(스크립트 생성) → TIER 3(배치 검증) → TIER 4(개인화)
    + CRISIS 선점 + 재시도 루프
    """
    graph = StateGraph(AgentState)

    # --- 노드 등록 ---
    graph.add_node("tier1_podcast", tier1_podcast_fan_out)
    graph.add_node("tier2_podcast", script_generator_node)
    graph.add_node("tier3_podcast", batch_validator_node)
    graph.add_node("tier4_podcast", script_personalizer_node)
    graph.add_node("crisis_response", crisis_response_node)
    graph.add_node("async_post", async_post_processing_node)
    graph.add_node("increment_iteration", increment_iteration_node)

    # --- 엣지 정의 ---
    graph.add_conditional_edges(
        "tier1_podcast",
        route_after_tier1,
        {
            "tier2": "tier2_podcast",
            "crisis_response": "crisis_response",
        },
    )

    graph.add_edge("tier2_podcast", "tier3_podcast")

    graph.add_conditional_edges(
        "tier3_podcast",
        route_after_tier3_podcast,
        {
            "tier4_podcast": "tier4_podcast",
            "tier2_podcast": "increment_iteration",
            "crisis_response": "crisis_response",
        },
    )

    graph.add_edge("increment_iteration", "tier2_podcast")
    graph.add_edge("tier4_podcast", "async_post")
    graph.add_edge("async_post", END)
    graph.add_edge("crisis_response", END)

    graph.set_entry_point("tier1_podcast")

    return graph


def build_unified_graph() -> StateGraph:
    """
    통합 진입점: TIER 0 → 모드 분기 → 대화/팟캐스트 파이프라인.

    사용법:
        graph = build_unified_graph()
        compiled = graph.compile()
        result = await compiled.ainvoke({"user_input": "...", "user_id": "..."})
    """
    graph = StateGraph(AgentState)

    # --- TIER 0: Intent Classifier ---
    graph.add_node("tier0", intent_classifier_node)

    # --- 대화모드 노드 ---
    graph.add_node("tier1_conversation", tier1_conversation_fan_out)
    graph.add_node("tier2_conversation", synthesis_node)
    graph.add_node("tier3_conversation", validator_node)
    graph.add_node("tier4_conversation", personalization_node)

    # --- 팟캐스트모드 노드 ---
    graph.add_node("tier1_podcast", tier1_podcast_fan_out)
    graph.add_node("tier2_podcast", script_generator_node)
    graph.add_node("tier3_podcast", batch_validator_node)
    graph.add_node("tier4_podcast", script_personalizer_node)

    # --- 공용 노드 ---
    graph.add_node("crisis_response", crisis_response_node)
    graph.add_node("async_post", async_post_processing_node)
    graph.add_node("increment_iteration_conv", increment_iteration_node)
    graph.add_node("increment_iteration_pod", increment_iteration_node)

    # --- TIER 0 → 모드 분기 ---
    graph.add_conditional_edges(
        "tier0",
        route_after_tier0,
        {
            "tier1_conversation": "tier1_conversation",
            "tier1_podcast": "tier1_podcast",
        },
    )

    # === 대화모드 엣지 ===
    graph.add_conditional_edges(
        "tier1_conversation",
        route_after_tier1,
        {
            "tier2": "tier2_conversation",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("tier2_conversation", "tier3_conversation")
    graph.add_conditional_edges(
        "tier3_conversation",
        route_after_tier3_conversation,
        {
            "tier4": "tier4_conversation",
            "tier2_conversation": "increment_iteration_conv",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("increment_iteration_conv", "tier2_conversation")
    graph.add_edge("tier4_conversation", "async_post")

    # === 팟캐스트모드 엣지 ===
    graph.add_conditional_edges(
        "tier1_podcast",
        route_after_tier1,
        {
            "tier2": "tier2_podcast",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("tier2_podcast", "tier3_podcast")
    graph.add_conditional_edges(
        "tier3_podcast",
        route_after_tier3_podcast,
        {
            "tier4_podcast": "tier4_podcast",
            "tier2_podcast": "increment_iteration_pod",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("increment_iteration_pod", "tier2_podcast")
    graph.add_edge("tier4_podcast", "async_post")

    # === 공용 엣지 ===
    graph.add_edge("async_post", END)
    graph.add_edge("crisis_response", END)

    # --- 진입점 ---
    graph.set_entry_point("tier0")

    return graph

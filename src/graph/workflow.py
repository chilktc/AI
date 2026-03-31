"""
LangGraph 워크플로우 정의 — 듀얼모드 TIER 기반 파이프라인.

[Protected File] 수정 시 3인 합의 필수.

TIER 기반 파이프라인:
    TIER 0: Intent Classifier → 의도 분류 + 모드 감지
    TIER 1 (병렬 Fan-out): Safety + Emotion + Context/ContentAnalyzer + Reasoning/PodcastReasoning
    TIER 2 (생성): Synthesis / Script Generator (+Visualization 병렬)
    TIER 3 (검증): Validator / Batch Validator (실패 시 TIER 2 재시도, 최대 2회)
    TIER 4 (후처리): Personalization / Script Personalizer
    비동기: Telemetry + Learning

Safety CRISIS 선점:
    Safety Agent의 CRISIS 판정 → asyncio.Event로 병렬 작업 취소 → 즉시 위기 응답

스트리밍 이벤트:
    get_stream_writer()로 TIER 시작/완료, 에이전트 완료, CRISIS 이벤트를 실시간 발행.
    stream_mode=["updates", "custom"]으로 소비 가능.

체크포인팅:
    compile_graph()에 checkpointer 전달 시 상태 체크포인팅 활성화.
    InMemorySaver(dev) 또는 PostgresSaver(prod) 사용.

참조:
    - ProjectDocs/ARCHITECTURE_v4.0.md line 237-264 — CRISIS 선점 pseudo-code
    - src/models/agent_state.py — AgentState 스키마
    - config/settings.yaml line 155-160 — pipeline 설정
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langgraph.graph import END, StateGraph

from config.loader import get_settings
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 스트리밍 헬퍼
# ---------------------------------------------------------------------------
def _get_writer():
    """LangGraph 스트림 라이터를 안전하게 가져온다.

    LangGraph 컨텍스트 외부(단위 테스트 등)에서 호출 시 no-op 함수를 반환한다.
    """
    try:
        from langgraph.config import get_stream_writer

        return get_stream_writer()
    except Exception:
        return lambda x: None


# ---------------------------------------------------------------------------
# 설정 로드
# ---------------------------------------------------------------------------
_settings = get_settings()
_MAX_RETRIES: int = _settings.max_retries
_MAX_CRITICAL_RETRIES: int = _settings.max_critical_retries
_TIER0_TIMEOUT: int = _settings.tier0_timeout
_TIER1_TIMEOUT: int = _settings.tier1_timeout
_TIER2_TIMEOUT: int = _settings.tier2_timeout
_TIER3_TIMEOUT: int = _settings.tier3_timeout
_TIER4_TIMEOUT: int = _settings.tier4_timeout
_ASYNC_TIMEOUT: int = _settings.async_timeout


async def _with_timeout(
    coro_func: Any, state: AgentState, timeout: int, name: str
) -> dict[str, Any]:
    """노드 함수를 타임아웃으로 감싸서 실행한다.

    Args:
        coro_func: 노드 함수 (state를 인자로 받는 async callable)
        state: AgentState
        timeout: 타임아웃(초)
        name: 노드 이름 (로깅용)

    Returns:
        노드 함수의 반환 dict. 타임아웃 시 빈 dict.
    """
    try:
        return await asyncio.wait_for(coro_func(state), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("[%s] 타임아웃 (%ds)", name, timeout)
        return {}

# ---------------------------------------------------------------------------
# 구현된 에이전트 노드 — 실제 import
# ---------------------------------------------------------------------------
from src.agents.podcast.intent_classifier import IntentClassifierAgent  # noqa: E402
from src.agents.podcast.batch_validator import batch_validator_node  # noqa: E402
from src.agents.podcast.content_analyzer import content_analyzer_node  # noqa: E402
from src.agents.podcast.emotion import emotion_node  # noqa: E402
from src.agents.podcast.learning import learning_node  # noqa: E402
from src.agents.podcast.podcast_reasoning import podcast_reasoning_node  # noqa: E402
from src.agents.podcast.safety import safety_node  # noqa: E402
from src.agents.podcast.script_generator import ScriptGeneratorAgent  # noqa: E402
from src.agents.podcast.script_personalizer import ScriptPersonalizerAgent  # noqa: E402
from src.agents.podcast.visualization import visualization_node  # noqa: E402

# --- TIER 0 (개발자1) ---


async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """Intent Classifier 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = IntentClassifierAgent()
    return await agent.process(state)


# --- TIER 2 팟캐스트모드 (개발자1) ---


async def script_generator_node(state: AgentState) -> dict[str, Any]:
    """Script Generator 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = ScriptGeneratorAgent()
    return await agent.process(state)


async def tier2_podcast_fan_out(state: AgentState) -> dict[str, Any]:
    """
    TIER 2 팟캐스트 병렬 실행: Script Generator + Visualization.

    Script Generator 결과는 필수 (TIER 3으로 전달),
    Visualization은 실패해도 파이프라인에 영향 없음.
    재시도 시 Visualization은 건너뜀 (visual_data가 이미 존재하면 스킵).
    """
    writer = _get_writer()
    if writer:
        writer({"event": "tier2_podcast_start"})

    async def _run_tier2_podcast() -> dict[str, Any]:
        # Script Generator는 항상 실행 (재시도 시에도)
        script_task = asyncio.create_task(script_generator_node(state))

        # Visualization은 이미 생성된 경우 건너뜀 (재시도 시 중복 방지)
        vis_task = None
        if not state.get("visual_data"):
            vis_task = asyncio.create_task(visualization_node(state))

        # Script Generator 결과는 필수 — 예외 시 전파
        script_result = await script_task

        # Visualization 결과는 선택 — 실패 시 무시
        vis_result: dict[str, Any] = {}
        if vis_task is not None:
            try:
                vis_result = await vis_task
            except Exception:
                logger.warning("[TIER 2] Visualization 실패 — 무시하고 계속 진행", exc_info=True)

        return {**script_result, **vis_result}

    try:
        merged = await asyncio.wait_for(_run_tier2_podcast(), timeout=_TIER2_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(
            "[TIER 2] 팟캐스트모드 타임아웃 (%ds) — Script Generator 미완료", _TIER2_TIMEOUT,
        )
        raise

    if writer:
        writer({"event": "tier2_podcast_end"})

    return merged


# --- TIER 4 팟캐스트모드 (개발자1) ---


async def script_personalizer_node(state: AgentState) -> dict[str, Any]:
    """Script Personalizer 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = ScriptPersonalizerAgent()
    return await agent.process(state)


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
    safety_flags = safety_result.get("safety_flags", {})
    required_scripts = safety_flags.get("required_in_script", [])

    crisis_msg = "\n".join(required_scripts) if required_scripts else (
        "지금 힘든 상황이시군요. 전문 상담사와 연결해 드리겠습니다."
    )

    return {
        "safety_flags": safety_flags,
        "risk_level": safety_result.get("risk_level", 4),
        "risk_score": safety_result.get("risk_score", 1.0),
        "final_output": crisis_msg,
    }


# ===================================================================
# TIER 1 Fan-out 함수
# ===================================================================

async def tier1_podcast_fan_out(state: AgentState) -> dict[str, Any]:
    """
    팟캐스트모드 TIER 1: Safety + Emotion + ContentAnalyzer + PodcastReasoning 병렬 실행.

    Safety CRISIS 선점 메커니즘은 대화모드와 동일.

    스트리밍 이벤트:
        tier_start → agent_complete (×4) → tier_end (또는 crisis)
    """
    writer = _get_writer()
    cancel_event = asyncio.Event()
    tier_start = time.monotonic()
    agent_names = ["safety", "emotion", "content_analyzer", "podcast_reasoning"]

    writer({
        "event": "tier_start",
        "tier": 1,
        "mode": "podcast",
        "agents": agent_names,
    })

    tasks = [
        run_with_cancel(safety_node(state), cancel_event, "safety"),
        run_with_cancel(emotion_node(state), cancel_event, "emotion"),
        run_with_cancel(content_analyzer_node(state), cancel_event, "content_analyzer"),
        run_with_cancel(podcast_reasoning_node(state), cancel_event, "podcast_reasoning"),
    ]

    async def _run_tier1_pod() -> dict[str, Any]:
        nonlocal tasks
        merged: dict[str, Any] = {}
        completed_count = 0
        for coro in asyncio.as_completed(tasks):
            name, result = await coro
            completed_count += 1
            elapsed_ms = int((time.monotonic() - tier_start) * 1000)

            if name == "safety" and result.get("safety_flags", {}).get("status") == "crisis":
                cancel_event.set()
                writer({
                    "event": "crisis_detected",
                    "tier": 1,
                    "agent": "safety",
                    "risk_level": result.get("risk_level", 4),
                    "elapsed_ms": elapsed_ms,
                })
                deep_result = await _safety_deep_crisis(result)
                writer({
                    "event": "tier_end",
                    "tier": 1,
                    "mode": "podcast",
                    "status": "crisis",
                    "elapsed_ms": int((time.monotonic() - tier_start) * 1000),
                })
                return {**deep_result, "next_step": "crisis_response"}

            writer({
                "event": "agent_complete",
                "tier": 1,
                "agent": name,
                "elapsed_ms": elapsed_ms,
                "progress": f"{completed_count}/{len(agent_names)}",
            })
            merged.update(result)

        return merged

    try:
        merged = await asyncio.wait_for(_run_tier1_pod(), timeout=_TIER1_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            "[TIER 1] 팟캐스트모드 타임아웃 (%ds) — 부분 결과로 계속 진행", _TIER1_TIMEOUT,
        )
        cancel_event.set()
        merged = {}

    writer({
        "event": "tier_end",
        "tier": 1,
        "mode": "podcast",
        "status": "ok" if "next_step" not in merged else merged.get("next_step", "ok"),
        "elapsed_ms": int((time.monotonic() - tier_start) * 1000),
    })

    return merged


# ===================================================================
# 비동기 후처리 (Fire-and-forget)
# ===================================================================
async def async_post_processing_node(state: AgentState) -> dict[str, Any]:
    """
    비동기 후처리: Learning Agent.

    최종 응답 출력 후 백그라운드에서 실행.
    실패해도 파이프라인에 영향 없음.
    _ASYNC_TIMEOUT 적용.

    Note: 모니터링은 callback + Prometheus + LangSmith가 담당.
    """
    tasks = [
        asyncio.create_task(learning_node(state)),
    ]

    async def _run_async_tasks() -> dict[str, Any]:
        results: dict[str, Any] = {}
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                results.update(result)
            except Exception:
                logger.exception("[ASYNC] 비동기 후처리 태스크 실패 — 무시")
        return results

    try:
        return await asyncio.wait_for(_run_async_tasks(), timeout=_ASYNC_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            "[ASYNC] 비동기 후처리 타임아웃 (%ds) — 부분 결과 반환", _ASYNC_TIMEOUT,
        )
        return {}


# ===================================================================
# 라우터 함수
# ===================================================================
def route_after_tier0(state: AgentState) -> str:
    """TIER 0 이후 라우터 — 팟캐스트 파이프라인으로 진행."""
    return "tier1_podcast"


def route_after_tier1(state: AgentState) -> str:
    """
    TIER 1 이후 라우터: CRISIS 여부 확인.

    Returns:
        "crisis_response" | "tier2"
    """
    if state.get("next_step") == "crisis_response":
        return "crisis_response"
    return "tier2"


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
        iteration_count = state.get("iteration_count", 0)
        if iteration_count < _MAX_CRITICAL_RETRIES:
            logger.warning(
                "[CRITICAL_FAIL] 스크립트 평가 미달 — 재시도 %d/%d",
                iteration_count, _MAX_CRITICAL_RETRIES,
            )
            return "tier2_podcast"
        logger.warning(
            "[CRITICAL_FAIL] 재시도 소진(%d) — 강제 통과",
            _MAX_CRITICAL_RETRIES,
        )
        return "tier4_podcast"

    if verdict == "PASS":
        return "tier4_podcast"

    # FAIL → 재시도
    iteration_count = state.get("iteration_count", 0)
    if iteration_count < _MAX_RETRIES:
        return "tier2_podcast"

    logger.warning("[RETRY] 팟캐스트 최대 재시도(%d) 도달 — 강제 통과", _MAX_RETRIES)
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
def build_podcast_graph() -> StateGraph:
    """
    팟캐스트모드 StateGraph 구축.

    TIER 1(병렬) → TIER 2(Script Generator + Visualization 병렬) → TIER 3(배치 검증) → TIER 4(개인화)
    + CRISIS 선점 + 재시도 루프
    """
    graph = StateGraph(AgentState)

    # --- 노드 등록 ---
    graph.add_node("tier1_podcast", tier1_podcast_fan_out)
    graph.add_node("tier2_podcast", tier2_podcast_fan_out)
    graph.add_node(
        "batch_validator",
        lambda s: _with_timeout(batch_validator_node, s, _TIER3_TIMEOUT, "batch_validator"),
    )
    graph.add_node(
        "script_personalizer",
        lambda s: _with_timeout(script_personalizer_node, s, _TIER4_TIMEOUT, "script_personalizer"),
    )
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

    graph.add_edge("tier2_podcast", "batch_validator")

    graph.add_conditional_edges(
        "batch_validator",
        route_after_tier3_podcast,
        {
            "tier4_podcast": "script_personalizer",
            "tier2_podcast": "increment_iteration",
            "crisis_response": "crisis_response",
        },
    )

    graph.add_edge("increment_iteration", "tier2_podcast")
    graph.add_edge("script_personalizer", "async_post")
    graph.add_edge("async_post", END)
    graph.add_edge("crisis_response", END)

    graph.set_entry_point("tier1_podcast")

    return graph


def build_unified_graph() -> StateGraph:
    """
    통합 진입점: TIER 0 → 팟캐스트 파이프라인.

    사용법:
        graph = build_unified_graph()
        compiled = graph.compile()
        result = await compiled.ainvoke({"user_input": "...", "user_id": "..."})
    """
    graph = StateGraph(AgentState)

    # --- TIER 0: Intent Classifier ---
    graph.add_node("intent_classifier", intent_classifier_node)

    # --- 팟캐스트 노드 ---
    graph.add_node("tier1_podcast", tier1_podcast_fan_out)
    graph.add_node("tier2_podcast", tier2_podcast_fan_out)
    graph.add_node("batch_validator", batch_validator_node)
    graph.add_node("script_personalizer", script_personalizer_node)

    # --- 공용 노드 ---
    graph.add_node("crisis_response", crisis_response_node)
    graph.add_node("async_post", async_post_processing_node)
    graph.add_node("increment_iteration_pod", increment_iteration_node)

    # --- TIER 0 → 팟캐스트 ---
    graph.add_conditional_edges(
        "intent_classifier",
        route_after_tier0,
        {
            "tier1_podcast": "tier1_podcast",
        },
    )

    # === 팟캐스트 엣지 ===
    graph.add_conditional_edges(
        "tier1_podcast",
        route_after_tier1,
        {
            "tier2": "tier2_podcast",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("tier2_podcast", "batch_validator")
    graph.add_conditional_edges(
        "batch_validator",
        route_after_tier3_podcast,
        {
            "tier4_podcast": "script_personalizer",
            "tier2_podcast": "increment_iteration_pod",
            "crisis_response": "crisis_response",
        },
    )
    graph.add_edge("increment_iteration_pod", "tier2_podcast")
    graph.add_edge("script_personalizer", "async_post")

    # === 공용 엣지 ===
    graph.add_edge("async_post", END)
    graph.add_edge("crisis_response", END)

    # --- 진입점 ---
    graph.set_entry_point("intent_classifier")

    return graph


# ===================================================================
# 그래프 컴파일 헬퍼
# ===================================================================
def compile_graph(
    graph_builder: str = "unified",
    *,
    checkpointer: Any = None,
) -> Any:
    """StateGraph를 빌드하고 컴파일한다.

    Args:
        graph_builder: 빌드할 그래프 유형
            "unified" — 통합 그래프 (TIER 0 포함)
            "podcast" — 팟캐스트 전용
        checkpointer: LangGraph 체크포인터 (선택).
            개발용: ``InMemorySaver()``
            프로덕션: ``PostgresSaver.from_conn_string(DB_URI)``

    Returns:
        컴파일된 그래프 (CompiledGraph).

    사용법::

        from langgraph.checkpoint.memory import InMemorySaver

        # 체크포인팅 활성화
        compiled = compile_graph(checkpointer=InMemorySaver())
        result = await compiled.ainvoke(
            state,
            config={
                "configurable": {"thread_id": f"session_{session_id}"},
                "callbacks": [MindLogTelemetryCallback()],
            },
        )

        # 스트리밍 + 체크포인팅
        async for mode, chunk in compiled.astream(
            state,
            config={"configurable": {"thread_id": "sess_001"}},
            stream_mode=["updates", "custom"],
        ):
            if mode == "custom":
                handle_streaming_event(chunk)
            elif mode == "updates":
                handle_state_update(chunk)

        # 상태 이력 조회 (Time-travel 디버깅)
        for state_snapshot in compiled.get_state_history(config):
            logger.debug("state_snapshot: %s", state_snapshot)
    """
    builders = {
        "unified": build_unified_graph,
        "podcast": build_podcast_graph,
    }
    builder_fn = builders.get(graph_builder)
    if builder_fn is None:
        raise ValueError(
            f"Unknown graph builder: {graph_builder!r}. "
            f"Choose from: {list(builders.keys())}"
        )

    graph = builder_fn()
    return graph.compile(checkpointer=checkpointer)

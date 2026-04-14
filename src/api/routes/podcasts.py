"""
팟캐스트 라우터.

사용자의 주제 및 선호도를 받아 팟캐스트 에피소드를 생성하는
LangGraph 파이프라인(팟캐스트 모드)을 호출한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi import Request as HttpRequest
from fastapi.responses import StreamingResponse

# src.api.main import removed from top level to prevent circular import
from src.api.backend_resources import (
    RESOURCE_PODCAST_METADATA,
    RESOURCE_VISUALIZATION,
    TYPE_PODCAST_METADATA,
    TYPE_VISUALIZATION,
)
from src.api.contracts import SaveRequest
from src.api.external_schemas import (
    ErrorResponse,
    PodcastEpisodeData,
    PodcastRequest,
    PodcastResponseMeta,
    SafetyAlertData,
    SlimPodcastResponse,
)
from src.utils.logger import get_agent_logger

logger = get_agent_logger("routes.podcasts")

router = APIRouter()


def _build_episode_data(state: dict[str, Any]) -> PodcastEpisodeData:
    """AgentState에서 PodcastEpisodeData를 구성한다."""
    # Script Personalizer 결과 가져오기 (이미 평탄화된 상태)
    output_str = state.get("final_output", "{}")

    try:
        script_data = json.loads(output_str) if output_str else {}
    except json.JSONDecodeError:
        script_data = {}

    # [보안] PII 정제 — DB 저장 전 script_text 등에서 개인정보 마스킹
    from config.loader import get_settings

    if getattr(get_settings(), "pii_sanitization_enabled", True):
        from src.agents.shared.output_sanitizer import sanitize_dict_values

        script_data = sanitize_dict_values(
            script_data,
            target_keys=["script_text", "episode_title", "key_insights"],
        )

    return PodcastEpisodeData(
        episode_id=script_data.get("episode_id", "ep_fallback"),
        session_id=state.get("session_id", ""),
        episode_title=script_data.get("episode_title", "무제 에피소드"),
        total_duration=script_data.get("total_duration", 0),
        script_text=script_data.get("script_text", ""),
        tts_markers=script_data.get("tts_markers", []),
        key_insights=script_data.get("key_insights", []),
        themes=script_data.get("themes", []),
    )


def _extract_safety_alert(state: dict[str, Any]) -> SafetyAlertData | None:
    """안전 경고 데이터를 구성한다 (필요 시에만 반환).

    Safety Agent 출력 키:
        - status: "safe" | "warning" | "crisis"
        - reasons: list[str] — 위험 사유 목록
        - required_in_script: list[str] — 스크립트에 필수 포함할 안전 메시지
    Note:
        Safety Agent는 "message" / "helpline_info" 키를 직접 생성하지 않는다.
        alert_message는 SAFETY_MESSAGES 상수에서, helpline_info는
        CRISIS_HELPLINES 상수에서 가져온다.
    """
    from src.agents.shared.safety_constants import CRISIS_HELPLINES, SAFETY_MESSAGES

    safety_flags = state.get("safety_flags", {})
    status = safety_flags.get("status", "safe")

    if status in ("warning", "crisis"):
        # alert_message: SAFETY_MESSAGES 상수 사용 (Safety Agent와 동일 소스)
        alert_message = SAFETY_MESSAGES.get(status, "안전 경고가 감지되었습니다.")

        # helpline_info: crisis 시 CRISIS_HELPLINES 상수에서 HelplineInfo 생성
        helpline_info = None
        if status == "crisis":
            from src.api.external_schemas import HelplineInfo

            helpline_info = [
                HelplineInfo(
                    name=h["name"],
                    phone=h["number"],
                    description="24시간 운영",
                )
                for h in CRISIS_HELPLINES
            ]

        return SafetyAlertData(
            status=status,
            alert_message=alert_message,
            helpline_info=helpline_info,
            show_emergency_button=(status == "crisis"),
        )
    return None


async def _save_core_data(
    user_id: str,
    session_id: str,
    episode_data: PodcastEpisodeData,
    final_state: dict[str, Any],
    meta: PodcastResponseMeta,
    trace_id: str,
    correlation_id: str,
    elapsed_ms: int,
) -> None:
    """
    핵심 데이터를 백엔드에 동기 저장 (응답 반환 전 완료).

    저장 순서: (1) 에피소드 메타+세그먼트 → (2) 시각화 메타
    감정 로그는 Emotion Agent가 TIER 1에서 AgentDataPublisher로 이미 저장.
    """
    from src.api.main import backend_client

    if backend_client is None:
        logger.warning("BackendClient가 초기화되지 않아 저장을 건너뜁니다.")
        return

    visual_data_raw = final_state.get("visual_data")

    # (1) 에피소드 메타 + 세그먼트
    # (1) 에피소드 메타 + 스크립트 본문
    try:
        cover_image_url = None
        if visual_data_raw:
            cover_image_url = visual_data_raw.get("image_url") or visual_data_raw.get("cdn_url")

        intent_data = final_state.get("intent", {})
        safety_flags = final_state.get("safety_flags", {})
        validation_result = final_state.get("validation_result", {})

        episode_request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_PODCAST_METADATA,
            data={
                "episode_id": episode_data.episode_id,
                "episode_title": episode_data.episode_title,
                "total_duration": episode_data.total_duration,
                "total_words": meta.total_words,
                "script_text": episode_data.script_text,
                "tts_markers_json": json.dumps(
                    [m.model_dump() for m in episode_data.tts_markers]
                    if episode_data.tts_markers
                    else []
                ),
                "key_insights": episode_data.key_insights,
                "themes": episode_data.themes,
                "reasoning_depth": meta.reasoning_depth,
                "cover_image_url": cover_image_url,
                "intent_type": intent_data.get("intent_type", "unknown"),
                "complexity_score": intent_data.get("complexity_score", 0.0),
                "safety_status": safety_flags.get("status", "safe"),
                "validation_score": validation_result.get("overall_score", 0.0),
                "retry_count": final_state.get("iteration_count", 0),
                "pipeline_duration_ms": elapsed_ms,
                "trace_id": trace_id,
                "correlation_id": correlation_id,
                "primary_emotion": final_state.get("emotion_vectors", {}).get(
                    "primary_emotion", "neutral"
                ),
                "secondary_emotions": final_state.get("emotion_vectors", {}).get(
                    "secondary_emotions", []
                )[:2],
            },
            timestamp=datetime.now(timezone.utc),
        )
        results = await asyncio.gather(
            backend_client.save(RESOURCE_PODCAST_METADATA, episode_request),
            backend_client.ingest_podcast_episodes(
                session_id=session_id,
                image_url=cover_image_url or "",
                text=episode_data.script_text,
                title=episode_data.episode_title,
            ),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning("에피소드 저장 작업 %d 실패: %s", i, result)
        logger.info(
            "에피소드 저장 완료 (episode_id=%s, words=%d)",
            episode_data.episode_id,
            meta.total_words,
        )
    except Exception:
        logger.warning("에피소드 저장 실패", exc_info=True)

    # (2) 시각화 메타 (visual_data가 있을 때만)
    # Visualization Agent 출력 키: image_url, interpretation, style_type,
    # original_prompt, resolution, status (flat 구조)
    if visual_data_raw:
        try:
            vis_request = SaveRequest(
                user_id=user_id,
                session_id=session_id,
                type=TYPE_VISUALIZATION,
                data={
                    "visualization_id": f"vis_{uuid.uuid4().hex[:12]}",
                    "mode": "podcast",
                    "episode_id": episode_data.episode_id,
                    "s3_key": visual_data_raw.get("s3_key", ""),
                    "cdn_url": visual_data_raw.get("image_url", ""),
                    "image_prompt": visual_data_raw.get("original_prompt", ""),
                    "interpretation_text": visual_data_raw.get("interpretation", ""),
                    "trace_id": trace_id,
                },
                timestamp=datetime.now(timezone.utc),
            )
            await backend_client.save(RESOURCE_VISUALIZATION, vis_request)
            logger.info("시각화 메타 저장 완료 (episode_id=%s)", episode_data.episode_id)
        except Exception:
            logger.warning("시각화 메타 저장 실패", exc_info=True)


@router.post(
    "/episodes",
    response_model=SlimPodcastResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"},
    },
)
async def create_podcast_episode(
    request: PodcastRequest,
    http_request: HttpRequest,
) -> SlimPodcastResponse:
    """
    팟캐스트 에피소드 생성.

    사용자의 상황·생각·행동·동료반응을 바탕으로 LangGraph 파이프라인(모드=podcast)을 실행하고,
    핵심 데이터를 DB에 저장한 뒤 완료 신호를 반환한다.
    모든 데이터는 DB에 저장되므로 Backend가 GET API로 조회 가능.
    """
    import time

    start_time = time.monotonic()

    # 1. AgentState 구성 — 프론트엔드 4필드를 파이프라인 user_input 형식으로 조합
    parts = [
        f"- 상황: {request.situation}",
        f"- 자신의 생각: {request.thought}",
        f"- 자신의 행동 및 반응: {request.action}",
    ]
    if request.colleague_reaction:
        parts.append(f"- 동료의 반응: {request.colleague_reaction}")
    user_input = "\n".join(parts)

    initial_state: dict[str, Any] = {
        "user_input": user_input,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "mode": "podcast",
        "learning_pattern": request.learning_pattern,
    }

    # 프롬프트 인젝션 패턴 감지 — Safety Agent가 최종 판단
    from src.agents.shared.input_sanitizer import detect_injection

    if detect_injection(user_input):
        logger.warning("[Injection] 패턴 감지: %s", user_input[:50])
        initial_state["safety_flags"] = {"injection_detected": True}

    # 2. 파이프라인(컴파일된 그래프) 실행
    from src.api.main import compiled_graph

    # C-2: TelemetryCallback으로 TIER별 메트릭 수집
    from src.monitoring.callbacks import MindLogTelemetryCallback

    req_id = getattr(http_request.state, "request_id", request.tracing.request_id)
    telemetry_cb = MindLogTelemetryCallback(
        session_id=request.session_id,
        mode="podcast",
        request_id=req_id,
    )

    try:
        if compiled_graph is None:
            raise RuntimeError("LangGraph has not been initialized.")

        final_state = await compiled_graph.ainvoke(
            initial_state,
            config={
                "configurable": {"thread_id": request.session_id},
                "callbacks": [telemetry_cb],
                "metadata": {"request_id": req_id},
            },
        )
    except Exception as e:
        logger.error("[Podcast] 파이프라인 오류", exc_info=True)
        raise e

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # C-2: 방어적 메트릭 기록 (실패해도 API 응답에 영향 없음)
    try:
        from src.monitoring.prometheus import MetricsCollector

        MetricsCollector.record_pipeline(telemetry_cb.get_metrics())
    except Exception:
        logger.warning("Prometheus 메트릭 기록 실패", exc_info=True)

    # 3. 데이터 추출
    episode_data = _build_episode_data(final_state)
    safety_alert = _extract_safety_alert(final_state)

    intent_data = final_state.get("intent", {})
    meta = PodcastResponseMeta(
        pipeline_duration_ms=elapsed_ms,
        intent_type=intent_data.get("intent_type", "unknown"),
        complexity_score=intent_data.get("complexity_score", 0.0),
        reasoning_depth=final_state.get("reasoning_result", {}).get("reasoning_depth", "standard"),
        retry_count=final_state.get("iteration_count", 0),
        total_words=len(episode_data.script_text.split()),
    )

    # 4. 핵심 데이터 동기 저장 (응답 반환 전 완료)
    await _save_core_data(
        user_id=request.user_id,
        session_id=request.session_id,
        episode_data=episode_data,
        final_state=final_state,
        meta=meta,
        trace_id=request.tracing.trace_id,
        correlation_id=request.tracing.correlation_id,
        elapsed_ms=elapsed_ms,
    )

    return SlimPodcastResponse(
        episode_id=episode_data.episode_id,
        session_id=request.session_id,
        safety_alert=safety_alert,
        tracing=request.tracing,
    )


# ---------------------------------------------------------------------------
# SSE 스트리밍 엔드포인트
# ---------------------------------------------------------------------------


def _sse_format(data: dict) -> str:
    """SSE 프로토콜 형식(data: {JSON}\\n\\n)으로 변환한다."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _now_iso() -> str:
    """현재 시각을 ISO 8601 UTC 형식으로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


@router.post("/episodes/stream")
async def stream_podcast_episode(
    request: PodcastRequest, http_request: HttpRequest
) -> StreamingResponse:
    """팟캐스트 에피소드 생성 — SSE 스트리밍.

    TIER별 진행 상황을 실시간으로 전송한다.
    기존 POST /episodes와 동일한 파이프라인을 실행하되,
    ainvoke() 대신 astream()을 사용하여 중간 이벤트를 SSE로 전달한다.

    SSE 이벤트 흐름:
        connected → tier_start → agent_complete → tier_end → result → done
    """
    import time

    from fastapi.responses import StreamingResponse

    start_time = time.monotonic()

    # 1. AgentState 구성 (기존과 동일)
    parts = [
        f"- 상황: {request.situation}",
        f"- 자신의 생각: {request.thought}",
        f"- 자신의 행동 및 반응: {request.action}",
    ]
    if request.colleague_reaction:
        parts.append(f"- 동료의 반응: {request.colleague_reaction}")
    user_input = "\n".join(parts)

    initial_state: dict[str, Any] = {
        "user_input": user_input,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "mode": "podcast",
        "learning_pattern": request.learning_pattern,
    }

    # 프롬프트 인젝션 감지
    from src.agents.shared.input_sanitizer import detect_injection

    if detect_injection(user_input):
        logger.warning("[SSE][Injection] 패턴 감지: %s", user_input[:50])
        initial_state["safety_flags"] = {"injection_detected": True}

    from src.api.main import compiled_graph
    from src.monitoring.callbacks import MindLogTelemetryCallback

    req_id = getattr(http_request.state, "request_id", request.tracing.request_id)
    telemetry_cb = MindLogTelemetryCallback(
        session_id=request.session_id,
        mode="podcast",
        request_id=req_id,
    )

    config = {
        "configurable": {"thread_id": request.session_id},
        "callbacks": [telemetry_cb],
        "metadata": {"request_id": req_id},
    }

    async def event_generator() -> AsyncIterator[str]:
        """SSE 이벤트 생성기 — astream(stream_mode=["updates","custom"])."""
        yield _sse_format(
            {
                "event": "connected",
                "session_id": request.session_id,
                "timestamp": _now_iso(),
            }
        )

        final_state: dict[str, Any] = {}

        try:
            if compiled_graph is None:
                raise RuntimeError("LangGraph has not been initialized.")

            async for mode, chunk in compiled_graph.astream(
                initial_state,
                config=config,
                stream_mode=["updates", "custom"],
            ):
                if mode == "custom":
                    chunk["timestamp"] = _now_iso()
                    yield _sse_format(chunk)
                elif mode == "updates":
                    if isinstance(chunk, dict):
                        for node_output in chunk.values():
                            if isinstance(node_output, dict):
                                final_state.update(node_output)

            # 파이프라인 완료 — 결과 구성
            episode_data = _build_episode_data(final_state)
            safety_alert = _extract_safety_alert(final_state)

            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            meta = PodcastResponseMeta(
                mode="podcast",
                pipeline_duration_ms=elapsed_ms,
                intent_type=final_state.get("intent", {}).get("intent_type", "unknown"),
                complexity_score=float(final_state.get("intent", {}).get("complexity_score", 0.0)),
                reasoning_depth=str(
                    final_state.get("reasoning_result", {}).get("reasoning_depth", "standard")
                ),
                retry_count=int(final_state.get("iteration_count", 0)),
                total_words=len(episode_data.script_text.split()),
            )

            # DB 저장
            await _save_core_data(
                user_id=request.user_id,
                session_id=request.session_id,
                episode_data=episode_data,
                final_state=final_state,
                meta=meta,
                trace_id=request.tracing.trace_id,
                correlation_id=request.tracing.correlation_id,
                elapsed_ms=elapsed_ms,
            )

            result_payload = SlimPodcastResponse(
                episode_id=episode_data.episode_id,
                session_id=request.session_id,
                safety_alert=safety_alert,
                tracing=request.tracing,
            )
            yield _sse_format(
                {
                    "event": "result",
                    "data": result_payload.model_dump(mode="json"),
                    "timestamp": _now_iso(),
                }
            )

        except Exception as e:
            logger.error("[SSE] 파이프라인 오류: %s", e, exc_info=True)
            yield _sse_format(
                {
                    "event": "error",
                    "message": "파이프라인 실행 중 오류가 발생했습니다.",
                    "timestamp": _now_iso(),
                }
            )

        yield _sse_format({"event": "done", "timestamp": _now_iso()})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

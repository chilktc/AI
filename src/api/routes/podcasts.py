"""
팟캐스트 라우터.

사용자의 주제 및 선호도를 받아 팟캐스트 에피소드를 생성하는
LangGraph 파이프라인(팟캐스트 모드)을 호출한다.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks

# src.api.main import removed from top level to prevent circular import
from src.api.backend_resources import (
    RESOURCE_EMOTION_LOG,
    RESOURCE_PODCAST_EPISODE,
    RESOURCE_VISUALIZATION,
    TYPE_EMOTION_LOG,
    TYPE_PODCAST_EPISODE,
    TYPE_VISUALIZATION,
)
from src.api.contracts import SaveRequest
from src.api.external_schemas import (
    PodcastRequest,
    PodcastEpisodeResponse,
    PodcastEpisodeData,
    PodcastSegment,
    EmotionSummary,
    SafetyAlertData,
    VisualizationData,
    PodcastResponseMeta,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_episode_data(state: dict[str, Any]) -> PodcastEpisodeData:
    """AgentState에서 PodcastEpisodeData를 구성한다."""
    # Script Personalizer 결과 가져오기
    output_str = state.get("final_output", "{}")

    try:
        script_data = json.loads(output_str) if output_str else {}
    except json.JSONDecodeError:
        script_data = {}
        
    segments_data = script_data.get("segments", [])
    segments = []
    
    for seg in segments_data:
        segments.append(
            PodcastSegment(
                segment_id=seg.get("segment_id", ""),
                segment_type=seg.get("segment_type", ""),
                duration_minutes=seg.get("duration_minutes", 0),
                script_text=seg.get("script_text", ""),
                word_count=seg.get("word_count", 0),
                emotional_tone=seg.get("emotional_tone", "neutral"),
                tts_markers=seg.get("tts_markers", []),
            )
        )
        
    return PodcastEpisodeData(
        episode_id=script_data.get("episode_id", "ep_fallback"),
        session_id=state.get("session_id", ""),
        episode_title=script_data.get("episode_title", "무제 에피소드"),
        total_duration=script_data.get("total_duration", 0),
        segments=segments,
        key_insights=script_data.get("key_insights", []),
        themes=script_data.get("themes", []),
    )


_EMOTION_EN_TO_KR: dict[str, str] = {
    "joy": "기쁨",
    "happiness": "행복",
    "sadness": "슬픔",
    "anxiety": "불안",
    "anger": "분노",
    "fear": "두려움",
    "surprise": "놀람",
    "disgust": "혐오",
    "frustration": "좌절",
    "disappointment": "실망",
    "loneliness": "외로움",
    "guilt": "죄책감",
    "shame": "수치심",
    "hope": "희망",
    "gratitude": "감사",
    "love": "사랑",
    "calm": "평온",
    "excitement": "흥분",
    "curiosity": "호기심",
    "confusion": "혼란",
    "boredom": "지루함",
    "pride": "자부심",
    "jealousy": "질투",
    "empathy": "공감",
    "nostalgia": "향수",
    "relief": "안도",
    "contentment": "만족",
    "neutral": "중립",
}


def _extract_emotion(state: dict[str, Any]) -> EmotionSummary | None:
    """AgentState에서 EmotionSummary를 구성한다.

    Emotion Agent 출력의 primary_emotion은 영문 키이므로,
    _EMOTION_EN_TO_KR 딕셔너리로 한국어 변환하여 primary_emotion_kr에 설정한다.
    """
    emotion_vectors = state.get("emotion_vectors")
    if not emotion_vectors:
        return None

    primary = emotion_vectors.get("primary_emotion", "neutral")
    primary_kr = _EMOTION_EN_TO_KR.get(primary, primary)

    return EmotionSummary(
        primary_emotion=primary,
        primary_emotion_kr=primary_kr,
        intensity=emotion_vectors.get("intensity", 0.5),
        valence=emotion_vectors.get("valence", 0.0),
        secondary_emotions=emotion_vectors.get("secondary_emotions", []),
        tone_recommendation=emotion_vectors.get("tone_recommendation", "supportive_neutral"),
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


async def _save_episode_bundle(
    user_id: str,
    session_id: str,
    episode_data: PodcastEpisodeData,
    emotion_summary: EmotionSummary | None,
    final_state: dict[str, Any],
    meta: PodcastResponseMeta,
    trace_id: str,
    correlation_id: str,
) -> None:
    """
    에피소드 관련 데이터를 백엔드에 비동기 일괄 저장.

    BackgroundTasks에서 호출되며, 실패해도 HTTP 응답에 영향을 주지 않는다.
    저장 순서: (1) 에피소드 메타+세그먼트 → (2) 감정 로그 → (3) 시각화 메타
    """
    from src.api.main import backend_client

    if backend_client is None:
        logger.warning("BackendClient가 초기화되지 않아 저장을 건너뜁니다.")
        return

    # (1) 에피소드 메타 + 세그먼트
    try:
        segments_data = []
        for idx, seg in enumerate(episode_data.segments):
            segments_data.append({
                "segment_id": seg.segment_id,
                "segment_order": idx,
                "segment_type": seg.segment_type,
                "duration_minutes": seg.duration_minutes,
                "script_text": seg.script_text,
                "word_count": seg.word_count,
                "emotional_tone": seg.emotional_tone,
                "tts_markers_json": json.dumps(
                    [m.model_dump() for m in seg.tts_markers]
                ) if seg.tts_markers else "[]",
            })

        visual_data_raw = final_state.get("visual_data")
        cover_image_url = None
        if visual_data_raw:
            cover_image_url = (
                visual_data_raw.get("image_url")
                or visual_data_raw.get("cdn_url")
            )

        episode_request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_PODCAST_EPISODE,
            data={
                "episode_id": episode_data.episode_id,
                "episode_title": episode_data.episode_title,
                "total_duration": episode_data.total_duration,
                "total_words": meta.total_words,
                "segment_count": len(episode_data.segments),
                "key_insights": episode_data.key_insights,
                "themes": episode_data.themes,
                "reasoning_depth": meta.reasoning_depth,
                "cover_image_url": cover_image_url,
                "trace_id": trace_id,
                "correlation_id": correlation_id,
                "segments": segments_data,
            },
            timestamp=datetime.now(timezone.utc),
        )
        await backend_client.save(RESOURCE_PODCAST_EPISODE, episode_request)
        logger.info(
            "에피소드 저장 완료 (episode_id=%s, segments=%d)",
            episode_data.episode_id,
            len(episode_data.segments),
        )
    except Exception:
        logger.warning("에피소드 저장 실패", exc_info=True)

    # (2) 감정 로그 (emotion_summary가 있을 때만)
    if emotion_summary:
        try:
            emotion_vectors = final_state.get("emotion_vectors", {})
            emotion_request = SaveRequest(
                user_id=user_id,
                session_id=session_id,
                type=TYPE_EMOTION_LOG,
                data={
                    "log_id": f"elog_{uuid.uuid4().hex[:12]}",
                    "mode": "podcast",
                    "episode_id": episode_data.episode_id,
                    "primary_emotion": emotion_summary.primary_emotion,
                    "intensity": emotion_summary.intensity,
                    "valence": emotion_summary.valence,
                    "arousal": emotion_vectors.get("arousal", 0.5),
                    "secondary_emotions": emotion_summary.secondary_emotions,
                    "tone_recommendation": emotion_summary.tone_recommendation,
                    "trace_id": trace_id,
                },
                timestamp=datetime.now(timezone.utc),
            )
            await backend_client.save(RESOURCE_EMOTION_LOG, emotion_request)
            logger.info("감정 로그 저장 완료 (episode_id=%s)", episode_data.episode_id)
        except Exception:
            logger.warning("감정 로그 저장 실패", exc_info=True)

    # (3) 시각화 메타 (visual_data가 있을 때만)
    # Visualization Agent 출력 키: image_url, interpretation, style_type,
    # original_prompt, resolution, status (flat 구조)
    visual_data_raw = final_state.get("visual_data")
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
                    "interpretation_text": visual_data_raw.get(
                        "interpretation", ""
                    ),
                    "primary_emotion": "",
                    "palette": "",
                    "style_tags": [],
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
    response_model=PodcastEpisodeResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"}
    }
)
async def create_podcast_episode(
    request: PodcastRequest,
    background_tasks: BackgroundTasks,
) -> PodcastEpisodeResponse:
    """
    팟캐스트 에피소드 생성.
    
    주제(topic)와 설명(description)을 바탕으로 LangGraph 파이프라인(모드=podcast)을 실행하여
    최종 팟캐스트 스크립트와 메타데이터 응답을 반환한다.
    """
    import time
    start_time = time.monotonic()
    
    # 1. AgentState 구성
    user_input = request.topic
    if request.description:
        user_input += f" - {request.description}"
        
    initial_state = {
        "user_input": user_input,
        "user_id": request.user_id,
        "session_id": request.session_id,
        "mode": "podcast",
    }
    
    # 2. 파이프라인(컴파일된 그래프) 실행
    # compile_graph()가 main 에서 "unified" 로 생성되었음
    from src.api.main import compiled_graph

    # C-2: TelemetryCallback으로 TIER별 메트릭 수집
    from src.monitoring.callbacks import MindLogTelemetryCallback
    telemetry_cb = MindLogTelemetryCallback(
        session_id=request.session_id,
        mode="podcast",
    )

    try:
        if compiled_graph is None:
            raise RuntimeError("LangGraph has not been initialized.")

        final_state = await compiled_graph.ainvoke(
            initial_state,
            config={
                "configurable": {"thread_id": request.session_id},
                "callbacks": [telemetry_cb],
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # C-2: 방어적 메트릭 기록 (실패해도 API 응답에 영향 없음)
    try:
        from src.monitoring.prometheus import MetricsCollector
        MetricsCollector.record_pipeline(telemetry_cb.get_metrics())
    except Exception:
        logger.warning("Prometheus 메트릭 기록 실패", exc_info=True)
    
    # 3. 데이터 추출 및 매핑
    episode_data = _build_episode_data(final_state)
    emotion_summary = _extract_emotion(final_state)
    safety_alert = _extract_safety_alert(final_state)
    
    # visual_data 맵핑 (비동기 생성 중이면 부분값만 있을 수 있음)
    visual_data_raw = final_state.get("visual_data")
    visual_data = None
    if visual_data_raw:
        visual_data = VisualizationData(**visual_data_raw)
        
    # 메타데이터
    intent_data = final_state.get("intent", {})
    
    meta = PodcastResponseMeta(
        pipeline_duration_ms=elapsed_ms,
        intent_type=intent_data.get("intent_type", "unknown"),
        complexity_score=intent_data.get("complexity_score", 0.0),
        reasoning_depth=final_state.get("reasoning_result", {}).get("reasoning_depth", "standard"),
        retry_count=final_state.get("iteration_count", 0),
        total_words=sum(seg.word_count for seg in episode_data.segments),
    )

    # 4. 비동기 저장 스케줄링 (응답 반환 후 BackgroundTasks에서 실행)
    background_tasks.add_task(
        _save_episode_bundle,
        user_id=request.user_id,
        session_id=request.session_id,
        episode_data=episode_data,
        emotion_summary=emotion_summary,
        final_state=final_state,
        meta=meta,
        trace_id=request.tracing.trace_id,
        correlation_id=request.tracing.correlation_id,
    )

    return PodcastEpisodeResponse(
        episode=episode_data,
        emotion=emotion_summary,
        safety_alert=safety_alert,
        cover_image=visual_data,
        metadata=meta,
        tracing=request.tracing,
    )

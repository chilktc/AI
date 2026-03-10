"""
팟캐스트 라우터.

사용자의 주제 및 선호도를 받아 팟캐스트 에피소드를 생성하는
LangGraph 파이프라인(팟캐스트 모드)을 호출한다.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

# src.api.main import removed from top level to prevent circular import
from src.api.external_schemas import (
    PodcastRequest,
    PodcastEpisodeResponse,
    PodcastEpisodeData,
    PodcastSegment,
    EmotionSummary,
    SafetyAlertData,
    VisualizationData,
    PodcastResponseMeta,
    ErrorResponse
)

router = APIRouter()


def _build_episode_data(state: dict[str, Any]) -> PodcastEpisodeData:
    """AgentState에서 PodcastEpisodeData를 구성한다."""
    # Script Personalizer 결과 가져오기
    output_str = state.get("final_output", "{}")
    import json
    
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
        title=script_data.get("episode_title", "무제 에피소드"),
        total_duration_minutes=script_data.get("total_duration", 0),
        segments=segments,
        key_insights=script_data.get("key_insights", []),
        themes=script_data.get("themes", []),
    )


def _extract_emotion(state: dict[str, Any]) -> EmotionSummary | None:
    """AgentState에서 EmotionSummary를 구성한다."""
    emotion_vectors = state.get("emotion_vectors")
    if not emotion_vectors:
        return None
        
    # primary_emotion은 기본 구조 안에 포함된다고 가정. 실제 데이터 구조에 맞게 매핑 수정 가능
    primary = emotion_vectors.get("primary_emotion", "neutral")
    
    return EmotionSummary(
        primary_emotion=primary,
        primary_emotion_kr=primary, # 프론트에서 매핑할 수도 있고, 미리 매핑된 값을 넘길 수도 있음
        intensity=emotion_vectors.get("intensity", 0.5),
        valence=emotion_vectors.get("valence", 0.0),
        secondary_emotions=emotion_vectors.get("secondary_emotions", []),
        tone_recommendation=emotion_vectors.get("tone_recommendation", "supportive_neutral"),
    )


def _extract_safety_alert(state: dict[str, Any]) -> SafetyAlertData | None:
    """안전 경고 데이터를 구성한다 (필요 시에만 반환)"""
    safety_flags = state.get("safety_flags", {})
    status = safety_flags.get("status", "safe")
    
    if status in ("warning", "crisis"):
        return SafetyAlertData(
            status=status,
            alert_message=safety_flags.get("message", "안전 경고가 감지되었습니다."),
            helpline_info=safety_flags.get("helpline_info", []),
            show_emergency_button=(status == "crisis"),
        )
    return None


@router.post(
    "/episodes",
    response_model=PodcastEpisodeResponse,
    responses={
        422: {"model": ErrorResponse, "description": "요청 검증 에러"},
        500: {"model": ErrorResponse, "description": "서버 에러"}
    }
)
async def create_podcast_episode(request: PodcastRequest) -> PodcastEpisodeResponse:
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
    try:
        if compiled_graph is None:
            raise RuntimeError("LangGraph has not been initialized.")
            
        final_state = await compiled_graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": request.session_id}}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e
        
    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    
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
    
    return PodcastEpisodeResponse(
        episode=episode_data,
        emotion=emotion_summary,
        safety_alert=safety_alert,
        cover_image=visual_data,
        metadata=meta,
        tracing=request.tracing,
    )

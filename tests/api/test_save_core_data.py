"""_save_core_data() + ingest_podcast_episodes() 백엔드 정합 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.routes.podcasts import _save_core_data
from src.api.external_schemas import PodcastEpisodeData


def _make_episode_data() -> PodcastEpisodeData:
    """테스트용 PodcastEpisodeData (v3.0 — script_text 기반)."""
    return PodcastEpisodeData(
        episode_id="ep_1", session_id="s1", episode_title="테스트",
        total_duration=5,
        script_text="안녕하세요. 오늘 힘든 하루였죠.",
        tts_markers=[], key_insights=["인사이트"], themes=["스트레스"],
    )


def _make_final_state(**overrides) -> dict:
    base = {
        "emotion_vectors": {
            "primary_emotion": "anxiety",
            "secondary_emotions": ["sadness", "fatigue", "anger"],
        },
        "visual_data": {},
        "validation_result": {"overall_score": 0.9},
        "intent": {}, "iteration_count": 0, "safety_flags": {},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_ingest_sends_text_not_texts():
    """ingest_podcast_episodes()가 text(단일 str)를 전송해야 한다 — texts(list) 아님."""
    mock_bc = AsyncMock()
    mock_bc.save = AsyncMock(return_value=MagicMock(success=True, id="ep_1"))
    mock_bc.ingest_podcast_episodes = AsyncMock()
    meta = MagicMock(); meta.total_words = 8; meta.reasoning_depth = "standard"

    with patch("src.api.main.backend_client", mock_bc):
        await _save_core_data(
            user_id="u1", session_id="s1",
            episode_data=_make_episode_data(), final_state=_make_final_state(),
            meta=meta, trace_id="t1", correlation_id="c1", elapsed_ms=100,
        )

    mock_bc.ingest_podcast_episodes.assert_called_once()
    kwargs = mock_bc.ingest_podcast_episodes.call_args.kwargs
    assert kwargs["text"] == "안녕하세요. 오늘 힘든 하루였죠.", "text=script_text 전달 필수"
    assert kwargs["title"] == "테스트", "title=episode_title 전달 필수"
    assert "texts" not in kwargs, "구 파라미터 texts 제거 필수"
    assert "summary" not in kwargs, "구 파라미터 summary 제거 필수"
    assert "keywords" not in kwargs, "구 파라미터 keywords 제거 필수"


@pytest.mark.asyncio
async def test_save_core_data_stores_emotion_columns():
    """podcast_metadata에 감정 컬럼(primary_emotion, secondary_emotions)이 포함되어야 한다."""
    mock_bc = AsyncMock()
    mock_bc.save = AsyncMock(return_value=MagicMock(success=True, id="ep_1"))
    mock_bc.ingest_podcast_episodes = AsyncMock()
    meta = MagicMock(); meta.total_words = 8; meta.reasoning_depth = "standard"

    with patch("src.api.main.backend_client", mock_bc):
        await _save_core_data(
            user_id="u1", session_id="s1",
            episode_data=_make_episode_data(), final_state=_make_final_state(),
            meta=meta, trace_id="t1", correlation_id="c1", elapsed_ms=100,
        )

    save_call = mock_bc.save.call_args
    request_obj = save_call.args[1] if len(save_call.args) > 1 else save_call.kwargs.get("request")
    data = request_obj.data
    assert data["primary_emotion"] == "anxiety"
    assert data["secondary_emotions"] == ["sadness", "fatigue"], "[0:2] 슬라이싱 확인"

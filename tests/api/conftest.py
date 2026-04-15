"""
API 엔드포인트 테스트 전용 Fixture.

compiled_graph와 backend_client를 mock으로 주입하여
LangGraph 파이프라인이나 실제 백엔드 서버 없이 엔드포인트 로직만 격리 테스트.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock: compiled_graph (LangGraph)
# ---------------------------------------------------------------------------


def _make_default_pipeline_result() -> dict[str, Any]:
    """기본 파이프라인 실행 결과 (podcast 모드)."""
    return {
        "final_output": json.dumps(
            {
                "episode_id": "ep_test001",
                "episode_title": "테스트 에피소드",
                "total_duration": 3,
                "segments": [
                    {
                        "segment_id": "seg_01",
                        "segment_type": "intro",
                        "duration_minutes": 1,
                        "script_text": "안녕하세요, 테스트 에피소드입니다.",
                        "word_count": 10,
                        "emotional_tone": "warm",
                        "tts_markers": [],
                    }
                ],
                "key_insights": ["테스트 인사이트"],
                "themes": ["테스트"],
            }
        ),
        "emotion_vectors": {
            "primary_emotion": "calm",
            "intensity": 0.6,
            "valence": 0.3,
            "secondary_emotions": ["hope"],
            "tone_recommendation": "supportive_neutral",
        },
        "safety_flags": {"status": "safe"},
        "visual_data": None,
        "intent": {
            "intent_type": "topic_exploration",
            "complexity_score": 0.5,
        },
        "reasoning_result": {"reasoning_depth": "standard"},
        "iteration_count": 0,
        "session_id": "sess_test123",
    }


@pytest.fixture
def mock_compiled_graph():
    """compiled_graph를 mock하여 실제 LangGraph 없이 테스트."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=_make_default_pipeline_result())
    return mock


@pytest.fixture
def mock_backend_client():
    """BackendClient mock."""
    mock = AsyncMock()
    mock.close = AsyncMock()
    mock._base_url = "http://mock-backend:8080/api"
    return mock


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def test_client(mock_compiled_graph, mock_backend_client):
    """FastAPI TestClient (동기). compiled_graph와 backend_client를 mock 주입."""
    with (
        patch("src.api.main.compiled_graph", mock_compiled_graph),
        patch("src.api.main.backend_client", mock_backend_client),
        patch("src.api.routes.health.compiled_graph", mock_compiled_graph, create=True),
        patch("src.api.routes.health.backend_client", mock_backend_client, create=True),
    ):
        from fastapi.testclient import TestClient

        from src.api.main import app

        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def test_client_not_ready():
    """compiled_graph=None 상태의 TestClient (not_ready 시나리오)."""
    with (
        patch("src.api.main.compiled_graph", None),
        patch("src.api.main.backend_client", None),
    ):
        from fastapi.testclient import TestClient

        from src.api.main import app

        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# 도우미 함수
# ---------------------------------------------------------------------------


def make_pipeline_result(**overrides: Any) -> dict[str, Any]:
    """파이프라인 결과를 커스터마이즈할 수 있는 팩토리 함수."""
    result = _make_default_pipeline_result()
    result.update(overrides)
    return result


def make_crisis_pipeline_result(**overrides: Any) -> dict[str, Any]:
    """CRISIS 판정 시 파이프라인이 반환하는 state 구조 (신규 아키텍처).

    TIER 1 완료 후 TIER 2~4가 CRISIS 폴백으로 실행된 결과:
    - final_output: 유효한 JSON (PersonalizedScript, ep_crisis_ prefix)
    - safety_flags.status: "crisis"
    - visual_data.image_url: non-empty placeholder URL
    - validation_result.verdict: "PASS" (auto-pass)
    """
    import uuid as _uuid

    from src.agents.shared.safety_constants import (
        CRISIS_FALLBACK_VALUES,
        SAFETY_MESSAGES,
    )
    from src.models.schemas import PersonalizationMeta, PersonalizedScript

    crisis_episode_id = f"ep_crisis_{_uuid.uuid4().hex[:12]}"
    crisis_script = PersonalizedScript(
        episode_id=crisis_episode_id,
        episode_title="마음 돌봄 안내",
        total_duration=0,
        script_text=SAFETY_MESSAGES["crisis"],
        tts_markers=[],
        key_insights=[],
        themes=[],
        personalization_meta=PersonalizationMeta(attitude_applied="crisis"),
    )

    result: dict[str, Any] = {
        "final_output": crisis_script.model_dump_json(),
        "safety_flags": {
            "status": "crisis",
            "risk_level": 4,
            "risk_score": 0.95,
            "required_in_script": [SAFETY_MESSAGES["crisis"]],
        },
        "risk_level": 4,
        "risk_score": 0.95,
        "next_step": "tier2",
        "script_draft": CRISIS_FALLBACK_VALUES["script_draft"],
        "visual_data": CRISIS_FALLBACK_VALUES["visual_data"],
        "validation_result": CRISIS_FALLBACK_VALUES["validation_result"],
        "intent": {"intent_type": "unknown", "complexity_score": 0.0},
        "session_id": "sess_test123",
    }
    result.update(overrides)
    return result

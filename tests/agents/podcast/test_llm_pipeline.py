"""
전체 팟캐스트 파이프라인 LLM 실제 호출 테스트.

TIER 0 → 1 → 2 → 3 순으로 에이전트를 순차 실행하여
AgentState가 올바르게 누적·전달되는지 검증한다.

Visualization(Bedrock/S3 필요)은 SKIP_VISUALIZATION=true로 우회.
외부 의존성(AgentDataPublisher, BackendClient)은 mock 처리.

마커 안내:
  @pytest.mark.live  — Ollama 실제 호출 (기본 실행 제외)
  @pytest.mark.slow  — 전체 체인 테스트 (3~5분 소요, -m "live and not slow" 로 제외 가능)

실행 예시:
  pytest tests/agents/podcast/test_llm_pipeline.py -m "live and not slow"  # 빠른 검증
  pytest tests/agents/podcast/test_llm_pipeline.py -m "live"               # 전체 포함
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.podcast.batch_validator import BatchValidatorAgent
from src.agents.podcast.content_analyzer import ContentAnalyzerAgent
from src.agents.podcast.emotion import EmotionAgent
from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
from src.agents.podcast.safety import SafetyAgent
from src.agents.podcast.script_generator import ScriptGeneratorAgent
from src.agents.podcast.visualization import VisualizationAgent
from src.models.agent_state import AgentState


# =============================================================================
# 전체 파이프라인 live 테스트
# =============================================================================


@pytest.mark.live
class TestPodcastPipelineWithLLM:
    """TIER 1~3 에이전트를 체이닝하여 전체 파이프라인을 검증한다."""

    @pytest.fixture
    def llm(self, llm_client):
        if llm_client is None:
            pytest.skip("LLM client not available")
        return llm_client

    # ------------------------------------------------------------------
    # TIER 1 — 병렬 에이전트를 순차적으로 실행 (테스트 단순화)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tier1_safety_and_emotion(self, llm) -> None:
        """TIER 1 Safety + Emotion이 올바른 출력을 누적한다."""
        state = AgentState(
            user_input="요즘 많이 지치고 힘들어요.",
            user_id="u",
            session_id="s",
            mode="podcast",
        )

        safety = SafetyAgent()
        safety.llm_client = llm
        emotion = EmotionAgent()
        emotion.llm_client = llm

        t0 = time.time()
        with patch("src.agents.podcast.emotion.AgentDataPublisher") as pub:
            pub.return_value.publish = AsyncMock(return_value=True)
            safety_out = await safety.process(state)
            state = {**state, **safety_out}
            emotion_out = await emotion.process(state)
            state = {**state, **emotion_out}
        elapsed = time.time() - t0

        print(f"\n[Pipeline TIER1 S+E] ⏱️ {elapsed:.2f}초")
        print(f"  safety={state.get('safety_flags', {}).get('status')}")
        print(f"  emotion={state.get('emotion_vectors', {}).get('primary_emotion')}")

        assert "safety_flags" in state
        assert state["safety_flags"]["status"] in {"safe", "warning", "crisis"}
        assert "emotion_vectors" in state
        assert isinstance(state["emotion_vectors"].get("primary_emotion"), str)

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_pipeline_tier1_to_tier3(self, llm) -> None:
        """TIER 1~3 전체 체인: safety → emotion → content → reasoning → script → validator.

        예상 소요: ~3~5분 (LLM 6회 직렬 호출). -m "live and not slow" 로 제외 가능.
        """
        state = AgentState(
            user_input="직장 스트레스로 번아웃이 왔어요. 무기력하고 잠도 못 자고 있어요.",
            user_id="test_pipeline_user",
            session_id="test_pipeline_session",
            mode="podcast",
        )
        timings: dict[str, float] = {}

        # --- TIER 1: Safety ---
        safety = SafetyAgent()
        safety.llm_client = llm
        t = time.time()
        out = await safety.process(state)
        timings["safety"] = time.time() - t
        state = {**state, **out}

        # 위기 상황이면 파이프라인 조기 종료
        if state.get("safety_flags", {}).get("status") == "crisis":
            print(f"\n[Pipeline] CRISIS 감지 → 조기 종료 (safety: {timings['safety']:.2f}초)")
            pytest.skip("CRISIS 판정 — 파이프라인 나머지 테스트 스킵")

        # --- TIER 1: Emotion ---
        emotion = EmotionAgent()
        emotion.llm_client = llm
        t = time.time()
        with patch("src.agents.podcast.emotion.AgentDataPublisher") as pub:
            pub.return_value.publish = AsyncMock(return_value=True)
            out = await emotion.process(state)
        timings["emotion"] = time.time() - t
        state = {**state, **out}

        # --- TIER 1: Content Analyzer ---
        content = ContentAnalyzerAgent()
        content.llm_client = llm
        t = time.time()
        with patch("src.agents.podcast.content_analyzer.AgentDataPublisher") as pub:
            pub.return_value.publish = AsyncMock(return_value=True)
            with patch("src.agents.podcast.content_analyzer.BackendClient") as mock_bc:
                mock_bc.return_value.ingest_mind_frequencies = AsyncMock()
                mock_bc.return_value.close = AsyncMock()
                out = await content.process(state)
        timings["content"] = time.time() - t
        state = {**state, **out}

        # --- TIER 1: Podcast Reasoning ---
        reasoning = PodcastReasoningAgent()
        reasoning.llm_client = llm
        t = time.time()
        out = await reasoning.process(state)
        timings["reasoning"] = time.time() - t
        state = {**state, **out}

        # --- TIER 2: Script Generator ---
        script_gen = ScriptGeneratorAgent()
        script_gen.llm_client = llm
        t = time.time()
        out = await script_gen.process(state)
        timings["script_gen"] = time.time() - t
        state = {**state, **out}

        # --- TIER 2: Visualization (SKIP_VISUALIZATION=true) ---
        t = time.time()
        with patch.dict(os.environ, {"SKIP_VISUALIZATION": "true"}):
            viz = VisualizationAgent()
            viz.llm_client = llm
            out = await viz.process(state)
        timings["viz"] = time.time() - t
        state = {**state, **out}

        # --- TIER 3: Batch Validator ---
        validator = BatchValidatorAgent()
        validator.llm_client = llm
        t = time.time()
        out = await validator.process(state)
        timings["validator"] = time.time() - t
        state = {**state, **out}

        total = sum(timings.values())
        print(f"\n[Pipeline TIER1-3] 총 ⏱️ {total:.2f}초")
        for name, t_val in timings.items():
            print(f"  {name}: {t_val:.2f}초")

        # 최종 상태 검증
        assert "safety_flags" in state
        assert "emotion_vectors" in state
        assert "content_analysis" in state
        assert "reasoning_result" in state
        assert "script_draft" in state
        assert "visual_data" in state
        assert "validation_result" in state

        vr = state["validation_result"]
        assert vr.get("verdict") in {"PASS", "FAIL", "CRITICAL_FAIL"}
        assert "action" in vr

        sd = state["script_draft"]
        # SG-2: top-level error 키 없음
        assert "error" not in state, "top-level 'error' 키는 AgentState 미정의"
        if "_error" not in sd:
            assert "episode_title" in sd or "segments" in sd

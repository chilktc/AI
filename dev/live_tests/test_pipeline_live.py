"""
파이프라인 시뮬레이션 라이브 테스트.

LangGraph 없이 수동으로 에이전트를 체이닝하여
TIER 1 → TIER 2(mock) → TIER 3 → 비동기 흐름을 검증한다.

Script Generator는 개발자1 담당이며 아직 구현되지 않았으므로
generate_mock_script()로 시뮬레이션한다 (fixtures.py 참조).

사용법:
    python3 -m dev.live_tests.run_live --pipeline
    python3 -m dev.live_tests.run_live --pipeline --provider anthropic
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from dev.live_tests.conftest_live import (
    Timer,
    check_provider_health,
    print_banner,
    print_error,
    print_result,
    print_section,
    setup_provider,
)
from dev.live_tests.fixtures import generate_mock_script, make_pipeline_initial_state


async def run_test(
    provider: str = "ollama",
    model_override: str | None = None,
) -> dict[str, Any] | None:
    """
    파이프라인 시뮬레이션을 실행한다.

    Step 1: TIER 1 — Content Analyzer + Podcast Reasoning (순차 실행)
    Step 2: Mock Script Generator (TIER 2 — 개발자1 미구현)
    Step 3: TIER 3 — Batch Validator
    Step 4: 비동기 — Learning Agent (BackendClient mock)

    각 단계별 결과를 출력하고, 상태 필드 전파를 확인한다.

    Args:
        provider: LLM 프로바이더 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (선택)

    Returns:
        최종 상태 dict 또는 실패 시 None
    """
    print_banner(f"파이프라인 시뮬레이션 ({provider})")

    # 1. 프로바이더 셋업
    print_section("프로바이더 셋업")
    setup_provider(provider, model_override)

    # 2. 헬스체크
    print_section("프로바이더 헬스체크")
    healthy = await check_provider_health(provider)
    if not healthy:
        print("  헬스체크 실패 — 테스트를 건너뜁니다.")
        return None

    try:
        # import를 여기서 하는 이유: setup_provider가 먼저 환경을 설정해야 함
        from src.agents.podcast.batch_validator import BatchValidatorAgent
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        from src.agents.shared.learning import LearningAgent
        from src.api.client import BackendClient

        # 초기 상태 생성
        state: dict[str, Any] = make_pipeline_initial_state()
        print_section("초기 상태")
        print(f"  user_input: {state['user_input'][:60]}...")
        print(f"  intent.category: {state['intent'].get('category', 'N/A')}")
        print(f"  complexity_score: {state['intent'].get('complexity_score', 'N/A')}")

        # ════════════════════════════════════════
        # Step 1: TIER 1 — Content Analyzer
        # ════════════════════════════════════════
        print_banner("Step 1-A: TIER 1 — Content Analyzer", color="cyan")
        content_analyzer = ContentAnalyzerAgent()

        with Timer() as t1a:
            ca_result = await content_analyzer(state)
        state.update(ca_result)
        print_result("content_analyzer", provider, ca_result, t1a.elapsed)

        # content_analysis 필드 확인
        _check_field(state, "content_analysis", ["main_theme", "sub_themes", "episode_type"])

        # ════════════════════════════════════════
        # Step 1: TIER 1 — Podcast Reasoning
        # ════════════════════════════════════════
        print_banner("Step 1-B: TIER 1 — Podcast Reasoning", color="cyan")
        podcast_reasoning = PodcastReasoningAgent()

        with Timer() as t1b:
            pr_result = await podcast_reasoning(state)
        state.update(pr_result)
        print_result("podcast_reasoning", provider, pr_result, t1b.elapsed)

        # reasoning_result 필드 확인
        _check_field(
            state, "reasoning_result", ["episode_structure", "narrative_flow", "key_points"]
        )

        # ════════════════════════════════════════
        # Step 2: TIER 2 — Mock Script Generator
        # ════════════════════════════════════════
        print_banner("Step 2: TIER 2 — Mock Script Generator (개발자1 미구현)", color="yellow")
        print("  Script Generator는 개발자1 담당이며 아직 구현되지 않았다.")
        print("  generate_mock_script()로 시뮬레이션한다.")
        print("  Content Analyzer와 Podcast Reasoning의 출력을 참조하여")
        print("  현실적인 script_draft 구조를 생성한다.")

        mock_script = generate_mock_script(state)
        state["script_draft"] = mock_script

        print(f"\n  mock script_draft.title: {mock_script.get('title', 'N/A')}")
        print(f"  mock script_draft.total_duration: {mock_script.get('total_duration', 'N/A')}초")
        print(f"  mock script_draft.segments: {len(mock_script.get('segments', []))}개")

        # Safety/Emotion mock (개발자2 미구현 — TIER 1 공용 에이전트)
        if "safety_flags" not in state:
            state["safety_flags"] = {
                "risk_level": "safe",
                "crisis_detected": False,
                "content_warnings": [],
            }
        if "emotion_vectors" not in state:
            state["emotion_vectors"] = {
                "primary_emotion": "neutral",
                "secondary_emotion": "hope",
                "intensity": 0.4,
                "valence": 0.1,
            }
        state["iteration_count"] = 0
        print("  Safety/Emotion mock 데이터 주입 완료")

        # ════════════════════════════════════════
        # Step 3: TIER 3 — Batch Validator
        # ════════════════════════════════════════
        print_banner("Step 3: TIER 3 — Batch Validator", color="cyan")
        batch_validator = BatchValidatorAgent()

        with Timer() as t3:
            bv_result = await batch_validator(state)
        state.update(bv_result)
        print_result("batch_validator", provider, bv_result, t3.elapsed)

        # 라우팅 결정 확인
        next_step = bv_result.get("next_step", "unknown")
        passed = bv_result.get("validation_result", {}).get("passed", False)
        print(f"  검증 통과: {passed}")
        print(f"  next_step: {next_step}")

        # ════════════════════════════════════════
        # Step 4: 비동기 — Learning Agent
        # ════════════════════════════════════════
        print_banner("Step 4: 비동기 — Learning Agent", color="cyan")

        # Learning Agent에 필요한 final_output 추가 (Script Personalizer 시뮬레이션)
        if "final_output" not in state:
            state["final_output"] = (
                f"{mock_script.get('title', '에피소드')} — "
                "오늘은 멘탈케어에 대해 이야기합니다..."
            )

        mock_response = {"success": True, "id": "pipeline-test-001", "message": "saved"}
        with patch.object(
            BackendClient, "save", new_callable=AsyncMock, return_value=mock_response
        ) as mock_save:
            learning = LearningAgent()

            with Timer() as t4:
                la_result = await learning(state)
            state.update(la_result)
            print_result("learning", provider, la_result, t4.elapsed)

            if mock_save.called:
                print(f"  [OK] BackendClient.save() 호출됨 ({mock_save.call_count}회)")
            else:
                print("  [WARN] BackendClient.save() 호출되지 않음")

        # ════════════════════════════════════════
        # 전체 요약
        # ════════════════════════════════════════
        _print_pipeline_summary(t1a, t1b, t3, t4, state)

        return state

    except Exception as e:
        print_error("pipeline", e)
        return None


def _check_field(state: dict[str, Any], field_name: str, sub_fields: list[str]) -> None:
    """상태에서 필드 존재와 하위 필드를 확인한다."""
    field = state.get(field_name, {})
    if not field:
        print(f"  [WARN] {field_name} 필드가 비어있음")
        return

    present = [sf for sf in sub_fields if sf in field]
    missing = [sf for sf in sub_fields if sf not in field]
    print(f"  {field_name}: 하위 필드 {len(present)}/{len(sub_fields)}개 존재")
    if missing:
        print(f"  누락: {missing}")


def _print_pipeline_summary(
    t1a: Timer,
    t1b: Timer,
    t3: Timer,
    t4: Timer,
    state: dict[str, Any],
) -> None:
    """파이프라인 전체 요약을 출력한다."""
    print_banner("파이프라인 요약", color="green")

    total_time = t1a.elapsed + t1b.elapsed + t3.elapsed + t4.elapsed
    print(f"  총 소요 시간: {total_time:.2f}초")
    print(f"    TIER 1 Content Analyzer: {t1a.elapsed:.2f}초")
    print(f"    TIER 1 Podcast Reasoning: {t1b.elapsed:.2f}초")
    print("    TIER 2 Script Generator: (mock — 0초)")
    print(f"    TIER 3 Batch Validator: {t3.elapsed:.2f}초")
    print(f"    비동기 Learning Agent: {t4.elapsed:.2f}초")

    # 상태 필드 전파 확인
    print_section("상태 필드 전파 확인")
    key_fields = [
        "content_analysis",
        "reasoning_result",
        "script_draft",
        "safety_flags",
        "emotion_vectors",
        "validation_result",
        "next_step",
    ]
    for field in key_fields:
        if field in state:
            value = state[field]
            if isinstance(value, dict):
                print(f"  [OK] {field}: {{{len(value)}개 키}}")
            elif isinstance(value, str) and len(value) > 50:
                print(f"  [OK] {field}: {value[:50]}...")
            else:
                print(f"  [OK] {field}: {value}")
        else:
            print(f"  [MISSING] {field}")


if __name__ == "__main__":
    asyncio.run(run_test())

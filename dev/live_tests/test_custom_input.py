"""
커스텀 입력 라이브 테스트 — 사용자 제공 텍스트로 구현된 에이전트 검증.

구현 완료된 4개 에이전트를 순차 + 파이프라인으로 실행:
1. Content Analyzer (TIER 1) — 개별 테스트
2. Podcast Reasoning (TIER 1) — 개별 테스트
3. Batch Validator (TIER 3) — 개별 테스트
4. Learning Agent (비동기) — 개별 테스트
5. 파이프라인 시뮬레이션 (TIER 1 → Mock TIER 2 → TIER 3 → 비동기)

사용법:
    cd /Users/kttechup/Documents/NewProject/mind-log
    python3 -m dev.live_tests.test_custom_input
"""

from __future__ import annotations

import asyncio
import json
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
from dev.live_tests.fixtures import generate_mock_script

# ════════════════════════════════════════
# 사용자 입력 텍스트
# ════════════════════════════════════════
USER_INPUT = (
    "아니 오늘 친하게 지내던 후배가 내 뒷담을 하는 걸 들었어. "
    "내가 과장 진급하고 위에서 하도 성과를 가지고 압박하길래 나도 나름대로 할 수 있을 수준으로 힘들게 네고하고, "
    "후배한테도 최대한 좋게 전달하려고 했던 건데 이렇게 뒷담을 들어야 한다는게 너무 짜증난다. "
    "나도 나름대로 중간에서 조율을 하고 내가 할 일을 하는 건데, "
    "그거가지고 친하게 지내던 후배가 뒷담을 하는게 너무 실망이고 오히려 그러니까 나도 그냥 차갑게 대하고 싶어. "
    "근데 그래봤자 나만 겉돌게 되는건 아닌지 무섭기도 하고… "
    "그렇다고 상사랑 친하게 지내기도 어려운게 진짜 내 상사는 진짜 말이 안 통함. "
    "아직은 그냥 모른척 내가 하던대로 하고 있어. "
    "그런데 후배를 마주치면 나도 모르게 얼굴이 굳고 좀 거리감이 느껴져서 괜히 툭 툭 내뱉듯이 말을 하게 되는 거 같아. "
    "후배는 내가 뒷담화 들은 걸 모르니까 그냥 아직까지는 자연스럽게 대하려고 하는거 같아. "
    "내가 업무 지시를 해도 그냥 웃으면서 잘 받고. 근데 그 뒤에 불만이 가득 쌓인거지. 차라리 말을 하던지."
)


def make_custom_state() -> dict[str, Any]:
    """사용자 입력으로 TIER 1 에이전트용 초기 상태를 생성한다."""
    return {
        "user_input": USER_INPUT,
        "user_id": "user_custom_test_001",
        "session_id": "sess_custom_test_001",
        "mode": "podcast",
        "intent": {
            "mode": "podcast",
            "category": "interpersonal_conflict",
            "complexity_score": 0.7,
            "topic_hint": "직장 내 뒷담화와 중간관리자의 갈등",
            "risk_flag": False,
        },
    }


def make_custom_batch_state(
    content_analysis: dict[str, Any],
    reasoning_result: dict[str, Any],
    script_draft: dict[str, Any],
) -> dict[str, Any]:
    """파이프라인에서 Batch Validator용 상태를 조합한다."""
    state = make_custom_state()
    state["content_analysis"] = content_analysis
    state["reasoning_result"] = reasoning_result
    state["script_draft"] = script_draft
    state["safety_flags"] = {
        "risk_level": "safe",
        "crisis_detected": False,
        "content_warnings": [],
    }
    state["emotion_vectors"] = {
        "primary_emotion": "anger",
        "secondary_emotion": "disappointment",
        "intensity": 0.7,
        "valence": -0.5,
    }
    state["iteration_count"] = 0
    return state


# ════════════════════════════════════════
# 개별 에이전트 테스트
# ════════════════════════════════════════


async def test_content_analyzer(provider: str) -> dict[str, Any] | None:
    """Content Analyzer 개별 테스트."""
    print_banner("1. Content Analyzer 테스트", color="cyan")
    try:
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        state = make_custom_state()

        print(f"  입력 텍스트 길이: {len(state['user_input'])}자")
        print(f"  complexity_score: {state['intent']['complexity_score']}")

        with Timer() as timer:
            result = await agent(state)

        print_result("ContentAnalyzer", provider, result, timer.elapsed)

        # 필드 검증
        ca = result.get("content_analysis", {})
        expected = ["main_theme", "sub_themes", "episode_type", "depth_level"]
        for field in expected:
            status = "[OK]" if field in ca else "[MISSING]"
            val = ca.get(field, "N/A")
            if isinstance(val, list):
                val = f"[{len(val)}개 항목]"
            print(f"  {status} {field}: {val}")

        return result
    except Exception as e:
        print_error("ContentAnalyzer", e)
        return None


async def test_podcast_reasoning(provider: str) -> dict[str, Any] | None:
    """Podcast Reasoning 개별 테스트."""
    print_banner("2. Podcast Reasoning 테스트", color="cyan")
    try:
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()
        state = make_custom_state()

        complexity = state["intent"]["complexity_score"]
        if complexity >= 0.8:
            depth = "full (GoT+ToT+CoT)"
        elif complexity >= 0.5:
            depth = "standard (ToT+CoT)"
        else:
            depth = "minimal (CoT)"

        print(f"  입력 텍스트 길이: {len(state['user_input'])}자")
        print(f"  complexity_score: {complexity}")
        print(f"  예상 추론 깊이: {depth}")

        with Timer() as timer:
            result = await agent(state)

        print_result("PodcastReasoning", provider, result, timer.elapsed)

        # 필드 검증
        rr = result.get("reasoning_result", {})
        expected = [
            "episode_structure",
            "narrative_flow",
            "key_points",
            "emotional_journey",
            "confidence",
            "reasoning_strategy",
        ]
        for field in expected:
            status = "[OK]" if field in rr else "[MISSING]"
            val = rr.get(field, "N/A")
            if isinstance(val, list):
                val = f"[{len(val)}개 항목]"
            elif isinstance(val, dict):
                val = f"{{{len(val)}개 키}}"
            print(f"  {status} {field}: {val}")

        return result
    except Exception as e:
        print_error("PodcastReasoning", e)
        return None


async def test_batch_validator(
    provider: str,
    content_analysis: dict[str, Any],
    reasoning_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Batch Validator 개별 테스트 (앞단 결과 필요)."""
    print_banner("3. Batch Validator 테스트", color="cyan")
    try:
        from src.agents.podcast.batch_validator import BatchValidatorAgent

        # Mock script 생성
        temp_state = make_custom_state()
        temp_state["content_analysis"] = content_analysis
        temp_state["reasoning_result"] = reasoning_result
        script_draft = generate_mock_script(temp_state)

        state = make_custom_batch_state(content_analysis, reasoning_result, script_draft)

        print(f"  script_draft.title: {script_draft.get('title', 'N/A')}")
        print(f"  script_draft.segments: {len(script_draft.get('segments', []))}개")
        print(f"  script_draft.total_duration: {script_draft.get('total_duration', 'N/A')}초")

        agent = BatchValidatorAgent()

        with Timer() as timer:
            result = await agent(state)

        print_result("BatchValidator", provider, result, timer.elapsed)

        # 결과 분석
        vr = result.get("validation_result", {})
        passed = vr.get("passed", False)
        score = vr.get("overall_score", "N/A")
        next_step = result.get("next_step", "unknown")

        print(f"  검증 통과: {passed}")
        print(f"  overall_score: {score}")
        print(f"  next_step: {next_step}")

        checks = vr.get("checks", {})
        if checks:
            print_section("검증 항목 상세")
            for name, detail in checks.items():
                if isinstance(detail, dict):
                    s = "PASS" if detail.get("passed", False) else "FAIL"
                    print(f"    [{s}] {name}: score={detail.get('score', 'N/A')}")

        return result
    except Exception as e:
        print_error("BatchValidator", e)
        return None


async def test_learning(
    provider: str,
    full_state: dict[str, Any],
) -> dict[str, Any] | None:
    """Learning Agent 개별 테스트 (BackendClient mock)."""
    print_banner("4. Learning Agent 테스트", color="cyan")
    try:
        from src.agents.shared.learning import LearningAgent
        from src.api.client import BackendClient

        # final_output 추가 (Script Personalizer 미구현)
        if "final_output" not in full_state:
            full_state["final_output"] = (
                "직장 내 뒷담화와 중간관리자의 갈등 — "
                "오늘은 직장에서 신뢰가 무너진 순간, 어떻게 대처할 수 있는지 이야기합니다..."
            )

        mock_response = {"success": True, "id": "custom-test-001", "message": "saved"}

        with patch.object(
            BackendClient, "save", new_callable=AsyncMock, return_value=mock_response
        ) as mock_save:
            agent = LearningAgent()

            with Timer() as timer:
                result = await agent(full_state)

            print_result("Learning", provider, result, timer.elapsed)

            if mock_save.called:
                print(f"  [OK] BackendClient.save() 호출됨 ({mock_save.call_count}회)")
                for i, call in enumerate(mock_save.call_args_list):
                    args = call[0]
                    if len(args) > 1:
                        req = args[1]
                        data = getattr(req, "data", {})
                        if isinstance(data, dict):
                            ld = data.get("learning_data", {})
                            if ld:
                                print(f"    호출 #{i+1} learning_data 키: {list(ld.keys())}")
            else:
                print("  [WARN] BackendClient.save() 호출되지 않음")

        return result
    except Exception as e:
        print_error("Learning", e)
        return None


# ════════════════════════════════════════
# 메인 실행
# ════════════════════════════════════════


async def main() -> None:
    provider = "ollama"

    print_banner("Mind-Log 커스텀 입력 라이브 테스트", color="bold")
    print(f"  프로바이더: {provider}")
    print(f"  모델: qwen2.5:7b")
    print(f"  입력 주제: 직장 내 뒷담화 — 중간관리자의 갈등")
    print(f"  입력 텍스트 길이: {len(USER_INPUT)}자")

    # 프로바이더 셋업
    print_section("프로바이더 셋업")
    setup_provider(provider)

    # 헬스체크
    print_section("헬스체크")
    healthy = await check_provider_health(provider)
    if not healthy:
        print("  Ollama 서버가 실행되지 않았습니다. `ollama serve`를 실행하세요.")
        return

    total_timer_start = asyncio.get_event_loop().time()

    # ════════════════════════════════
    # 1. Content Analyzer
    # ════════════════════════════════
    ca_result = await test_content_analyzer(provider)
    if ca_result is None:
        print("\n  Content Analyzer 실패 — 이후 테스트 중단")
        return

    # ════════════════════════════════
    # 2. Podcast Reasoning
    # ════════════════════════════════
    pr_result = await test_podcast_reasoning(provider)
    if pr_result is None:
        print("\n  Podcast Reasoning 실패 — 이후 테스트 중단")
        return

    # ════════════════════════════════
    # 3. Batch Validator (앞단 결과 활용)
    # ════════════════════════════════
    content_analysis = ca_result.get("content_analysis", {})
    reasoning_result = pr_result.get("reasoning_result", {})

    bv_result = await test_batch_validator(provider, content_analysis, reasoning_result)

    # ════════════════════════════════
    # 4. Learning Agent (전체 상태 조합)
    # ════════════════════════════════
    full_state = make_custom_state()
    full_state["content_analysis"] = content_analysis
    full_state["reasoning_result"] = reasoning_result
    if bv_result:
        full_state["validation_result"] = bv_result.get("validation_result", {})
        full_state["next_step"] = bv_result.get("next_step", "")

    # Mock script
    script_draft = generate_mock_script(full_state)
    full_state["script_draft"] = script_draft
    full_state["safety_flags"] = {
        "risk_level": "safe",
        "crisis_detected": False,
        "content_warnings": [],
    }
    full_state["emotion_vectors"] = {
        "primary_emotion": "anger",
        "secondary_emotion": "disappointment",
        "intensity": 0.7,
        "valence": -0.5,
    }

    la_result = await test_learning(provider, full_state)

    # ════════════════════════════════
    # 전체 요약
    # ════════════════════════════════
    total_elapsed = asyncio.get_event_loop().time() - total_timer_start
    print_banner("전체 테스트 요약", color="green")
    print(f"  총 소요 시간: {total_elapsed:.2f}초")
    print()

    results = {
        "Content Analyzer": ca_result is not None,
        "Podcast Reasoning": pr_result is not None,
        "Batch Validator": bv_result is not None,
        "Learning Agent": la_result is not None,
    }

    for name, success in results.items():
        status = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
        print(f"  {status} {name}")

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    print(f"\n  결과: {passed} 성공 / {failed} 실패 (총 {len(results)}개)")


if __name__ == "__main__":
    asyncio.run(main())

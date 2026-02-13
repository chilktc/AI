"""
Podcast Reasoning 라이브 LLM 테스트.

실제 LLM을 호출하여 Podcast Reasoning의 GoT/ToT/CoT 추론 파이프라인을 검증한다.
complexity_score=0.7 → "standard" 깊이 (ToT → CoT, LLM 2회 호출).

사용법:
    python3 -m dev.live_tests.run_live --agent podcast_reasoning
    python3 -m dev.live_tests.run_live --agent podcast_reasoning --provider anthropic
"""

from __future__ import annotations

import asyncio
from typing import Any

from dev.live_tests.conftest_live import (
    Timer,
    check_provider_health,
    print_banner,
    print_error,
    print_result,
    print_section,
    setup_provider,
)
from dev.live_tests.fixtures import make_podcast_reasoning_state

# reasoning_result에 존재해야 하는 필수 필드 목록
EXPECTED_FIELDS = [
    "episode_structure",
    "narrative_flow",
    "key_points",
    "emotional_journey",
    "confidence",
    "reasoning_strategy",
    "reasoning_depth",
]


async def run_test(
    provider: str = "ollama",
    model_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Podcast Reasoning 라이브 테스트를 실행한다.

    complexity_score=0.7 → "standard" 깊이 → ToT + CoT (LLM 2회 호출).
    GoT는 실행되지 않는다 (complexity < 0.8).

    Args:
        provider: LLM 프로바이더 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (선택)

    Returns:
        에이전트 반환 dict 또는 실패 시 None
    """
    agent_name = "podcast_reasoning"
    print_banner(f"Podcast Reasoning 라이브 테스트 ({provider})")

    # 1. 프로바이더 셋업
    print_section("프로바이더 셋업")
    setup_provider(provider, model_override)

    # 2. 헬스체크
    print_section("프로바이더 헬스체크")
    healthy = await check_provider_health(provider)
    if not healthy:
        print("  헬스체크 실패 — 테스트를 건너뜁니다.")
        return None

    # 3. 에이전트 생성 + 실행
    print_section("에이전트 실행")
    try:
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()
        state = make_podcast_reasoning_state()

        complexity = state["intent"].get("complexity_score", 0.5)
        # 추론 깊이 예상 출력
        if complexity >= 0.8:
            expected_depth = "full (GoT+ToT+CoT, LLM 3회)"
        elif complexity >= 0.5:
            expected_depth = "standard (ToT+CoT, LLM 2회)"
        else:
            expected_depth = "minimal (CoT만, LLM 1회)"

        print(f"  입력 user_input: {state['user_input'][:60]}...")
        print(f"  입력 intent.category: {state['intent'].get('category', 'N/A')}")
        print(f"  입력 complexity_score: {complexity}")
        print(f"  예상 추론 깊이: {expected_depth}")

        with Timer() as timer:
            result = await agent(state)

        # 4. 결과 출력
        print_result(agent_name, provider, result, timer.elapsed)

        # 5. 필드 존재 확인
        _check_expected_fields(result)

        # 6. 추론 깊이 확인
        _check_reasoning_depth(result)

        return result

    except Exception as e:
        print_error(agent_name, e)
        return None


def _check_expected_fields(result: dict[str, Any]) -> None:
    """reasoning_result 필드 존재 여부를 확인한다."""
    print_section("필드 검증")
    reasoning = result.get("reasoning_result", {})

    missing = []
    for field in EXPECTED_FIELDS:
        if field in reasoning:
            print(f"  [OK] {field}: {_summarize_value(reasoning[field])}")
        else:
            print(f"  [MISSING] {field}")
            missing.append(field)

    if missing:
        print(f"\n  ** 누락 필드 {len(missing)}개: {missing}")
    else:
        print(f"\n  ** 필수 필드 {len(EXPECTED_FIELDS)}개 모두 존재")


def _check_reasoning_depth(result: dict[str, Any]) -> None:
    """추론 깊이와 전략이 올바른지 확인한다."""
    print_section("추론 깊이 검증")
    reasoning = result.get("reasoning_result", {})

    depth = reasoning.get("reasoning_depth", "unknown")
    strategy = reasoning.get("reasoning_strategy", "unknown")
    has_got = "got_result" in reasoning
    has_tot = "tot_result" in reasoning

    print(f"  reasoning_depth: {depth}")
    print(f"  reasoning_strategy: {strategy}")
    print(f"  GoT 결과 포함: {has_got}")
    print(f"  ToT 결과 포함: {has_tot}")

    # complexity=0.7 → standard → ToT+CoT
    if depth == "standard":
        if has_tot and not has_got:
            print("  [OK] standard 깊이에 맞게 ToT 포함, GoT 미포함")
        else:
            print("  [WARN] standard 깊이이지만 예상과 다른 구성")
    elif depth == "full":
        if has_got and has_tot:
            print("  [OK] full 깊이에 맞게 GoT+ToT 모두 포함")
        else:
            print("  [WARN] full 깊이이지만 예상과 다른 구성")
    elif depth == "minimal":
        if not has_got and not has_tot:
            print("  [OK] minimal 깊이에 맞게 GoT/ToT 미포함")
        else:
            print("  [WARN] minimal 깊이이지만 예상과 다른 구성")


def _summarize_value(value: Any) -> str:
    """값을 짧은 요약 문자열로 변환한다."""
    if isinstance(value, list):
        return f"[{len(value)}개 항목]"
    if isinstance(value, dict):
        return f"{{{len(value)}개 키}}"
    if isinstance(value, str) and len(value) > 50:
        return f"{value[:50]}..."
    return str(value)


if __name__ == "__main__":
    asyncio.run(run_test())

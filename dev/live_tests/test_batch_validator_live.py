"""
Batch Validator 라이브 LLM 테스트.

실제 LLM을 호출하여 Batch Validator의 스크립트 품질 검증을 테스트한다.
TIER 3이므로 Content Analyzer, Podcast Reasoning, Safety, Emotion,
Script Generator의 결과가 모두 포함된 상태를 입력으로 사용한다.

사용법:
    python3 -m dev.live_tests.run_live --agent batch_validator
    python3 -m dev.live_tests.run_live --agent batch_validator --provider anthropic
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
from dev.live_tests.fixtures import make_batch_validator_state

# validation_result에 존재해야 하는 필수 필드 목록
EXPECTED_FIELDS = [
    "passed",
    "overall_score",
]


async def run_test(
    provider: str = "ollama",
    model_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Batch Validator 라이브 테스트를 실행한다.

    TIER 1 + TIER 2 결과가 모두 포함된 상태를 입력으로 사용한다.
    검증 결과(passed/failed)와 next_step 라우팅을 확인한다.

    Args:
        provider: LLM 프로바이더 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (선택)

    Returns:
        에이전트 반환 dict 또는 실패 시 None
    """
    agent_name = "batch_validator"
    print_banner(f"Batch Validator 라이브 테스트 ({provider})")

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
        from src.agents.podcast.batch_validator import BatchValidatorAgent

        agent = BatchValidatorAgent()
        state = make_batch_validator_state()

        print(f"  입력 user_input: {state['user_input'][:60]}...")
        print(f"  입력 script_draft.title: {state['script_draft'].get('title', 'N/A')}")
        duration = state["script_draft"].get("total_duration", "N/A")
        print(f"  입력 script_draft.total_duration: {duration}초")
        print(f"  입력 iteration_count: {state.get('iteration_count', 0)}")
        risk = state.get("safety_flags", {}).get("risk_level", "N/A")
        print(f"  입력 safety_flags.risk_level: {risk}")

        with Timer() as timer:
            result = await agent(state)

        # 4. 결과 출력
        print_result(agent_name, provider, result, timer.elapsed)

        # 5. 검증 결과 분석
        _analyze_validation_result(result)

        return result

    except Exception as e:
        print_error(agent_name, e)
        return None


def _analyze_validation_result(result: dict[str, Any]) -> None:
    """검증 결과를 분석하고 라우팅 결정을 출력한다."""
    print_section("검증 결과 분석")
    validation = result.get("validation_result", {})
    next_step = result.get("next_step", "unknown")
    iteration_count = result.get("iteration_count")

    # 필수 필드 확인
    missing = []
    for field in EXPECTED_FIELDS:
        if field in validation:
            print(f"  [OK] {field}: {validation[field]}")
        else:
            print(f"  [MISSING] {field}")
            missing.append(field)

    if missing:
        print(f"\n  ** 누락 필드 {len(missing)}개: {missing}")

    # 라우팅 결정 출력
    print_section("라우팅 결정")
    passed = validation.get("passed", False)
    forced = validation.get("forced_pass", False)

    if passed:
        print("  결과: 검증 통과")
        print(f"  next_step: {next_step}")
        if next_step == "script_personalizer":
            print("  [OK] 올바른 라우팅 (TIER 4 Script Personalizer로 진행)")
        else:
            print(f"  [WARN] 통과했지만 next_step이 예상과 다름: {next_step}")
    elif forced:
        print("  결과: 강제 통과 (최대 재시도 초과)")
        print(f"  next_step: {next_step}")
    else:
        print("  결과: 검증 실패")
        print(f"  next_step: {next_step}")
        if iteration_count is not None:
            print(f"  iteration_count: {iteration_count}")
        if next_step == "retry_script":
            print("  [OK] 올바른 라우팅 (TIER 2 Script Generator 재시도)")
        else:
            print(f"  [WARN] 실패했지만 next_step이 예상과 다름: {next_step}")

    # 검증 항목 상세 출력 (있으면)
    checks = validation.get("checks", {})
    if checks:
        print_section("검증 항목 상세")
        for check_name, check_detail in checks.items():
            if isinstance(check_detail, dict):
                status = "PASS" if check_detail.get("passed", False) else "FAIL"
                score = check_detail.get("score", "N/A")
                print(f"  [{status}] {check_name}: score={score}")
            else:
                print(f"  {check_name}: {check_detail}")


if __name__ == "__main__":
    asyncio.run(run_test())

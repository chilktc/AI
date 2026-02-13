"""
라이브 LLM 테스트 CLI 러너.

개별 에이전트 또는 파이프라인 시뮬레이션을 실제 LLM으로 실행한다.
Ollama(로컬), Anthropic API, AWS Bedrock 모든 프로바이더를 지원한다.

사용법:
    # Ollama (기본값)
    python3 -m dev.live_tests.run_live --agent content_analyzer
    python3 -m dev.live_tests.run_live --all
    python3 -m dev.live_tests.run_live --pipeline

    # Anthropic API
    python3 -m dev.live_tests.run_live --agent content_analyzer --provider anthropic
    python3 -m dev.live_tests.run_live --all --provider anthropic

    # AWS Bedrock
    python3 -m dev.live_tests.run_live --pipeline --provider bedrock

    # 모델 오버라이드 (Ollama)
    python3 -m dev.live_tests.run_live --agent content_analyzer --model mistral:7b

    # 모델 오버라이드 (Anthropic)
    python3 -m dev.live_tests.run_live --agent content_analyzer \
        --provider anthropic --model claude-sonnet-4-20250514
"""

from __future__ import annotations

import argparse
import asyncio
import time

from dev.live_tests.conftest_live import print_banner

# 지원하는 에이전트 이름과 해당 테스트 모듈 매핑
AGENT_MODULES = {
    "content_analyzer": "dev.live_tests.test_content_analyzer_live",
    "podcast_reasoning": "dev.live_tests.test_podcast_reasoning_live",
    "batch_validator": "dev.live_tests.test_batch_validator_live",
    "learning": "dev.live_tests.test_learning_live",
}

# 지원하는 프로바이더 목록
SUPPORTED_PROVIDERS = ["ollama", "anthropic", "bedrock"]


def create_parser() -> argparse.ArgumentParser:
    """CLI 인자를 파싱하는 argparse 파서를 생성한다."""
    parser = argparse.ArgumentParser(
        description="Mind-Log 라이브 LLM 테스트 러너",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 단일 에이전트 (Ollama 기본)
  python3 -m dev.live_tests.run_live --agent content_analyzer

  # 전체 에이전트 순차 실행
  python3 -m dev.live_tests.run_live --all

  # 파이프라인 시뮬레이션
  python3 -m dev.live_tests.run_live --pipeline

  # Anthropic API 사용
  python3 -m dev.live_tests.run_live --all --provider anthropic

  # AWS Bedrock 사용
  python3 -m dev.live_tests.run_live --pipeline --provider bedrock

  # 모델 오버라이드
  python3 -m dev.live_tests.run_live --agent content_analyzer --model mistral:7b
        """,
    )

    # 실행 대상 (상호 배타적 그룹)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--agent",
        choices=list(AGENT_MODULES.keys()),
        help="단일 에이전트 테스트 실행",
    )
    target.add_argument(
        "--all",
        action="store_true",
        help="4개 에이전트 전부 순차 실행",
    )
    target.add_argument(
        "--pipeline",
        action="store_true",
        help="파이프라인 시뮬레이션 (TIER 1→2→3→비동기)",
    )

    # 프로바이더 옵션
    parser.add_argument(
        "--provider",
        choices=SUPPORTED_PROVIDERS,
        default=None,
        help="LLM 프로바이더 (기본값: 환경변수 LLM_PROVIDER 또는 ollama)",
    )

    # 모델 오버라이드
    parser.add_argument(
        "--model",
        default=None,
        help="모델 오버라이드 (예: mistral:7b, claude-sonnet-4-20250514)",
    )

    return parser


def _resolve_provider(provider_arg: str | None) -> str:
    """
    프로바이더를 결정한다.

    우선순위:
        1. CLI --provider 옵션
        2. 환경변수 LLM_PROVIDER
        3. 기본값 "ollama"
    """
    if provider_arg:
        return provider_arg

    import os

    env_provider = os.getenv("LLM_PROVIDER")
    if env_provider and env_provider in SUPPORTED_PROVIDERS:
        return env_provider

    return "ollama"


async def run_single_agent(agent_name: str, provider: str, model_override: str | None) -> bool:
    """
    단일 에이전트 라이브 테스트를 실행한다.

    Args:
        agent_name: 에이전트 이름
        provider: 프로바이더
        model_override: 모델 오버라이드

    Returns:
        성공 여부
    """
    import importlib

    module_name = AGENT_MODULES[agent_name]
    module = importlib.import_module(module_name)
    result = await module.run_test(provider=provider, model_override=model_override)
    return result is not None


async def run_all_agents(provider: str, model_override: str | None) -> None:
    """
    4개 에이전트를 순차적으로 실행한다.

    각 에이전트 결과를 출력하고, 전체 요약을 보여준다.
    """
    print_banner("전체 에이전트 라이브 테스트 시작", color="bold")
    print(f"  프로바이더: {provider}")
    if model_override:
        print(f"  모델 오버라이드: {model_override}")
    print(f"  에이전트 수: {len(AGENT_MODULES)}개")

    results: dict[str, bool] = {}
    total_start = time.perf_counter()

    for agent_name in AGENT_MODULES:
        success = await run_single_agent(agent_name, provider, model_override)
        results[agent_name] = success

    total_elapsed = time.perf_counter() - total_start

    # 전체 요약
    print_banner("전체 에이전트 테스트 요약", color="green")
    print(f"  총 소요 시간: {total_elapsed:.2f}초")
    print(f"  프로바이더: {provider}")
    print()

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    for name, success in results.items():
        status = "\033[92m[OK]\033[0m" if success else "\033[91m[FAIL]\033[0m"
        print(f"  {status} {name}")

    print(f"\n  결과: {passed} 성공 / {failed} 실패 (총 {len(results)}개)")


async def run_pipeline(provider: str, model_override: str | None) -> None:
    """파이프라인 시뮬레이션을 실행한다."""
    from dev.live_tests.test_pipeline_live import run_test

    await run_test(provider=provider, model_override=model_override)


def main() -> None:
    """CLI 메인 엔트리포인트."""
    parser = create_parser()
    args = parser.parse_args()

    provider = _resolve_provider(args.provider)

    print_banner("Mind-Log 라이브 LLM 테스트", color="bold")
    print(f"  프로바이더: {provider}")
    if args.model:
        print(f"  모델 오버라이드: {args.model}")

    if args.agent:
        print(f"  대상: {args.agent}")
        asyncio.run(run_single_agent(args.agent, provider, args.model))
    elif args.all:
        print("  대상: 전체 에이전트 (4개)")
        asyncio.run(run_all_agents(provider, args.model))
    elif args.pipeline:
        print("  대상: 파이프라인 시뮬레이션")
        asyncio.run(run_pipeline(provider, args.model))


if __name__ == "__main__":
    main()

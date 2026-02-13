"""
Content Analyzer 라이브 LLM 테스트.

실제 LLM을 호출하여 Content Analyzer의 동작을 검증한다.
JSON 파싱, 후처리(validation_and_correct), 필드 존재 여부를 확인한다.

사용법:
    python3 -m dev.live_tests.run_live --agent content_analyzer
    python3 -m dev.live_tests.run_live --agent content_analyzer --provider anthropic
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
from dev.live_tests.fixtures import make_content_analyzer_state

# Content Analyzer가 반환해야 하는 필수 필드 목록
EXPECTED_FIELDS = [
    "main_theme",
    "sub_themes",
    "episode_type",
    "depth_level",
    "target_duration",
    "narrative_structure",
]


async def run_test(
    provider: str = "ollama",
    model_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Content Analyzer 라이브 테스트를 실행한다.

    1. 프로바이더 셋업 + 헬스체크
    2. 현실적인 한국어 AgentState 생성
    3. ContentAnalyzerAgent 인스턴스 생성 + 실행
    4. 결과 출력 (JSON pretty-print)

    Args:
        provider: LLM 프로바이더 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (선택)

    Returns:
        에이전트 반환 dict 또는 실패 시 None
    """
    agent_name = "content_analyzer"
    print_banner(f"Content Analyzer 라이브 테스트 ({provider})")

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
        # import를 여기서 하는 이유: setup_provider가 먼저 환경을 설정해야 함
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        state = make_content_analyzer_state()

        print(f"  입력 user_input: {state['user_input'][:60]}...")
        print(f"  입력 intent.category: {state['intent'].get('category', 'N/A')}")
        print(f"  입력 complexity_score: {state['intent'].get('complexity_score', 'N/A')}")

        with Timer() as timer:
            result = await agent(state)

        # 4. 결과 출력
        print_result(agent_name, provider, result, timer.elapsed)

        # 5. 필드 존재 확인
        _check_expected_fields(result)

        return result

    except Exception as e:
        print_error(agent_name, e)
        return None


def _check_expected_fields(result: dict[str, Any]) -> None:
    """content_analysis 필드 존재 여부를 확인하고 결과를 출력한다."""
    print_section("필드 검증")
    content_analysis = result.get("content_analysis", {})

    missing = []
    for field in EXPECTED_FIELDS:
        if field in content_analysis:
            print(f"  [OK] {field}: {_summarize_value(content_analysis[field])}")
        else:
            print(f"  [MISSING] {field}")
            missing.append(field)

    if missing:
        print(f"\n  ** 누락 필드 {len(missing)}개: {missing}")
    else:
        print(f"\n  ** 필수 필드 {len(EXPECTED_FIELDS)}개 모두 존재")


def _summarize_value(value: Any) -> str:
    """값을 짧은 요약 문자열로 변환한다."""
    if isinstance(value, list):
        return f"[{len(value)}개 항목]"
    if isinstance(value, str) and len(value) > 50:
        return f"{value[:50]}..."
    return str(value)


if __name__ == "__main__":
    asyncio.run(run_test())

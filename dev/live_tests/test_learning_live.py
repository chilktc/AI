"""
Learning Agent 라이브 LLM 테스트.

실제 LLM을 호출하여 Learning Agent의 패턴 학습 동작을 검증한다.
BackendClient.save()만 mock 처리하고, LLM 호출은 실제로 수행한다.

사용법:
    python3 -m dev.live_tests.run_live --agent learning
    python3 -m dev.live_tests.run_live --agent learning --provider anthropic
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
from dev.live_tests.fixtures import make_learning_state


async def run_test(
    provider: str = "ollama",
    model_override: str | None = None,
) -> dict[str, Any] | None:
    """
    Learning Agent 라이브 테스트를 실행한다.

    Learning Agent는 전체 파이프라인 완료 상태를 입력으로 받아
    LLM으로 사용자 패턴을 분석한 후 백엔드 API로 저장한다.
    이 테스트에서는 BackendClient.save()만 mock하고 LLM 호출은 실제 수행.

    Args:
        provider: LLM 프로바이더 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (선택)

    Returns:
        에이전트 반환 dict 또는 실패 시 None
    """
    agent_name = "learning"
    print_banner(f"Learning Agent 라이브 테스트 ({provider})")

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
        from src.agents.shared.learning import LearningAgent
        from src.api.client import BackendClient

        state = make_learning_state()

        print(f"  입력 user_input: {state['user_input'][:60]}...")
        print(f"  입력 mode: {state.get('mode', 'N/A')}")
        print(f"  입력 content_analysis 존재: {'content_analysis' in state}")
        print(f"  입력 validation_result 존재: {'validation_result' in state}")
        print(f"  입력 final_output 존재: {'final_output' in state}")

        # BackendClient.save()만 mock — LLM 호출은 실제
        mock_response = {"success": True, "id": "live-test-learning-001", "message": "saved"}

        with patch.object(
            BackendClient, "save", new_callable=AsyncMock, return_value=mock_response
        ) as mock_save:
            agent = LearningAgent()

            with Timer() as timer:
                result = await agent(state)

            # 4. 결과 출력
            # Learning Agent는 빈 dict를 반환한다 (AgentState 변경 없음)
            print_result(agent_name, provider, result, timer.elapsed)

            # 5. BackendClient.save() 호출 확인
            _check_api_call(mock_save)

        return result

    except Exception as e:
        print_error(agent_name, e)
        return None


def _check_api_call(mock_save: AsyncMock) -> None:
    """BackendClient.save()가 올바르게 호출되었는지 확인한다."""
    print_section("API 호출 확인")

    if mock_save.called:
        call_count = mock_save.call_count
        print(f"  [OK] BackendClient.save() 호출됨 ({call_count}회)")

        # 호출 인자 확인
        for i, call in enumerate(mock_save.call_args_list):
            args, kwargs = call
            print(f"\n  호출 #{i + 1}:")
            if args:
                print(f"    resource: {args[0] if args else 'N/A'}")
            if len(args) > 1:
                request = args[1]
                print(f"    request.user_id: {getattr(request, 'user_id', 'N/A')}")
                print(f"    request.session_id: {getattr(request, 'session_id', 'N/A')}")
                print(f"    request.type: {getattr(request, 'type', 'N/A')}")
                data = getattr(request, "data", {})
                if isinstance(data, dict):
                    print(f"    request.data.mode: {data.get('mode', 'N/A')}")
                    learning_data = data.get("learning_data", {})
                    if learning_data:
                        print(f"    learning_data 키: {list(learning_data.keys())}")
    else:
        print("  [WARN] BackendClient.save()가 호출되지 않았습니다.")
        print("  Learning Agent가 API 저장을 건너뛴 것일 수 있습니다.")


if __name__ == "__main__":
    asyncio.run(run_test())

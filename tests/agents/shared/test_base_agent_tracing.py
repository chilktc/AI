"""
BaseAgent LangSmith LLM 트레이싱 테스트.

_traced_llm_call()이 run_type="llm" 스팬을 올바르게 생성하고,
graceful degradation이 정상 동작하는지 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState

# ── 테스트용 구체 에이전트 ──


class _StubAgent(BaseAgent):
    """테스트용 BaseAgent 구현체."""

    def __init__(self) -> None:
        # BaseAgent.__init__은 Settings, LLMClient 등을 로드하므로 전부 mock
        with (
            patch("src.agents.shared.base_agent.LLMClient") as mock_llm_cls,
            patch("src.agents.shared.base_agent.get_settings") as mock_settings,
            patch("src.agents.shared.base_agent.PromptLoader"),
            patch("src.agents.shared.base_agent.get_prompt_base_dir", return_value="/tmp"),
        ):
            settings = MagicMock()
            settings.get_agent_config.return_value = {
                "model": "sonnet",
                "model_id": "claude-sonnet-4-5-20250929",
                "max_tokens": 2048,
                "temperature": 0.7,
            }
            settings.get_prompt_version.return_value = None
            settings.get_ab_test_config.return_value = None
            mock_settings.return_value = settings

            mock_client = MagicMock()
            mock_client.model_id = "claude-sonnet-4-5-20250929"
            mock_client.provider = "anthropic"
            mock_client.generate = AsyncMock(return_value="LLM 응답 텍스트")
            mock_client.last_usage = {
                "input_tokens": 500,
                "output_tokens": 200,
                "total_tokens": 700,
            }
            mock_client._parse_json_response = MagicMock(
                return_value={"key": "value"}
            )
            mock_llm_cls.return_value = mock_client

            super().__init__(name="test_agent", tier=1)

    async def process(self, state: AgentState) -> dict[str, Any]:
        return {}


# ── 테스트 ──


class TestTracedLlmCall:
    """_traced_llm_call() LangSmith LLM 스팬 생성 검증."""

    @pytest.mark.asyncio
    async def test_graceful_without_langsmith(self) -> None:
        """langsmith 미설치 시에도 generate()가 정상 호출된다."""
        agent = _StubAgent()

        with patch(
            "src.agents.shared.base_agent.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.langsmith_tracing_enabled = True
            mock_settings.return_value = settings

            # langsmith import를 실패시킨다
            with patch.dict("sys.modules", {"langsmith": None}):
                result = await agent._traced_llm_call(
                    system_prompt="system",
                    user_message="hello",
                )

        assert result == "LLM 응답 텍스트"
        agent.llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_disabled_by_config(self) -> None:
        """tracing_enabled=false 시 직접 호출한다."""
        agent = _StubAgent()

        with patch(
            "src.agents.shared.base_agent.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.langsmith_tracing_enabled = False
            mock_settings.return_value = settings

            result = await agent._traced_llm_call(
                system_prompt="system",
                user_message="hello",
            )

        assert result == "LLM 응답 텍스트"
        agent.llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_llm_span_when_enabled(self) -> None:
        """langsmith 활성 시 @traceable(run_type='llm')이 호출된다."""
        agent = _StubAgent()

        mock_traceable = MagicMock()
        # @traceable(...)가 데코레이터로 동작하도록 설정
        # traceable(**kwargs) -> decorator -> decorator(fn) -> fn (pass-through)
        mock_traceable.side_effect = lambda **kwargs: lambda fn: fn

        mock_langsmith = MagicMock()
        mock_langsmith.traceable = mock_traceable

        with (
            patch(
                "src.agents.shared.base_agent.get_settings"
            ) as mock_settings,
            patch.dict("sys.modules", {"langsmith": mock_langsmith}),
        ):
            settings = MagicMock()
            settings.langsmith_tracing_enabled = True
            mock_settings.return_value = settings

            # importlib cache를 우회하기 위해 직접 import mock
            await agent._traced_llm_call(
                system_prompt="system",
                user_message="hello",
            )

        # traceable이 run_type="llm"으로 호출되었는지 확인
        mock_traceable.assert_called_once()
        call_kwargs = mock_traceable.call_args[1]
        assert call_kwargs["run_type"] == "llm"
        assert "ls_model_name" in call_kwargs.get("metadata", {})
        assert "ls_provider" in call_kwargs.get("metadata", {})

    @pytest.mark.asyncio
    async def test_returns_str_type(self) -> None:
        """_traced_llm_call()은 항상 str을 반환한다."""
        agent = _StubAgent()

        with patch(
            "src.agents.shared.base_agent.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.langsmith_tracing_enabled = False
            mock_settings.return_value = settings

            result = await agent._traced_llm_call(
                system_prompt="system",
                user_message="hello",
            )

        assert isinstance(result, str)


class TestCallLlmTracing:
    """call_llm(), call_llm_json()이 _traced_llm_call()을 경유하는지 검증."""

    @pytest.mark.asyncio
    async def test_call_llm_delegates_to_traced(self) -> None:
        """call_llm()이 _traced_llm_call()을 호출한다."""
        agent = _StubAgent()
        agent._traced_llm_call = AsyncMock(return_value="traced result")

        result = await agent.call_llm(
            system_prompt="system",
            user_message="hello",
        )

        assert result == "traced result"
        agent._traced_llm_call.assert_called_once_with(
            system_prompt="system",
            user_message="hello",
        )
        assert agent._llm_call_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_json_delegates_to_traced(self) -> None:
        """call_llm_json()이 _traced_llm_call() + JSON 파싱을 수행한다."""
        agent = _StubAgent()
        agent._traced_llm_call = AsyncMock(
            return_value='{"key": "value"}'
        )
        agent.llm_client._parse_json_response.return_value = {"key": "value"}

        result = await agent.call_llm_json(
            system_prompt="system",
            user_message="hello",
        )

        assert result == {"key": "value"}
        agent._traced_llm_call.assert_called_once()
        agent.llm_client._parse_json_response.assert_called_once_with(
            '{"key": "value"}'
        )
        assert agent._llm_call_count == 1

    @pytest.mark.asyncio
    async def test_token_usage_available_after_call(self) -> None:
        """LLM 호출 후 토큰 사용량이 llm_client.last_usage에 유지된다."""
        agent = _StubAgent()

        with patch(
            "src.agents.shared.base_agent.get_settings"
        ) as mock_settings:
            settings = MagicMock()
            settings.langsmith_tracing_enabled = False
            mock_settings.return_value = settings

            await agent.call_llm(
                system_prompt="system",
                user_message="hello",
            )

        usage = agent.llm_client.last_usage
        assert usage is not None
        assert usage["input_tokens"] == 500
        assert usage["output_tokens"] == 200
        assert usage["total_tokens"] == 700

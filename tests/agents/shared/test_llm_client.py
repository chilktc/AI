"""
LLM 클라이언트 듀얼 프로바이더 테스트.

v9에서 도입된 Anthropic + AWS Bedrock 듀얼 아키텍처를 검증한다.
- LLMClient: 프로바이더 선택, 모델 ID 해석, generate/generate_json
- Settings: llm_provider, bedrock_region, bedrock_config, get_bedrock_model_id
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.loader import Settings

# ===================================================================
# 환경변수 격리 — .env의 LLM_PROVIDER가 테스트에 간섭하지 않도록 보장
# ===================================================================


@pytest.fixture(autouse=True)
def _clean_llm_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM_PROVIDER 환경변수가 테스트에 간섭하지 않도록 제거."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ===================================================================
# 공통 헬퍼
# ===================================================================

_TEST_SETTINGS_YAML = """\
app:
  name: mind-log-test
  version: "0.1.0"

llm:
  provider: anthropic
  models:
    haiku: "claude-haiku-4-5-20251001"
    sonnet: "claude-sonnet-4-5-20250929"
    opus: "claude-opus-4-6"
  bedrock_models:
    haiku: "anthropic.claude-haiku-4-5-20251001-v1:0"
    sonnet: "anthropic.claude-sonnet-4-5-20250929-v2:0"
    opus: "anthropic.claude-opus-4-6-v1:0"
  openai_models:
    haiku: "gpt-4o-mini"
    sonnet: "gpt-4o-mini"
    opus: "gpt-4o"
  bedrock:
    region: "ap-northeast-2"
  default_max_tokens: 4096
  temperature:
    default: 0.7
    safety: 0.1
    reasoning: 0.3

agents:
  content_analyzer:
    model: sonnet
    max_tokens: 2048

pipeline:
  max_retries: 2
  tier1_timeout_seconds: 15
  tier2_timeout_seconds: 20
  async_timeout_seconds: 30

api:
  timeout: 5
  llm_timeout: 30
  max_retries: 3

prompts:
  base_dir: "prompts"
  versions:
    default: "1.0.0"

features:
  podcast_mode: true
"""


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    """테스트용 Settings 인스턴스를 생성한다."""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(_TEST_SETTINGS_YAML)
    return Settings(config_path=config_file)


def _mock_settings_factory(
    provider: str = "anthropic",
    model: str = "sonnet",
    model_id: str | None = "claude-sonnet-4-5-20250929",
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> MagicMock:
    """LLMClient 테스트용 mock Settings 팩토리."""
    settings = MagicMock()
    settings.llm_provider = provider
    agent_config: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if model_id is not None:
        agent_config["model_id"] = model_id
    settings.get_agent_config.return_value = agent_config
    settings.get_model_id.return_value = (
        model_id or "claude-sonnet-4-5-20250929"
    )
    settings.get_bedrock_model_id.return_value = (
        "anthropic.claude-sonnet-4-5-20250929-v2:0"
    )
    settings.get_openai_model_id.return_value = "gpt-4o-mini"
    settings.bedrock_region = "ap-northeast-2"
    settings.bedrock_config = {"region": "ap-northeast-2"}
    settings.prompt_caching_config = {"enabled": False, "min_tokens": 1024}
    return settings


def _mock_anthropic_response(
    text: str, input_tokens: int = 100, output_tokens: int = 50
) -> MagicMock:
    """Anthropic API 응답 mock."""
    mock_text_block = MagicMock()
    mock_text_block.text = text
    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_response.usage.input_tokens = input_tokens
    mock_response.usage.output_tokens = output_tokens
    return mock_response


# ===================================================================
# Settings 속성 테스트
# ===================================================================


def test_settings_llm_provider_default(test_settings: Settings) -> None:
    """기본 프로바이더는 anthropic이다."""
    assert test_settings.llm_provider == "anthropic"


def test_settings_llm_provider_env_override(test_settings: Settings) -> None:
    """환경변수 LLM_PROVIDER로 프로바이더 오버라이드 가능."""
    with patch.dict("os.environ", {"LLM_PROVIDER": "bedrock"}):
        assert test_settings.llm_provider == "bedrock"


@pytest.mark.parametrize(
    "getter, key, expected",
    [
        ("get_bedrock_model_id", "haiku", "anthropic.claude-haiku-4-5-20251001-v1:0"),
        ("get_bedrock_model_id", "sonnet", "anthropic.claude-sonnet-4-5-20250929-v2:0"),
        ("get_bedrock_model_id", "opus", "anthropic.claude-opus-4-6-v1:0"),
        ("get_openai_model_id", "haiku", "gpt-4o-mini"),
        ("get_openai_model_id", "sonnet", "gpt-4o-mini"),
        ("get_openai_model_id", "opus", "gpt-4o"),
    ],
    ids=[
        "bedrock_haiku", "bedrock_sonnet", "bedrock_opus",
        "openai_haiku", "openai_sonnet", "openai_opus",
    ],
)
def test_settings_model_id_by_provider(
    test_settings: Settings, getter: str, key: str, expected: str
) -> None:
    """프로바이더별 모델 ID를 키로 조회한다."""
    assert getattr(test_settings, getter)(key) == expected


def test_settings_bedrock_model_id_env_override(test_settings: Settings) -> None:
    """환경변수로 Bedrock 모델 ID 오버라이드 가능."""
    with patch.dict("os.environ", {"LLM_BEDROCK_MODEL_SONNET": "custom-model"}):
        assert test_settings.get_bedrock_model_id("sonnet") == "custom-model"


# ===================================================================
# LLMClient — Anthropic 모드
# ===================================================================


@patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
@patch("src.agents.shared.llm_client.get_settings")
def test_anthropic_client_init(
    mock_settings: MagicMock, mock_anthropic: MagicMock
) -> None:
    """기본 Anthropic 모드로 LLMClient가 초기화된다."""
    mock_settings.return_value = _mock_settings_factory()

    from src.agents.shared.llm_client import LLMClient

    client = LLMClient(agent_name="content_analyzer")
    assert client.provider == "anthropic"
    assert client.model_id == "claude-sonnet-4-5-20250929"


@patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
@patch("src.agents.shared.llm_client.get_settings")
async def test_anthropic_generate(
    mock_settings: MagicMock, mock_anthropic_cls: MagicMock
) -> None:
    """Anthropic generate()가 API를 호출하고 텍스트를 반환한다."""
    mock_settings.return_value = _mock_settings_factory()
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response("분석 결과입니다.")
    )
    mock_anthropic_cls.return_value = mock_client

    from src.agents.shared.llm_client import LLMClient

    client = LLMClient(agent_name="content_analyzer")
    result = await client.generate(system_prompt="시스템", user_message="메시지")

    assert result == "분석 결과입니다."
    mock_client.messages.create.assert_called_once()


@patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
@patch("src.agents.shared.llm_client.get_settings")
async def test_anthropic_generate_json(
    mock_settings: MagicMock, mock_anthropic_cls: MagicMock
) -> None:
    """Anthropic generate_json()이 JSON 응답을 파싱한다."""
    mock_settings.return_value = _mock_settings_factory()
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response('{"key": "value", "score": 0.95}')
    )
    mock_anthropic_cls.return_value = mock_client

    from src.agents.shared.llm_client import LLMClient

    client = LLMClient(agent_name="content_analyzer")
    result = await client.generate_json(
        system_prompt="JSON으로 응답하라.", user_message="테스트"
    )

    assert result == {"key": "value", "score": 0.95}


# ===================================================================
# LLMClient — Bedrock 모드
# ===================================================================


@patch("src.agents.shared.llm_client.get_settings")
def test_bedrock_client_init(mock_settings: MagicMock) -> None:
    """provider_override='bedrock'으로 Bedrock 모드를 활성화한다."""
    mock_settings.return_value = _mock_settings_factory(model_id=None)
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = MagicMock()

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer", provider_override="bedrock"
        )
        assert client.provider == "bedrock"
        assert client.model_id == "anthropic.claude-sonnet-4-5-20250929-v2:0"


@patch("src.agents.shared.llm_client.get_settings")
async def test_bedrock_generate(mock_settings: MagicMock) -> None:
    """Bedrock generate()가 Converse API를 호출한다."""
    mock_settings.return_value = _mock_settings_factory(model_id=None)

    mock_bedrock_client = MagicMock()
    mock_bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Bedrock 응답입니다."}]
            }
        },
        "usage": {"inputTokens": 10, "outputTokens": 5},
    }
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_bedrock_client

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer", provider_override="bedrock"
        )
        result = await client.generate(system_prompt="시스템", user_message="메시지")

        assert result == "Bedrock 응답입니다."
        mock_bedrock_client.converse.assert_called_once()

        # Converse API 요청 검증
        call_kwargs = mock_bedrock_client.converse.call_args
        assert call_kwargs.kwargs["system"] == [{"text": "시스템"}]
        assert call_kwargs.kwargs["messages"][0]["content"] == [{"text": "메시지"}]


# ===================================================================
# 프로바이더 우선순위: override > 환경변수 > 설정
# ===================================================================


@patch("src.agents.shared.llm_client.get_settings")
def test_provider_override_trumps_env_and_settings(
    mock_settings: MagicMock,
) -> None:
    """provider_override가 환경변수와 settings보다 우선한다."""
    mock_settings.return_value = _mock_settings_factory()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = MagicMock()

    with (
        patch.dict("os.environ", {"LLM_PROVIDER": "anthropic"}),
        patch.dict("sys.modules", {"boto3": mock_boto3}),
    ):
        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer", provider_override="bedrock"
        )
        assert client.provider == "bedrock"


# ===================================================================
# JSON 파싱
# ===================================================================


@pytest.mark.parametrize(
    "input_text, expected",
    [
        ('{"key": "value"}', {"key": "value"}),
        ('```json\n{"key": "value"}\n```', {"key": "value"}),
        ('  \n{"key": "value"}\n  ', {"key": "value"}),
        (
            '{"outer": {"inner": [1, 2, 3]}, "score": 0.95}',
            {"outer": {"inner": [1, 2, 3]}, "score": 0.95},
        ),
    ],
)
def test_json_parsing_valid(input_text: str, expected: dict) -> None:
    """다양한 형태의 JSON 문자열을 파싱한다."""
    from src.agents.shared.llm_client import LLMClient

    assert LLMClient.parse_json_response(input_text) == expected


def test_json_parsing_invalid() -> None:
    """유효하지 않은 JSON은 JSONDecodeError를 발생시킨다."""
    from src.agents.shared.llm_client import LLMClient

    with pytest.raises(json.JSONDecodeError):
        LLMClient.parse_json_response("not json at all")


# ===================================================================
# Bedrock boto3 미설치
# ===================================================================


@patch("src.agents.shared.llm_client.get_settings")
def test_bedrock_without_boto3_raises(mock_settings: MagicMock) -> None:
    """boto3 없이 Bedrock 모드 초기화 시 ImportError가 발생한다."""
    mock_settings.return_value = _mock_settings_factory()

    import builtins

    original_import = builtins.__import__

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "boto3":
            raise ImportError("No module named 'boto3'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        from src.agents.shared.llm_client import LLMClient

        with pytest.raises(ImportError, match="boto3"):
            LLMClient(
                agent_name="content_analyzer", provider_override="bedrock"
            )


# ===================================================================
# 커스텀 프로바이더
# ===================================================================


@patch("src.agents.shared.llm_client.get_settings")
async def test_custom_provider_lifecycle(mock_settings: MagicMock) -> None:
    """커스텀 프로바이더 등록 → 초기화 → generate → 해제 전체 라이프사이클."""
    mock_settings.return_value = _mock_settings_factory()

    mock_provider_instance = MagicMock()
    mock_provider_instance.generate = AsyncMock(return_value="커스텀 응답")
    mock_provider_cls = MagicMock(return_value=mock_provider_instance)

    from src.agents.shared.llm_client import LLMClient

    try:
        # 등록
        LLMClient.register_provider("test_local", mock_provider_cls)
        assert "test_local" in LLMClient._custom_providers

        # 초기화
        client = LLMClient(
            agent_name="content_analyzer", provider_override="test_local"
        )
        assert client.provider == "test_local"
        mock_provider_cls.assert_called_once_with(model_id="sonnet")

        # generate 호출
        result = await client.generate(
            system_prompt="시스템 프롬프트", user_message="사용자 메시지"
        )
        assert result == "커스텀 응답"
        mock_provider_instance.generate.assert_called_once_with(
            "시스템 프롬프트", "사용자 메시지", 2048, 0.7
        )
    finally:
        # 해제
        LLMClient.unregister_provider("test_local")
        assert "test_local" not in LLMClient._custom_providers


@patch("src.agents.shared.llm_client.get_settings")
async def test_custom_provider_error_propagates(mock_settings: MagicMock) -> None:
    """커스텀 프로바이더의 generate() 예외가 그대로 전파된다."""
    mock_settings.return_value = _mock_settings_factory()

    mock_provider_instance = MagicMock()
    mock_provider_instance.generate = AsyncMock(
        side_effect=ConnectionError("Ollama 서버 연결 실패")
    )
    mock_provider_cls = MagicMock(return_value=mock_provider_instance)

    from src.agents.shared.llm_client import LLMClient

    try:
        LLMClient.register_provider("test_err", mock_provider_cls)
        client = LLMClient(
            agent_name="content_analyzer", provider_override="test_err"
        )

        with pytest.raises(ConnectionError, match="Ollama 서버 연결 실패"):
            await client.generate(system_prompt="시스템", user_message="메시지")
    finally:
        LLMClient.unregister_provider("test_err")


# ===================================================================
# OpenAI 모드
# ===================================================================


@patch("src.agents.shared.llm_client.get_settings")
def test_openai_client_init(mock_settings: MagicMock) -> None:
    """provider_override='openai'로 OpenAI 모드를 활성화한다."""
    mock_settings.return_value = _mock_settings_factory(model_id=None)

    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI.return_value = MagicMock()

    with patch.dict("sys.modules", {"openai": mock_openai}):
        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer", provider_override="openai"
        )
        assert client.provider == "openai"
        assert client.model_id == "gpt-4o-mini"


@patch("src.agents.shared.llm_client.get_settings")
async def test_openai_generate(mock_settings: MagicMock) -> None:
    """OpenAI generate()가 API를 올바르게 호출한다."""
    mock_settings.return_value = _mock_settings_factory(model_id=None)

    mock_message = MagicMock()
    mock_message.content = "OpenAI 응답입니다."
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 100
    mock_usage.completion_tokens = 50
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create = AsyncMock(
        return_value=mock_response
    )
    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI.return_value = mock_client_instance

    with patch.dict("sys.modules", {"openai": mock_openai}):
        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer", provider_override="openai"
        )
        result = await client.generate(
            system_prompt="시스템 프롬프트", user_message="사용자 메시지"
        )

        assert result == "OpenAI 응답입니다."
        mock_client_instance.chat.completions.create.assert_called_once()

        # API 호출 파라미터 검증
        call_kwargs = (
            mock_client_instance.chat.completions.create.call_args.kwargs
        )
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["messages"][0] == {
            "role": "system",
            "content": "시스템 프롬프트",
        }


# ===================================================================
# 토큰 사용량 추적
# ===================================================================


@patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
@patch("src.agents.shared.llm_client.get_settings")
async def test_token_usage_lifecycle(
    mock_settings: MagicMock, mock_anthropic_cls: MagicMock
) -> None:
    """토큰 사용량: 초기(None) → 기록 → 누적 → 리셋 전체 라이프사이클."""
    mock_settings.return_value = _mock_settings_factory()

    resp1 = _mock_anthropic_response("응답1", input_tokens=100, output_tokens=50)
    resp2 = _mock_anthropic_response("응답2", input_tokens=200, output_tokens=80)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=[resp1, resp2])
    mock_anthropic_cls.return_value = mock_client

    from src.agents.shared.llm_client import LLMClient

    client = LLMClient(agent_name="content_analyzer")

    # 초기 상태
    assert client.last_usage is None
    total = client.total_usage
    assert total["input_tokens"] == 0
    assert total["output_tokens"] == 0
    assert total["total_tokens"] == 0

    # 첫 번째 호출 — 사용량 기록
    await client.generate(system_prompt="시스템", user_message="메시지1")
    assert client.last_usage is not None
    assert client.last_usage["input_tokens"] == 100
    assert client.last_usage["output_tokens"] == 50
    assert client.last_usage["total_tokens"] == 150
    assert client.total_usage["total_tokens"] == 150

    # 두 번째 호출 — 누적
    await client.generate(system_prompt="시스템", user_message="메시지2")
    assert client.last_usage["input_tokens"] == 200  # 마지막 호출 결과
    assert client.total_usage["input_tokens"] == 300  # 100 + 200
    assert client.total_usage["output_tokens"] == 130  # 50 + 80
    assert client.total_usage["total_tokens"] == 430  # 150 + 280

    # 리셋
    client.reset_total_usage()
    assert client.total_usage["total_tokens"] == 0
    assert client.last_usage is not None  # last_usage는 리셋되지 않음

    # total_usage는 복사본 반환 — 외부 변경이 내부에 영향 없음
    total_copy = client.total_usage
    total_copy["input_tokens"] = 99999
    assert client.total_usage["input_tokens"] == 0

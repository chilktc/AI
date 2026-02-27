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
    """
    .env의 LLM_PROVIDER가 테스트에 간섭하지 않도록 환경변수를 제거한다.

    load_dotenv()가 모듈 임포트 시점에 LLM_PROVIDER를 설정할 수 있으므로,
    매 테스트 전 깨끗한 상태를 보장한다.
    개별 테스트가 patch.dict로 LLM_PROVIDER를 설정하면 그 값이 우선한다.
    """
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ===================================================================
# 테스트용 설정 파일 내용 (settings.yaml과 동일 구조)
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


# ===================================================================
# Settings — LLM 프로바이더 속성 테스트
# ===================================================================


class TestSettingsLLMProvider:
    """Settings의 LLM 프로바이더 관련 속성을 검증한다."""

    def test_llm_provider_default_is_anthropic(self, test_settings: Settings) -> None:
        """기본 프로바이더는 anthropic이다."""
        assert test_settings.llm_provider == "anthropic"

    def test_llm_provider_env_override(self, test_settings: Settings) -> None:
        """환경변수 LLM_PROVIDER로 오버라이드 가능하다."""
        with patch.dict("os.environ", {"LLM_PROVIDER": "bedrock"}):
            assert test_settings.llm_provider == "bedrock"

    def test_bedrock_region_default(self, test_settings: Settings) -> None:
        """기본 Bedrock 리전은 ap-northeast-2이다."""
        assert test_settings.bedrock_region == "ap-northeast-2"

    def test_bedrock_region_env_override(self, test_settings: Settings) -> None:
        """환경변수 AWS_REGION으로 리전 오버라이드 가능하다."""
        with patch.dict("os.environ", {"AWS_REGION": "us-east-1"}):
            assert test_settings.bedrock_region == "us-east-1"

    def test_bedrock_config_returns_dict(self, test_settings: Settings) -> None:
        """bedrock_config는 dict를 반환한다."""
        config = test_settings.bedrock_config
        assert isinstance(config, dict)
        assert config.get("region") == "ap-northeast-2"

    def test_bedrock_config_empty_when_missing(self, tmp_path: Path) -> None:
        """bedrock 섹션이 없으면 빈 dict를 반환한다."""
        minimal_yaml = """\
app:
  name: test
  version: "0.1.0"
llm:
  provider: anthropic
  models:
    sonnet: "claude-sonnet-4-5-20250929"
  default_max_tokens: 4096
  temperature:
    default: 0.7
agents: {}
pipeline:
  max_retries: 2
  tier1_timeout_seconds: 15
api:
  timeout: 5
  max_retries: 3
features: {}
prompts:
  base_dir: "prompts"
  versions:
    default: "1.0.0"
"""
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(minimal_yaml)
        settings = Settings(config_path=config_file)
        assert settings.bedrock_config == {}


# ===================================================================
# Settings — Bedrock 모델 ID 테스트
# ===================================================================


class TestSettingsBedrockModelId:
    """Settings의 Bedrock 모델 ID 조회를 검증한다."""

    def test_get_bedrock_model_id_sonnet(self, test_settings: Settings) -> None:
        """sonnet 키로 Bedrock 모델 ID를 조회한다."""
        model_id = test_settings.get_bedrock_model_id("sonnet")
        assert model_id == "anthropic.claude-sonnet-4-5-20250929-v2:0"

    def test_get_bedrock_model_id_haiku(self, test_settings: Settings) -> None:
        """haiku 키로 Bedrock 모델 ID를 조회한다."""
        model_id = test_settings.get_bedrock_model_id("haiku")
        assert model_id == "anthropic.claude-haiku-4-5-20251001-v1:0"

    def test_get_bedrock_model_id_opus(self, test_settings: Settings) -> None:
        """opus 키로 Bedrock 모델 ID를 조회한다."""
        model_id = test_settings.get_bedrock_model_id("opus")
        assert model_id == "anthropic.claude-opus-4-6-v1:0"

    def test_get_bedrock_model_id_env_override(self, test_settings: Settings) -> None:
        """환경변수 LLM_BEDROCK_MODEL_SONNET으로 오버라이드 가능하다."""
        with patch.dict(
            "os.environ",
            {"LLM_BEDROCK_MODEL_SONNET": "custom-bedrock-model-id"},
        ):
            model_id = test_settings.get_bedrock_model_id("sonnet")
            assert model_id == "custom-bedrock-model-id"

    def test_get_bedrock_model_id_fallback_to_anthropic(self, tmp_path: Path) -> None:
        """bedrock_models에 키가 없으면 기본 Anthropic 모델 ID로 fallback한다."""
        yaml_without_bedrock_models = """\
app:
  name: test
  version: "0.1.0"
llm:
  provider: anthropic
  models:
    sonnet: "claude-sonnet-4-5-20250929"
  default_max_tokens: 4096
  temperature:
    default: 0.7
agents: {}
pipeline:
  max_retries: 2
  tier1_timeout_seconds: 15
api:
  timeout: 5
  max_retries: 3
features: {}
prompts:
  base_dir: "prompts"
  versions:
    default: "1.0.0"
"""
        config_file = tmp_path / "no_bedrock.yaml"
        config_file.write_text(yaml_without_bedrock_models)
        settings = Settings(config_path=config_file)
        # bedrock_models가 없으므로 Anthropic 모델 ID로 fallback
        model_id = settings.get_bedrock_model_id("sonnet")
        assert model_id == "claude-sonnet-4-5-20250929"


# ===================================================================
# LLMClient — Anthropic 모드 테스트
# ===================================================================


class TestLLMClientAnthropicMode:
    """Anthropic 직접 API 모드에서 LLMClient 동작을 검증한다."""

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_anthropic_provider_default(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """기본 프로바이더는 anthropic이다."""
        # Settings mock 설정
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_model_id.return_value = "claude-sonnet-4-5-20250929"
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        assert client.provider == "anthropic"
        assert client.model_id == "claude-sonnet-4-5-20250929"

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_model_override(self, mock_settings: MagicMock, mock_anthropic: MagicMock) -> None:
        """model_override로 모델 ID를 직접 지정할 수 있다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(
            agent_name="content_analyzer",
            model_override="custom-model-v99",
        )
        assert client.model_id == "custom-model-v99"

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    async def test_generate_calls_anthropic_api(
        self, mock_settings: MagicMock, mock_anthropic_cls: MagicMock
    ) -> None:
        """generate()가 Anthropic API를 올바르게 호출한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        # Anthropic 응답 mock
        mock_text_block = MagicMock()
        mock_text_block.text = "분석 결과입니다."
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_cls.return_value = mock_client_instance

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        result = await client.generate(
            system_prompt="시스템 프롬프트",
            user_message="사용자 메시지",
        )

        assert result == "분석 결과입니다."
        mock_client_instance.messages.create.assert_called_once()

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    async def test_generate_json_parses_response(
        self, mock_settings: MagicMock, mock_anthropic_cls: MagicMock
    ) -> None:
        """generate_json()이 JSON 응답을 올바르게 파싱한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        json_response = '{"key": "value", "score": 0.95}'
        mock_text_block = MagicMock()
        mock_text_block.text = json_response
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_cls.return_value = mock_client_instance

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        result = await client.generate_json(
            system_prompt="JSON으로 응답하라.",
            user_message="테스트",
        )

        assert result == {"key": "value", "score": 0.95}


# ===================================================================
# LLMClient — Bedrock 모드 테스트
# ===================================================================


class TestLLMClientBedrockMode:
    """AWS Bedrock 모드에서 LLMClient 동작을 검증한다."""

    @patch("src.agents.shared.llm_client.get_settings")
    def test_bedrock_provider_override(self, mock_settings: MagicMock) -> None:
        """provider_override="bedrock"으로 Bedrock 모드를 활성화한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"  # 설정은 anthropic이지만
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        # boto3 mock
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
            )
            assert client.provider == "bedrock"
            assert client.model_id == "anthropic.claude-sonnet-4-5-20250929-v2:0"

    @patch("src.agents.shared.llm_client.get_settings")
    def test_bedrock_model_override(self, mock_settings: MagicMock) -> None:
        """Bedrock 모드에서도 model_override가 동작한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
                model_override="custom-bedrock-model",
            )
            assert client.model_id == "custom-bedrock-model"

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_generate_bedrock_calls_invoke_model(self, mock_settings: MagicMock) -> None:
        """Bedrock generate()가 invoke_model을 올바르게 호출한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        # Bedrock 응답 mock — body는 StreamingBody처럼 read() 가능해야 함
        bedrock_response_body = json.dumps({"content": [{"text": "Bedrock 응답입니다."}]}).encode(
            "utf-8"
        )
        mock_body = io.BytesIO(bedrock_response_body)
        mock_invoke_response = {"body": mock_body}

        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = mock_invoke_response

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_bedrock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
            )

            result = await client.generate(
                system_prompt="시스템",
                user_message="메시지",
            )

            assert result == "Bedrock 응답입니다."
            mock_bedrock_client.invoke_model.assert_called_once()

            # invoke_model에 전달된 요청 본문 검증
            call_kwargs = mock_bedrock_client.invoke_model.call_args
            request_body = json.loads(call_kwargs.kwargs["body"])
            assert request_body["anthropic_version"] == "bedrock-2023-05-31"
            assert request_body["system"] == "시스템"
            assert request_body["messages"][0]["content"] == "메시지"


# ===================================================================
# LLMClient — 프로바이더 우선순위 테스트
# ===================================================================


class TestLLMClientProviderPriority:
    """프로바이더 결정 우선순위를 검증한다: override > 환경변수 > 설정."""

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_settings_provider_used_when_no_override(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """override/환경변수 없으면 settings의 provider를 사용한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        # 환경변수 LLM_PROVIDER가 없는 상태
        with patch.dict("os.environ", {}, clear=False):
            # LLM_PROVIDER 환경변수 제거
            import os

            os.environ.pop("LLM_PROVIDER", None)
            client = LLMClient(agent_name="content_analyzer")
            assert client.provider == "anthropic"

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_env_overrides_settings(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """환경변수 LLM_PROVIDER가 settings보다 우선한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"  # settings는 anthropic
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        # 환경변수로 anthropic 설정 (bedrock이 아닌 값으로 테스트)
        with patch.dict("os.environ", {"LLM_PROVIDER": "anthropic"}):
            client = LLMClient(agent_name="content_analyzer")
            # 환경변수 값이 사용됨
            assert client.provider == "anthropic"

    @patch("src.agents.shared.llm_client.get_settings")
    def test_override_trumps_env_and_settings(self, mock_settings: MagicMock) -> None:
        """provider_override가 환경변수와 settings보다 우선한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = MagicMock()

        with (
            patch.dict("os.environ", {"LLM_PROVIDER": "anthropic"}),
            patch.dict("sys.modules", {"boto3": mock_boto3}),
        ):
            from src.agents.shared.llm_client import LLMClient

            # override가 env보다 우선
            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
            )
            assert client.provider == "bedrock"


# ===================================================================
# LLMClient — JSON 파싱 테스트
# ===================================================================


class TestLLMClientJsonParsing:
    """_parse_json_response 정적 메서드를 검증한다."""

    def test_parse_plain_json(self) -> None:
        """순수 JSON 문자열을 파싱한다."""
        from src.agents.shared.llm_client import LLMClient

        result = LLMClient._parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_markdown_block(self) -> None:
        """마크다운 코드 블록 내 JSON을 파싱한다."""
        from src.agents.shared.llm_client import LLMClient

        text = '```json\n{"key": "value"}\n```'
        result = LLMClient._parse_json_response(text)
        assert result == {"key": "value"}

    def test_parse_json_with_whitespace(self) -> None:
        """앞뒤 공백이 있는 JSON을 파싱한다."""
        from src.agents.shared.llm_client import LLMClient

        result = LLMClient._parse_json_response('  \n{"key": "value"}\n  ')
        assert result == {"key": "value"}

    def test_parse_invalid_json_raises_error(self) -> None:
        """유효하지 않은 JSON은 JSONDecodeError를 발생시킨다."""
        from src.agents.shared.llm_client import LLMClient

        with pytest.raises(json.JSONDecodeError):
            LLMClient._parse_json_response("not json at all")

    def test_parse_nested_json(self) -> None:
        """중첩된 JSON 구조를 파싱한다."""
        from src.agents.shared.llm_client import LLMClient

        text = '{"outer": {"inner": [1, 2, 3]}, "score": 0.95}'
        result = LLMClient._parse_json_response(text)
        assert result["outer"]["inner"] == [1, 2, 3]
        assert result["score"] == 0.95


# ===================================================================
# LLMClient — Bedrock boto3 미설치 테스트
# ===================================================================


class TestLLMClientBoto3Missing:
    """boto3가 설치되지 않은 환경에서의 동작을 검증한다."""

    @patch("src.agents.shared.llm_client.get_settings")
    def test_bedrock_without_boto3_raises_import_error(self, mock_settings: MagicMock) -> None:
        """boto3 없이 Bedrock 모드 초기화 시 ImportError가 발생한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        # boto3 import를 실패하게 만듦
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
                    agent_name="content_analyzer",
                    provider_override="bedrock",
                )


# ===================================================================
# LLMClient — 커스텀 프로바이더 등록/해제 테스트
# ===================================================================


class TestLLMClientCustomProvider:
    """register_provider / unregister_provider를 통한 커스텀 프로바이더 동작을 검증한다."""

    def setup_method(self) -> None:
        """각 테스트 전 커스텀 프로바이더 레지스트리를 초기화한다."""
        from src.agents.shared.llm_client import LLMClient

        # 테스트 간 간섭 방지 — 기존 등록 제거
        LLMClient._custom_providers.clear()

    def teardown_method(self) -> None:
        """각 테스트 후 커스텀 프로바이더 레지스트리를 정리한다."""
        from src.agents.shared.llm_client import LLMClient

        LLMClient._custom_providers.clear()

    def test_register_provider_adds_to_registry(self) -> None:
        """register_provider()가 레지스트리에 프로바이더를 추가한다."""
        from src.agents.shared.llm_client import LLMClient

        mock_provider_cls = MagicMock()
        LLMClient.register_provider("test_provider", mock_provider_cls)

        assert "test_provider" in LLMClient._custom_providers
        assert LLMClient._custom_providers["test_provider"] is mock_provider_cls

    def test_unregister_provider_removes_from_registry(self) -> None:
        """unregister_provider()가 레지스트리에서 프로바이더를 제거한다."""
        from src.agents.shared.llm_client import LLMClient

        mock_provider_cls = MagicMock()
        LLMClient.register_provider("test_provider", mock_provider_cls)
        assert "test_provider" in LLMClient._custom_providers

        LLMClient.unregister_provider("test_provider")
        assert "test_provider" not in LLMClient._custom_providers

    def test_unregister_nonexistent_provider_does_not_raise(self) -> None:
        """존재하지 않는 프로바이더를 해제해도 예외가 발생하지 않는다."""
        from src.agents.shared.llm_client import LLMClient

        # 예외 없이 실행되어야 한다
        LLMClient.unregister_provider("nonexistent")

    @patch("src.agents.shared.llm_client.get_settings")
    def test_custom_provider_init_called(self, mock_settings: MagicMock) -> None:
        """커스텀 프로바이더로 LLMClient 생성 시 프로바이더 __init__이 호출된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        # 커스텀 프로바이더 mock 등록
        mock_provider_instance = MagicMock()
        mock_provider_cls = MagicMock(return_value=mock_provider_instance)

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        client = LLMClient(
            agent_name="content_analyzer",
            provider_override="test_local",
        )

        # 프로바이더 클래스가 model_id로 호출되었는지 확인
        mock_provider_cls.assert_called_once_with(model_id="sonnet")
        assert client.provider == "test_local"
        assert client.model_id == "sonnet"

    @patch("src.agents.shared.llm_client.get_settings")
    def test_custom_provider_model_override(self, mock_settings: MagicMock) -> None:
        """커스텀 프로바이더에서 model_override가 정상 동작한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        mock_provider_cls = MagicMock(return_value=MagicMock())

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        client = LLMClient(
            agent_name="content_analyzer",
            provider_override="test_local",
            model_override="custom-local-model",
        )

        mock_provider_cls.assert_called_once_with(model_id="custom-local-model")
        assert client.model_id == "custom-local-model"

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_custom_provider_generate_dispatches(self, mock_settings: MagicMock) -> None:
        """generate()가 커스텀 프로바이더의 generate()를 호출한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        # 비동기 generate mock
        mock_provider_instance = MagicMock()
        mock_provider_instance.generate = AsyncMock(return_value="커스텀 응답")
        mock_provider_cls = MagicMock(return_value=mock_provider_instance)

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        client = LLMClient(
            agent_name="content_analyzer",
            provider_override="test_local",
        )

        result = await client.generate(
            system_prompt="시스템 프롬프트",
            user_message="사용자 메시지",
        )

        assert result == "커스텀 응답"
        mock_provider_instance.generate.assert_called_once_with(
            "시스템 프롬프트", "사용자 메시지", 2048, 0.7
        )

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_custom_provider_generate_json_dispatches(self, mock_settings: MagicMock) -> None:
        """generate_json()이 커스텀 프로바이더를 통해 JSON 파싱까지 정상 동작한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "haiku",
            "max_tokens": 1024,
            "temperature": 0.3,
        }
        mock_settings.return_value = settings

        json_response = '{"topic": "스트레스", "score": 0.8}'
        mock_provider_instance = MagicMock()
        mock_provider_instance.generate = AsyncMock(return_value=json_response)
        mock_provider_cls = MagicMock(return_value=mock_provider_instance)

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        client = LLMClient(
            agent_name="content_analyzer",
            provider_override="test_local",
        )

        result = await client.generate_json(
            system_prompt="JSON으로 응답하라.",
            user_message="테스트",
        )

        assert result == {"topic": "스트레스", "score": 0.8}

    @patch("src.agents.shared.llm_client.get_settings")
    def test_env_selects_custom_provider(self, mock_settings: MagicMock) -> None:
        """LLM_PROVIDER 환경변수로 커스텀 프로바이더를 선택할 수 있다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        mock_provider_cls = MagicMock(return_value=MagicMock())

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        with patch.dict("os.environ", {"LLM_PROVIDER": "test_local"}):
            client = LLMClient(agent_name="content_analyzer")
            assert client.provider == "test_local"

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_unregistered_provider_falls_through_to_anthropic(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """등록되지 않은 프로바이더명은 기본 Anthropic으로 fallback한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_model_id.return_value = "claude-sonnet-4-5-20250929"
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        # 커스텀 프로바이더 미등록 상태에서 anthropic이 기본
        client = LLMClient(agent_name="content_analyzer")
        assert client.provider == "anthropic"

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_custom_provider_error_propagates(self, mock_settings: MagicMock) -> None:
        """커스텀 프로바이더의 generate() 예외가 그대로 전파된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        mock_provider_instance = MagicMock()
        mock_provider_instance.generate = AsyncMock(
            side_effect=ConnectionError("Ollama 서버 연결 실패")
        )
        mock_provider_cls = MagicMock(return_value=mock_provider_instance)

        from src.agents.shared.llm_client import LLMClient

        LLMClient.register_provider("test_local", mock_provider_cls)

        client = LLMClient(
            agent_name="content_analyzer",
            provider_override="test_local",
        )

        with pytest.raises(ConnectionError, match="Ollama 서버 연결 실패"):
            await client.generate(
                system_prompt="시스템",
                user_message="메시지",
            )


# ===================================================================
# Settings — OpenAI 모델 ID 테스트
# ===================================================================


class TestSettingsOpenAIModelId:
    """Settings의 OpenAI 모델 ID 조회를 검증한다."""

    def test_get_openai_model_id_sonnet(self, test_settings: Settings) -> None:
        """sonnet 키로 OpenAI 모델 ID를 조회한다."""
        model_id = test_settings.get_openai_model_id("sonnet")
        assert model_id == "gpt-4o-mini"

    def test_get_openai_model_id_opus(self, test_settings: Settings) -> None:
        """opus 키로 OpenAI 모델 ID를 조회한다."""
        model_id = test_settings.get_openai_model_id("opus")
        assert model_id == "gpt-4o"

    def test_get_openai_model_id_haiku(self, test_settings: Settings) -> None:
        """haiku 키로 OpenAI 모델 ID를 조회한다."""
        model_id = test_settings.get_openai_model_id("haiku")
        assert model_id == "gpt-4o-mini"

    def test_get_openai_model_id_env_override(self, test_settings: Settings) -> None:
        """환경변수 LLM_OPENAI_MODEL_SONNET으로 오버라이드 가능하다."""
        with patch.dict(
            "os.environ",
            {"LLM_OPENAI_MODEL_SONNET": "custom-openai-model"},
        ):
            model_id = test_settings.get_openai_model_id("sonnet")
            assert model_id == "custom-openai-model"

    def test_get_openai_model_id_fallback_when_missing(self, tmp_path: Path) -> None:
        """openai_models에 키가 없으면 gpt-4o-mini로 fallback한다."""
        yaml_without_openai_models = """\
app:
  name: test
  version: "0.1.0"
llm:
  provider: anthropic
  models:
    sonnet: "claude-sonnet-4-5-20250929"
  default_max_tokens: 4096
  temperature:
    default: 0.7
agents: {}
pipeline:
  max_retries: 2
  tier1_timeout_seconds: 15
api:
  timeout: 5
  max_retries: 3
features: {}
prompts:
  base_dir: "prompts"
  versions:
    default: "1.0.0"
"""
        config_file = tmp_path / "no_openai.yaml"
        config_file.write_text(yaml_without_openai_models)
        settings = Settings(config_path=config_file)
        model_id = settings.get_openai_model_id("sonnet")
        assert model_id == "gpt-4o-mini"


# ===================================================================
# LLMClient — OpenAI 모드 테스트
# ===================================================================


class TestLLMClientOpenAIMode:
    """OpenAI 모드에서 LLMClient 동작을 검증한다."""

    @patch("src.agents.shared.llm_client.get_settings")
    def test_openai_provider_override(self, mock_settings: MagicMock) -> None:
        """provider_override='openai'로 OpenAI 모드를 활성화한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="openai",
            )
            assert client.provider == "openai"
            assert client.model_id == "gpt-4o-mini"

    @patch("src.agents.shared.llm_client.get_settings")
    def test_openai_model_override(self, mock_settings: MagicMock) -> None:
        """OpenAI 모드에서 model_override가 동작한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = MagicMock()

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="openai",
                model_override="gpt-4-turbo",
            )
            assert client.model_id == "gpt-4-turbo"

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_generate_openai_calls_api(self, mock_settings: MagicMock) -> None:
        """generate()가 OpenAI API를 올바르게 호출한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        # OpenAI 응답 mock
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
                agent_name="content_analyzer",
                provider_override="openai",
            )

            result = await client.generate(
                system_prompt="시스템 프롬프트",
                user_message="사용자 메시지",
            )

            assert result == "OpenAI 응답입니다."
            mock_client_instance.chat.completions.create.assert_called_once()

            # API 호출 파라미터 검증
            call_kwargs = mock_client_instance.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o-mini"
            assert call_kwargs["max_tokens"] == 2048
            assert call_kwargs["temperature"] == 0.7
            assert call_kwargs["messages"][0] == {
                "role": "system",
                "content": "시스템 프롬프트",
            }
            assert call_kwargs["messages"][1] == {
                "role": "user",
                "content": "사용자 메시지",
            }

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_generate_json_openai(self, mock_settings: MagicMock) -> None:
        """OpenAI 모드에서 generate_json()이 JSON을 올바르게 파싱한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        mock_message = MagicMock()
        mock_message.content = '{"key": "value", "score": 0.9}'
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 80
        mock_usage.completion_tokens = 30
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
                agent_name="content_analyzer",
                provider_override="openai",
            )

            result = await client.generate_json(
                system_prompt="JSON으로 응답하라.",
                user_message="테스트",
            )

            assert result == {"key": "value", "score": 0.9}


# ===================================================================
# LLMClient — 토큰 사용량 추적 테스트
# ===================================================================


class TestLLMClientTokenUsage:
    """토큰 사용량 추적 (last_usage, total_usage, _record_usage) 검증."""

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_initial_usage_is_none(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """초기 상태에서 last_usage는 None이다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        assert client.last_usage is None

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_initial_total_usage_is_zero(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """초기 상태에서 total_usage는 모든 값이 0이다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        total = client.total_usage
        assert total["input_tokens"] == 0
        assert total["output_tokens"] == 0
        assert total["total_tokens"] == 0

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    async def test_anthropic_records_token_usage(
        self, mock_settings: MagicMock, mock_anthropic_cls: MagicMock
    ) -> None:
        """Anthropic generate() 호출 후 토큰 사용량이 기록된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        mock_text_block = MagicMock()
        mock_text_block.text = "응답"
        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 200

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_cls.return_value = mock_client_instance

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        await client.generate(system_prompt="시스템", user_message="메시지")

        assert client.last_usage is not None
        assert client.last_usage["input_tokens"] == 500
        assert client.last_usage["output_tokens"] == 200
        assert client.last_usage["total_tokens"] == 700

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_bedrock_records_token_usage(
        self, mock_settings: MagicMock
    ) -> None:
        """Bedrock generate() 호출 후 토큰 사용량이 기록된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        bedrock_response_body = json.dumps({
            "content": [{"text": "Bedrock 응답"}],
            "usage": {"input_tokens": 300, "output_tokens": 150},
        }).encode("utf-8")
        mock_body = io.BytesIO(bedrock_response_body)
        mock_invoke_response = {"body": mock_body}

        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = mock_invoke_response

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_bedrock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
            )

            await client.generate(system_prompt="시스템", user_message="메시지")

            assert client.last_usage is not None
            assert client.last_usage["input_tokens"] == 300
            assert client.last_usage["output_tokens"] == 150
            assert client.last_usage["total_tokens"] == 450

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_openai_records_token_usage(
        self, mock_settings: MagicMock
    ) -> None:
        """OpenAI generate() 호출 후 토큰 사용량이 기록된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        mock_message = MagicMock()
        mock_message.content = "OpenAI 응답"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 400
        mock_usage.completion_tokens = 180
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
                agent_name="content_analyzer",
                provider_override="openai",
            )

            await client.generate(system_prompt="시스템", user_message="메시지")

            assert client.last_usage is not None
            assert client.last_usage["input_tokens"] == 400
            assert client.last_usage["output_tokens"] == 180
            assert client.last_usage["total_tokens"] == 580

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    async def test_total_usage_accumulates(
        self, mock_settings: MagicMock, mock_anthropic_cls: MagicMock
    ) -> None:
        """여러 번 generate() 호출 시 total_usage가 누적된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        # 첫 번째 응답
        mock_text1 = MagicMock()
        mock_text1.text = "응답1"
        mock_response1 = MagicMock()
        mock_response1.content = [mock_text1]
        mock_response1.usage.input_tokens = 100
        mock_response1.usage.output_tokens = 50

        # 두 번째 응답
        mock_text2 = MagicMock()
        mock_text2.text = "응답2"
        mock_response2 = MagicMock()
        mock_response2.content = [mock_text2]
        mock_response2.usage.input_tokens = 200
        mock_response2.usage.output_tokens = 80

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )
        mock_anthropic_cls.return_value = mock_client_instance

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")

        await client.generate(system_prompt="시스템", user_message="메시지1")
        await client.generate(system_prompt="시스템", user_message="메시지2")

        # last_usage는 마지막 호출 결과
        assert client.last_usage["input_tokens"] == 200
        assert client.last_usage["output_tokens"] == 80

        # total_usage는 누적
        total = client.total_usage
        assert total["input_tokens"] == 300   # 100 + 200
        assert total["output_tokens"] == 130  # 50 + 80
        assert total["total_tokens"] == 430   # 150 + 280

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    async def test_reset_total_usage(
        self, mock_settings: MagicMock, mock_anthropic_cls: MagicMock
    ) -> None:
        """reset_total_usage()가 누적 사용량을 초기화한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        mock_text = MagicMock()
        mock_text.text = "응답"
        mock_response = MagicMock()
        mock_response.content = [mock_text]
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 200

        mock_client_instance = MagicMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_response)
        mock_anthropic_cls.return_value = mock_client_instance

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        await client.generate(system_prompt="시스템", user_message="메시지")

        assert client.total_usage["total_tokens"] == 700

        client.reset_total_usage()

        total = client.total_usage
        assert total["input_tokens"] == 0
        assert total["output_tokens"] == 0
        assert total["total_tokens"] == 0
        # last_usage는 리셋되지 않음
        assert client.last_usage is not None

    @patch("src.agents.shared.llm_client.anthropic.AsyncAnthropic")
    @patch("src.agents.shared.llm_client.get_settings")
    def test_total_usage_returns_copy(
        self, mock_settings: MagicMock, mock_anthropic: MagicMock
    ) -> None:
        """total_usage는 내부 dict의 복사본을 반환한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "model_id": "claude-sonnet-4-5-20250929",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        from src.agents.shared.llm_client import LLMClient

        client = LLMClient(agent_name="content_analyzer")
        total1 = client.total_usage
        total1["input_tokens"] = 99999  # 외부에서 변경

        # 내부 상태는 영향 없음
        total2 = client.total_usage
        assert total2["input_tokens"] == 0

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_openai_no_usage_does_not_crash(
        self, mock_settings: MagicMock
    ) -> None:
        """OpenAI 응답에 usage가 None이어도 오류 없이 동작한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_openai_model_id.return_value = "gpt-4o-mini"
        mock_settings.return_value = settings

        mock_message = MagicMock()
        mock_message.content = "응답"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = None  # usage 없음

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI.return_value = mock_client_instance

        with patch.dict("sys.modules", {"openai": mock_openai}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="openai",
            )

            result = await client.generate(system_prompt="시스템", user_message="메시지")

            assert result == "응답"
            # usage가 없으면 last_usage는 변경되지 않음
            assert client.last_usage is None

    @patch("src.agents.shared.llm_client.get_settings")
    async def test_bedrock_no_usage_records_zero(
        self, mock_settings: MagicMock
    ) -> None:
        """Bedrock 응답에 usage 필드가 없어도 0으로 기록된다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        settings.get_bedrock_model_id.return_value = "anthropic.claude-sonnet-4-5-20250929-v2:0"
        settings.bedrock_region = "ap-northeast-2"
        settings.bedrock_config = {"region": "ap-northeast-2"}
        mock_settings.return_value = settings

        # usage 필드 없는 응답
        bedrock_response_body = json.dumps({
            "content": [{"text": "응답"}],
        }).encode("utf-8")
        mock_body = io.BytesIO(bedrock_response_body)
        mock_invoke_response = {"body": mock_body}

        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = mock_invoke_response

        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_bedrock_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from src.agents.shared.llm_client import LLMClient

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="bedrock",
            )

            await client.generate(system_prompt="시스템", user_message="메시지")

            assert client.last_usage is not None
            assert client.last_usage["input_tokens"] == 0
            assert client.last_usage["output_tokens"] == 0

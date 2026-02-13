"""
Ollama 프로바이더 전용 테스트 — 로컬 개발 전용.

이 파일은 dev/ 폴더에 위치하며 운영 배포 시 제거 가능하다.
운영 테스트(tests/)와 독립적이며, Ollama 프로바이더의 단위 테스트를 포함한다.

실행 방법:
    # Ollama 서버 실행 불필요 (httpx mock 사용)
    python3 -m pytest dev/test_ollama.py -v

    # 실제 Ollama 서버 연동 테스트 (서버 실행 필요)
    OLLAMA_LIVE_TEST=1 python3 -m pytest dev/test_ollama.py -v -k "live"
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml

# === 픽스처 ===


@pytest.fixture(autouse=True)
def _cleanup_custom_providers() -> Any:  # noqa: ANN401
    """각 테스트 후 LLMClient 커스텀 프로바이더 레지스트리를 정리한다."""
    yield
    from src.agents.shared.llm_client import LLMClient

    LLMClient._custom_providers.clear()


@pytest.fixture()
def mock_ollama_config(tmp_path: Path) -> Path:
    """테스트용 ollama_config.yaml을 생성한다."""
    config = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "timeout": 60,
            "models": {
                "haiku": "gemma2:2b",
                "sonnet": "llama3.2",
                "opus": "llama3.2:latest",
            },
        }
    }
    config_file = tmp_path / "ollama_config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True)
    return config_file


# === OllamaProvider 단위 테스트 ===


class TestOllamaProviderInit:
    """OllamaProvider 초기화 테스트."""

    def test_init_with_model_key_mapping(self, mock_ollama_config: Path) -> None:
        """모델 키(sonnet)가 Ollama 모델명(llama3.2)으로 매핑된다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")
            assert provider.model_id == "llama3.2"

    def test_init_with_direct_model_name(self, mock_ollama_config: Path) -> None:
        """매핑에 없는 모델명은 그대로 사용된다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="mistral:7b")
            assert provider.model_id == "mistral:7b"

    def test_init_with_haiku_mapping(self, mock_ollama_config: Path) -> None:
        """haiku 키가 gemma2:2b로 매핑된다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="haiku")
            assert provider.model_id == "gemma2:2b"

    def test_init_default_base_url(self, mock_ollama_config: Path) -> None:
        """기본 base_url은 localhost:11434이다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")
            assert provider.base_url == "http://localhost:11434"

    def test_init_env_override_base_url(self, mock_ollama_config: Path) -> None:
        """OLLAMA_BASE_URL 환경변수로 base_url을 오버라이드할 수 있다."""
        with (
            patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config),
            patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://remote:8080"}),
        ):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")
            assert provider.base_url == "http://remote:8080"

    def test_init_env_override_timeout(self, mock_ollama_config: Path) -> None:
        """OLLAMA_TIMEOUT 환경변수로 타임아웃을 오버라이드할 수 있다."""
        with (
            patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config),
            patch.dict(os.environ, {"OLLAMA_TIMEOUT": "300"}),
        ):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")
            assert provider._timeout == 300

    def test_init_without_config_file(self, tmp_path: Path) -> None:
        """설정 파일이 없으면 기본값을 사용한다."""
        nonexistent = tmp_path / "nonexistent.yaml"
        with patch("dev.ollama_provider._CONFIG_PATH", nonexistent):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="llama3.2")
            # 매핑 없으므로 model_id 그대로
            assert provider.model_id == "llama3.2"
            assert provider.base_url == "http://localhost:11434"
            assert provider._timeout == 120


class TestOllamaProviderGenerate:
    """OllamaProvider.generate() 테스트 (httpx mock)."""

    @pytest.mark.asyncio
    async def test_generate_success(self, mock_ollama_config: Path) -> None:
        """정상적인 응답을 반환한다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")

        # httpx.AsyncClient mock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Ollama 응답입니다."}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("dev.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = await provider.generate(
                system_prompt="시스템",
                user_message="메시지",
                max_tokens=1024,
                temperature=0.7,
            )

        assert result == "Ollama 응답입니다."

        # POST 요청 검증
        call_kwargs = mock_client.post.call_args
        assert "/v1/chat/completions" in call_kwargs.args[0]
        payload = call_kwargs.kwargs["json"]
        assert payload["model"] == "llama3.2"
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["max_tokens"] == 1024
        assert payload["temperature"] == 0.7
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_generate_connection_error(self, mock_ollama_config: Path) -> None:
        """Ollama 서버 연결 실패 시 httpx.ConnectError가 전파된다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("연결 실패")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("dev.ollama_provider.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(httpx.ConnectError, match="연결 실패"),
        ):
            await provider.generate(
                system_prompt="시스템",
                user_message="메시지",
                max_tokens=1024,
                temperature=0.7,
            )

    @pytest.mark.asyncio
    async def test_generate_http_error(self, mock_ollama_config: Path) -> None:
        """HTTP 에러 응답 시 httpx.HTTPStatusError가 전파된다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import OllamaProvider

            provider = OllamaProvider(model_id="sonnet")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404),
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("dev.ollama_provider.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await provider.generate(
                system_prompt="시스템",
                user_message="메시지",
                max_tokens=1024,
                temperature=0.7,
            )


class TestOllamaConfigLoading:
    """ollama_config.yaml 설정 로드 테스트."""

    def test_load_config_from_file(self, mock_ollama_config: Path) -> None:
        """설정 파일에서 올바르게 값을 로드한다."""
        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_provider import _load_ollama_config

            config = _load_ollama_config()

        assert config["base_url"] == "http://localhost:11434"
        assert config["timeout"] == 60
        assert config["models"]["haiku"] == "gemma2:2b"
        assert config["models"]["sonnet"] == "llama3.2"

    def test_load_config_missing_file_uses_defaults(self, tmp_path: Path) -> None:
        """설정 파일이 없으면 기본값을 반환한다."""
        nonexistent = tmp_path / "nonexistent.yaml"
        with patch("dev.ollama_provider._CONFIG_PATH", nonexistent):
            from dev.ollama_provider import _load_ollama_config

            config = _load_ollama_config()

        assert config["base_url"] == "http://localhost:11434"
        assert config["timeout"] == 120
        assert config["models"] == {}


class TestOllamaBootstrap:
    """ollama_bootstrap.py 등록/해제 테스트."""

    def test_register_ollama(self) -> None:
        """register_ollama()가 LLMClient에 ollama 프로바이더를 등록한다."""
        from dev.ollama_bootstrap import register_ollama
        from src.agents.shared.llm_client import LLMClient

        register_ollama()
        assert "ollama" in LLMClient._custom_providers

    def test_unregister_ollama(self) -> None:
        """unregister_ollama()가 LLMClient에서 ollama 프로바이더를 제거한다."""
        from dev.ollama_bootstrap import register_ollama, unregister_ollama
        from src.agents.shared.llm_client import LLMClient

        register_ollama()
        assert "ollama" in LLMClient._custom_providers

        unregister_ollama()
        assert "ollama" not in LLMClient._custom_providers


# === LLMClient + Ollama 통합 테스트 (mock) ===


class TestLLMClientOllamaIntegration:
    """LLMClient에서 Ollama 프로바이더를 사용하는 통합 테스트 (mock)."""

    @patch("src.agents.shared.llm_client.get_settings")
    def test_llm_client_with_ollama_provider(
        self, mock_settings: MagicMock, mock_ollama_config: Path
    ) -> None:
        """LLMClient가 등록된 Ollama 프로바이더를 올바르게 초기화한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_bootstrap import register_ollama
            from src.agents.shared.llm_client import LLMClient

            register_ollama()

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="ollama",
            )

            assert client.provider == "ollama"
            # sonnet → llama3.2 매핑 확인
            assert client.model_id == "sonnet"  # LLMClient는 키를 전달
            # 실제 매핑은 OllamaProvider 내부에서 수행

    @patch("src.agents.shared.llm_client.get_settings")
    @pytest.mark.asyncio
    async def test_llm_client_generate_with_ollama(
        self, mock_settings: MagicMock, mock_ollama_config: Path
    ) -> None:
        """LLMClient.generate()가 Ollama를 통해 응답을 생성한다."""
        settings = MagicMock()
        settings.llm_provider = "anthropic"
        settings.get_agent_config.return_value = {
            "model": "sonnet",
            "max_tokens": 2048,
            "temperature": 0.7,
        }
        mock_settings.return_value = settings

        with patch("dev.ollama_provider._CONFIG_PATH", mock_ollama_config):
            from dev.ollama_bootstrap import register_ollama
            from src.agents.shared.llm_client import LLMClient

            register_ollama()

            client = LLMClient(
                agent_name="content_analyzer",
                provider_override="ollama",
            )

        # httpx mock — 실제 Ollama 서버 불필요
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"topic": "테스트"}'}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.post.return_value = mock_response
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)

        with patch("dev.ollama_provider.httpx.AsyncClient", return_value=mock_http_client):
            result = await client.generate(
                system_prompt="시스템",
                user_message="메시지",
            )

        assert result == '{"topic": "테스트"}'

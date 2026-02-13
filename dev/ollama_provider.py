"""
Ollama 프로바이더 — 로컬 개발/테스트 전용.

Ollama의 OpenAI 호환 API(/v1/chat/completions)를 통해 로컬 LLM을 호출한다.
이 파일은 dev/ 폴더에 위치하며 운영 배포 시 제거 가능하다.

운영 코드(src/)와 완전히 분리되어 있으므로, dev/ 폴더 삭제만으로 제거 가능.
LLMClient.register_provider()를 통해 플러그인으로 등록한다.

사용법:
    from dev.ollama_bootstrap import register_ollama
    register_ollama()
    # 이후 LLM_PROVIDER=ollama 또는 provider_override="ollama"로 사용
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

# Ollama 설정 파일 경로 (dev/ollama_config.yaml)
_CONFIG_PATH = Path(__file__).parent / "ollama_config.yaml"


def _load_ollama_config() -> dict[str, Any]:
    """
    dev/ollama_config.yaml에서 Ollama 설정을 로드한다.

    설정 파일이 없으면 기본값을 사용한다.
    환경변수로 개별 값을 오버라이드할 수 있다.
    """
    config: dict[str, Any] = {}

    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            config = raw.get("ollama", {})

    # 환경변수 오버라이드
    config.setdefault("base_url", "http://localhost:11434")
    config["base_url"] = os.getenv("OLLAMA_BASE_URL", config["base_url"])
    config.setdefault("timeout", 120)
    config["timeout"] = int(os.getenv("OLLAMA_TIMEOUT", str(config["timeout"])))
    config.setdefault("models", {})

    return config


class OllamaProvider:
    """
    Ollama OpenAI 호환 API를 통한 LLM 프로바이더.

    LLMClient.register_provider("ollama", OllamaProvider)로 등록하고,
    provider_override="ollama" 또는 LLM_PROVIDER=ollama로 활성화한다.

    model_id에는 에이전트의 모델 키(예: "sonnet")가 전달된다.
    ollama_config.yaml의 models 매핑을 통해 실제 Ollama 모델명으로 변환한다.
    """

    def __init__(self, model_id: str) -> None:
        """
        Ollama 프로바이더를 초기화한다.

        Args:
            model_id: 에이전트의 모델 키 (예: "sonnet", "haiku", "opus")
                      또는 직접 Ollama 모델명 (예: "llama3.2", "gemma2:2b")
        """
        config = _load_ollama_config()

        self._base_url: str = config["base_url"]
        self._timeout: int = config["timeout"]

        # 모델 매핑: 에이전트 키 → Ollama 모델명
        models_map: dict[str, str] = config.get("models", {})
        self._model_id = models_map.get(model_id, model_id)

    @property
    def model_id(self) -> str:
        """현재 사용 중인 Ollama 모델명."""
        return self._model_id

    @property
    def base_url(self) -> str:
        """Ollama 서버 URL."""
        return self._base_url

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """
        Ollama /v1/chat/completions 엔드포인트를 호출하여 텍스트를 생성한다.

        OpenAI 호환 API를 사용하므로, Ollama가 지원하는 모든 모델에서 동작한다.

        Args:
            system_prompt: 시스템 프롬프트
            user_message: 사용자 메시지
            max_tokens: 최대 토큰 수
            temperature: 샘플링 온도

        Returns:
            LLM이 생성한 텍스트 응답

        Raises:
            httpx.ConnectError: Ollama 서버에 연결할 수 없을 때
            httpx.HTTPStatusError: API 호출 실패 시
            KeyError: 응답 형식이 예상과 다를 때
        """
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        result = response.json()
        return str(result["choices"][0]["message"]["content"])

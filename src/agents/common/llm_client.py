# agents/common/llm_client.py
"""
Ollama LLM 클라이언트 래퍼 (테스트 모드용)

설치 필요 라이브러리 (선택):
    pip install openai
Ollama는 OpenAI API와 호환되므로 openai 라이브러리를 통해 접근 가능합니다.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama를 활용한 로컬 모델 클라이언트 (OpenAI API 호환)"""

    def __init__(
        self,
        model_name: str = "llama3",  # Ollama에 설치된 기본 모델명 (예: llama3, qwen)
        base_url: str = "http://localhost:11434/v1",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        verbose: bool = True,
    ):
        self.model_name = model_name
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.verbose = verbose

        try:
            from openai import AsyncOpenAI, OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key="ollama")
            self._async_client = AsyncOpenAI(base_url=self.base_url, api_key="ollama")
        except ImportError:
            logger.warning("openai 패키지가 없습니다. pip install openai 필수")
            self._client = None
            self._async_client = None

        if self.verbose:
            print(f"✅ Ollama 클라이언트 생성 완료: {self.base_url} (모델: {self.model_name})")

    def generate(
        self, prompt: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None
    ) -> str:
        """텍스트 생성 (동기)"""
        if not self._client:
            return "Ollama client not initialized."

        temp_val = temperature if temperature is not None else self.temperature

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self.max_tokens,
            temperature=temp_val,
        )
        return response.choices[0].message.content

    async def agenerate(
        self, prompt: str, max_tokens: Optional[int] = None, temperature: Optional[float] = None
    ) -> str:
        """텍스트 생성 (비동기)"""
        if not self._async_client:
            return "Ollama client not initialized."

        temp_val = temperature if temperature is not None else self.temperature

        response = await self._async_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens or self.max_tokens,
            temperature=temp_val,
        )
        return response.choices[0].message.content

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """채팅 형식"""
        if not self._client:
            return "Ollama client not initialized."

        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
        )
        return response.choices[0].message.content


class OllamaChatWrapper:
    """OpenAI/Anthropic 호환 인터페이스 래퍼"""

    def __init__(self, ollama_client: OllamaClient):
        self.ollama_client = ollama_client
        self.messages = self
        self.chat = self

    def create(
        self,
        messages: List[Dict[str, str]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs,
    ):
        response_text = self.ollama_client.chat(
            messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        return OllamaResponse(response_text)

    @property
    def completions(self):
        return self


class OllamaResponse:
    """응답 래퍼"""

    def __init__(self, text: str):
        self.content = [type("Content", (), {"text": text, "type": "text"})()]
        self.choices = [
            type(
                "Choice",
                (),
                {
                    "message": type("Message", (), {"content": text, "role": "assistant"})(),
                    "index": 0,
                },
            )()
        ]


def create_ollama_client(
    model_name: str = "llama3",
    max_tokens: int = 1024,
    temperature: float = 0.7,
    verbose: bool = True,
) -> OllamaChatWrapper:
    """Ollama 클라이언트 생성"""
    return OllamaChatWrapper(
        OllamaClient(model_name, "http://localhost:11434/v1", max_tokens, temperature, verbose)
    )

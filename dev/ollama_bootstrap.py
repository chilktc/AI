"""
Ollama 프로바이더 부트스트랩 — LLMClient에 등록.

이 파일은 dev/ 폴더에 위치하며 운영 배포 시 제거 가능하다.
앱 시작 시 또는 테스트 전에 register_ollama()를 호출하면
LLMClient에서 Ollama 프로바이더를 사용할 수 있다.

사용법:
    # 방법 1: 앱 시작 시 (main.py 등)
    from dev.ollama_bootstrap import register_ollama
    register_ollama()

    # 방법 2: 환경변수 + pytest conftest.py
    # conftest.py에서 register_ollama()를 fixture로 호출

    # 방법 3: CLI에서 직접
    # LLM_PROVIDER=ollama python3 -m pytest tests/ -v
"""

from __future__ import annotations


def register_ollama() -> None:
    """
    LLMClient에 Ollama 프로바이더를 등록한다.

    등록 후 provider_override="ollama" 또는 환경변수 LLM_PROVIDER=ollama로
    Ollama 모드를 활성화할 수 있다.
    """
    from dev.ollama_provider import OllamaProvider
    from src.agents.shared.llm_client import LLMClient

    LLMClient.register_provider("ollama", OllamaProvider)


def unregister_ollama() -> None:
    """
    LLMClient에서 Ollama 프로바이더를 제거한다 (테스트 정리용).
    """
    from src.agents.shared.llm_client import LLMClient

    LLMClient.unregister_provider("ollama")

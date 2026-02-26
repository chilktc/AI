import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# Ollama 설정
# =============================================================================
OLLAMA_MODEL = "gpt-oss:20b"  # 로컬에 설치된 Ollama 모델 이름

# =============================================================================
# Fixtures
# =============================================================================

_ollama_client = None


@pytest.fixture(scope="session")
def llm_client():
    """Ollama를 바라보는 실제 LLMClient (세션 전체 공유)"""
    global _ollama_client

    if _ollama_client is None:
        import os

        from src.agents.shared.llm_client import LLMClient

        # OpenAI 라이브러리가 로컬 Ollama를 볼 수 있도록 환경변수 설정
        os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
        os.environ["OPENAI_API_KEY"] = "ollama"
        # LLMClient 생성 시 model_override로 OLLAMA_MODEL을 넘겨줍니다.
        _ollama_client = LLMClient(
            agent_name="intent_classifier", provider_override="openai", model_override=OLLAMA_MODEL
        )

    return _ollama_client

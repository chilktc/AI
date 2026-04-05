import enum
import os
import sys
import typing

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# Python 3.11+ 타입 백포트 (로컬 3.9 환경 호환)
# 프로젝트 대상: Python 3.11+ / 로컬 시스템: Python 3.9
# =============================================================================
if not hasattr(enum, "StrEnum"):

    class _StrEnum(str, enum.Enum):
        pass

    enum.StrEnum = _StrEnum  # type: ignore[attr-defined]

if not hasattr(typing, "Self"):
    typing.Self = typing.TypeVar("Self")  # type: ignore[attr-defined]

# =============================================================================
# 외부 API 안전장치
# =============================================================================


@pytest.fixture(autouse=True, scope="session")
def _guard_external_api():
    """테스트 중 실수로 Anthropic/OpenAI 외부 API를 호출하지 않도록 API 키를 일시 제거.

    Ollama(localhost)는 OPENAI_BASE_URL로 리다이렉트되므로 영향 없음.
    """
    saved: dict[str, str | None] = {}
    for key in ("ANTHROPIC_API_KEY",):
        saved[key] = os.environ.pop(key, None)
    yield
    for key, val in saved.items():
        if val is not None:
            os.environ[key] = val


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
        from src.agents.shared.llm_client import LLMClient

        # OpenAI 라이브러리가 로컬 Ollama를 볼 수 있도록 환경변수 설정
        os.environ["OPENAI_BASE_URL"] = "http://localhost:11434/v1"
        os.environ["OPENAI_API_KEY"] = "ollama"
        # LLMClient 생성 시 model_override로 OLLAMA_MODEL을 넘겨줍니다.
        _ollama_client = LLMClient(
            agent_name="intent_classifier", provider_override="openai", model_override=OLLAMA_MODEL
        )

    return _ollama_client

"""
라이브 테스트 공통 인프라 — 멀티 프로바이더 셋업, 헬스체크, 출력 포맷팅.

모든 라이브 테스트 스크립트가 공유하는 유틸리티 함수.
Ollama(로컬), Anthropic API, AWS Bedrock 프로바이더를 모두 지원한다.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any

# ────────────────────────────────────────────
# 프로바이더 셋업
# ────────────────────────────────────────────


def setup_provider(provider: str, model_override: str | None = None) -> None:
    """
    프로바이더에 따라 LLM 환경을 설정한다.

    - ollama: register_ollama() + 환경변수 LLM_PROVIDER=ollama
    - anthropic: ANTHROPIC_API_KEY 확인 + 환경변수 LLM_PROVIDER=anthropic
    - bedrock: AWS 인증 확인 + 환경변수 LLM_PROVIDER=bedrock

    모든 프로바이더 공통으로 Settings 싱글톤을 리셋하여
    환경변수 변경이 반영되도록 한다.

    Args:
        provider: 프로바이더 이름 (ollama, anthropic, bedrock)
        model_override: 모델 오버라이드 (예: "mistral:7b", "claude-sonnet-4-20250514")
    """
    # 프로바이더 환경변수 설정
    os.environ["LLM_PROVIDER"] = provider

    # 모델 오버라이드 설정 (설정 시 모든 에이전트에 적용)
    if model_override:
        os.environ["LLM_MODEL_SONNET"] = model_override
        os.environ["LLM_MODEL_HAIKU"] = model_override

    # Settings 싱글톤 리셋 — 환경변수 변경 반영
    import config.loader

    config.loader._settings_instance = None

    if provider == "ollama":
        _setup_ollama()
    elif provider == "anthropic":
        _setup_anthropic()
    elif provider == "bedrock":
        _setup_bedrock()
    else:
        print_banner(f"[ERROR] 알 수 없는 프로바이더: {provider}", color="red")
        print("  지원 프로바이더: ollama, anthropic, bedrock")
        sys.exit(1)


def _setup_ollama() -> None:
    """Ollama 프로바이더를 LLMClient에 등록한다."""
    try:
        from dev.ollama_bootstrap import register_ollama

        register_ollama()
    except ImportError:
        print_banner("[ERROR] Ollama 프로바이더 파일을 찾을 수 없습니다.", color="red")
        print("  dev/ollama_provider.py, dev/ollama_bootstrap.py 파일이 필요합니다.")
        print("  docs/OLLAMA_SETUP.md를 참고하세요.")
        sys.exit(1)


def _setup_anthropic() -> None:
    """Anthropic API 키를 확인한다."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print_banner("[ERROR] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.", color="red")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)
    # 키 형식 기본 확인 (sk-ant- 접두사)
    if not api_key.startswith("sk-ant-"):
        print_banner("[WARNING] API 키 형식이 일반적이지 않습니다.", color="yellow")
        print(f"  키 접두사: {api_key[:10]}...")


def _setup_bedrock() -> None:
    """AWS Bedrock 인증을 확인한다."""
    try:
        import boto3  # type: ignore[import-untyped]

        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        print(f"  AWS 계정: {identity['Account']}")
        print(f"  ARN: {identity['Arn']}")
    except ImportError:
        print_banner("[ERROR] boto3가 설치되지 않았습니다.", color="red")
        print("  pip install boto3")
        sys.exit(1)
    except Exception as e:
        print_banner("[ERROR] AWS 인증 실패.", color="red")
        print(f"  {e}")
        print("  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY를 확인하세요.")
        sys.exit(1)


# ────────────────────────────────────────────
# 헬스체크
# ────────────────────────────────────────────


async def check_provider_health(provider: str) -> bool:
    """
    프로바이더별 연결 상태를 확인한다.

    Args:
        provider: 프로바이더 이름

    Returns:
        연결 성공 여부
    """
    if provider == "ollama":
        return await _check_ollama_health()
    elif provider == "anthropic":
        return _check_anthropic_health()
    elif provider == "bedrock":
        return _check_bedrock_health()
    return False


async def _check_ollama_health() -> bool:
    """Ollama 서버 연결을 확인한다."""
    try:
        import httpx

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base_url}/v1/models")
            if response.status_code == 200:
                models = response.json()
                model_names = [m.get("id", "unknown") for m in models.get("data", [])]
                print(f"  Ollama 서버 연결 성공 ({base_url})")
                print(f"  사용 가능한 모델: {', '.join(model_names) if model_names else '(없음)'}")
                return True
    except Exception as e:
        print_banner("[ERROR] Ollama 서버 연결 실패.", color="red")
        print(f"  {e}")
        print("  `ollama serve`를 실행하세요.")
    return False


def _check_anthropic_health() -> bool:
    """Anthropic API 키 존재를 확인한다."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        print(f"  Anthropic API 키 확인됨 (길이: {len(api_key)})")
        return True
    return False


def _check_bedrock_health() -> bool:
    """AWS Bedrock 인증을 확인한다."""
    try:
        import boto3  # type: ignore[import-untyped]

        sts = boto3.client("sts")
        sts.get_caller_identity()
        print("  AWS Bedrock 인증 확인됨")
        return True
    except Exception:
        return False


# ────────────────────────────────────────────
# 출력 포맷팅
# ────────────────────────────────────────────

# ANSI 컬러 코드
_COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def print_banner(text: str, color: str = "blue") -> None:
    """배너 형식으로 텍스트를 출력한다."""
    c = _COLORS.get(color, "")
    r = _COLORS["reset"]
    b = _COLORS["bold"]
    print(f"\n{b}{c}{'=' * 60}{r}")
    print(f"{b}{c} {text}{r}")
    print(f"{b}{c}{'=' * 60}{r}")


def print_section(title: str) -> None:
    """섹션 구분선을 출력한다."""
    c = _COLORS["cyan"]
    r = _COLORS["reset"]
    print(f"\n{c}--- {title} ---{r}")


def print_result(
    agent_name: str,
    provider: str,
    result: dict[str, Any],
    elapsed: float,
) -> None:
    """
    에이전트 실행 결과를 컬러 포맷팅으로 출력한다.

    Args:
        agent_name: 에이전트 이름
        provider: 사용된 프로바이더
        result: 에이전트 반환 dict (AgentState 부분)
        elapsed: 소요 시간 (초)
    """
    g = _COLORS["green"]
    r = _COLORS["reset"]
    b = _COLORS["bold"]

    print(f"\n{b}{g}[SUCCESS] {agent_name} ({provider}){r}")
    print(f"  소요 시간: {elapsed:.2f}초")
    print(f"  반환 필드: {list(result.keys())}")
    print()

    # 각 필드를 JSON pretty-print
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"  {b}{key}:{r}")
            formatted = json.dumps(value, ensure_ascii=False, indent=4)
            for line in formatted.split("\n"):
                print(f"    {line}")
        elif isinstance(value, str) and len(value) > 100:
            # 긴 텍스트는 요약
            print(f"  {b}{key}:{r} {value[:100]}... (총 {len(value)}자)")
        else:
            print(f"  {b}{key}:{r} {value}")


def print_error(agent_name: str, error: Exception) -> None:
    """
    에이전트 실행 에러를 출력한다.

    Args:
        agent_name: 에이전트 이름
        error: 발생한 예외
    """
    red = _COLORS["red"]
    r = _COLORS["reset"]
    b = _COLORS["bold"]

    print(f"\n{b}{red}[ERROR] {agent_name}{r}")
    print(f"  에러 타입: {type(error).__name__}")
    print(f"  에러 메시지: {error}")
    print()
    # 스택 트레이스 요약 (마지막 5줄)
    tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
    tb_text = "".join(tb_lines)
    lines = tb_text.strip().split("\n")
    if len(lines) > 10:
        print("  스택 트레이스 (마지막 10줄):")
        for line in lines[-10:]:
            print(f"    {line}")
    else:
        print("  스택 트레이스:")
        for line in lines:
            print(f"    {line}")


class Timer:
    """소요 시간 측정 컨텍스트 매니저."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.elapsed = time.perf_counter() - self._start

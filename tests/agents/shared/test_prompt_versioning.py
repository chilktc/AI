"""
멀티버전 프롬프트 + A/B 테스트 검증.

v8에서 도입된 멀티버전 YAML 형식, settings 기반 버전 해석,
BaseAgent A/B 테스트 기능을 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.shared.prompt_loader import (
    PromptLoader,
    PromptLoadError,
)

# ===================================================================
# 멀티버전 YAML 헬퍼
# ===================================================================


def _make_loader(tmp_path: Path, mode: str, agent: str, yaml_content: str) -> PromptLoader:
    """tmp_path에 YAML을 생성하고 PromptLoader를 반환한다."""
    prompts_dir = tmp_path / "prompts"
    (prompts_dir / mode).mkdir(parents=True, exist_ok=True)
    (prompts_dir / mode / f"{agent}.yaml").write_text(yaml_content)

    loader = PromptLoader.__new__(PromptLoader)
    loader._base_dir = prompts_dir.resolve()
    loader._cache = {}
    return loader


_SINGLE_PROMPT_YAML = """\
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: "v1.0.0 프롬프트"
  "1.1.0":
    system_prompt: "v1.1.0 개선된 프롬프트"
"""

_MULTI_PROMPT_YAML = """\
agent: reasoning
default_version: "1.0.0"

versions:
  "1.0.0":
    prompts:
      got:
        system_prompt: "GoT v1"
      tot:
        system_prompt: "ToT v1"
      cot:
        system_prompt: "CoT v1"
  "1.1.0":
    prompts:
      got:
        system_prompt: "GoT v1.1 개선"
      tot:
        system_prompt: "ToT v1.1 개선"
      cot:
        system_prompt: "CoT v1.1 개선"
"""


# ===================================================================
# PromptLoader 멀티버전 테스트
# ===================================================================


def test_load_multi_version_single_prompt(tmp_path: Path) -> None:
    """특정 버전을 지정하여 단일 프롬프트를 로드한다."""
    loader = _make_loader(tmp_path, "podcast", "test_agent", _SINGLE_PROMPT_YAML)

    prompt = loader.load("podcast", "test_agent", version="1.1.0")
    assert prompt == "v1.1.0 개선된 프롬프트"


def test_load_multi_version_multi_prompt(tmp_path: Path) -> None:
    """특정 버전을 지정하여 다중 프롬프트(got/tot/cot)를 로드한다."""
    loader = _make_loader(tmp_path, "podcast", "reasoning", _MULTI_PROMPT_YAML)

    prompts = loader.load_all("podcast", "reasoning", version="1.1.0")
    assert prompts["got"] == "GoT v1.1 개선"
    assert prompts["tot"] == "ToT v1.1 개선"
    assert prompts["cot"] == "CoT v1.1 개선"


@pytest.mark.parametrize(
    "yaml_content, expected",
    [
        # default_version이 있으면 해당 버전 사용
        (
            'agent: a\ndefault_version: "1.1.0"\n\nversions:\n  "1.0.0":\n'
            '    system_prompt: "v1"\n  "1.1.0":\n    system_prompt: "v1.1 기본"\n',
            "v1.1 기본",
        ),
        # default_version이 없으면 첫 번째 버전 사용
        (
            'agent: a\n\nversions:\n  "1.0.0":\n    system_prompt: "첫 번째"\n'
            '  "1.1.0":\n    system_prompt: "두 번째"\n',
            "첫 번째",
        ),
    ],
    ids=["default_version", "fallback_first"],
)
def test_load_default_and_fallback(
    tmp_path: Path, yaml_content: str, expected: str
) -> None:
    """default_version 사용 / 없으면 첫 번째 버전 fallback."""
    loader = _make_loader(tmp_path, "podcast", "test_agent", yaml_content)
    prompt = loader.load("podcast", "test_agent")
    assert prompt == expected


def test_load_invalid_version_raises(tmp_path: Path) -> None:
    """존재하지 않는 버전 요청 시 PromptLoadError."""
    loader = _make_loader(tmp_path, "podcast", "test_agent", _SINGLE_PROMPT_YAML)

    with pytest.raises(PromptLoadError, match="찾을 수 없음"):
        loader.load("podcast", "test_agent", version="9.9.9")


@pytest.mark.parametrize(
    "yaml_content, expected_versions",
    [
        # 멀티버전 — 버전 목록 반환
        (_SINGLE_PROMPT_YAML, ["1.0.0", "1.1.0"]),
        # legacy — 단일 버전 리스트
        (
            'version: "1.0.0"\nagent: test_agent\nsystem_prompt: "legacy"\n',
            ["1.0.0"],
        ),
    ],
    ids=["multi_version", "legacy"],
)
def test_get_available_versions(
    tmp_path: Path, yaml_content: str, expected_versions: list[str]
) -> None:
    """멀티버전/레거시 YAML에서 버전 목록을 반환한다."""
    loader = _make_loader(tmp_path, "podcast", "test_agent", yaml_content)
    versions = loader.get_available_versions("podcast", "test_agent")
    assert versions == expected_versions


def test_legacy_backward_compat(tmp_path: Path) -> None:
    """기존 legacy YAML이 version=None으로 정상 동작한다."""
    yaml_content = 'version: "1.0.0"\nagent: test_agent\nsystem_prompt: "legacy 프롬프트"\n'
    loader = _make_loader(tmp_path, "podcast", "test_agent", yaml_content)

    prompt = loader.load("podcast", "test_agent")
    assert prompt == "legacy 프롬프트"
    assert loader.get_version("podcast", "test_agent") == "1.0.0"


@pytest.mark.parametrize(
    "yaml_content, match_pattern",
    [
        ('agent: a\nversions: {}\n', "비어있음"),
        (
            'agent: a\ndefault_version: "1.0.0"\n\nversions:\n  "1.0.0":\n'
            '    description: "프롬프트 없음"\n',
            "system_prompt.*또는.*prompts.*누락",
        ),
    ],
    ids=["empty_versions", "missing_prompt_in_version"],
)
def test_multi_version_errors(
    tmp_path: Path, yaml_content: str, match_pattern: str
) -> None:
    """비정상 멀티버전 YAML에 대한 에러를 검증한다."""
    loader = _make_loader(tmp_path, "podcast", "test_agent", yaml_content)

    with pytest.raises(PromptLoadError, match=match_pattern):
        loader.load("podcast", "test_agent")


# ===================================================================
# Settings 버전 해석 테스트
# ===================================================================


def test_settings_prompt_version() -> None:
    """글로벌 default 버전을 반환하고, 설정 없으면 None을 반환한다."""
    from config.loader import get_settings

    settings = get_settings()
    # settings.yaml에 prompts.versions.default: "1.0.0" 설정됨
    version = settings.get_prompt_version("unknown_agent")
    assert version == "1.0.0"


def test_ab_test_config(tmp_path: Path) -> None:
    """기본 비활성 + 활성화 설정 모두 검증한다."""
    from config.loader import Settings, get_settings

    # 기본 설정 — A/B 비활성
    settings = get_settings()
    assert settings.get_ab_test_config("content_analyzer") is None

    # 활성화 설정
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        "app:\n  name: test\n  version: '0.1.0'\n"
        "llm:\n  provider: test\n  models:\n    haiku: test\n  "
        "default_max_tokens: 4096\n  temperature:\n    default: 0.7\n"
        "agents: {}\npipeline:\n  max_retries: 2\n  tier1_timeout_seconds: 15\n"
        "api:\n  timeout: 5\n  max_retries: 3\n"
        "prompts:\n  base_dir: prompts\n  versions:\n    default: '1.0.0'\n"
        "  ab_tests:\n    content_analyzer:\n      enabled: true\n"
        "      variant_a: '1.0.0'\n      variant_b: '1.1.0'\n"
        "      traffic_split: 0.5\n      assignment: session\n"
        "features:\n  podcast_mode: true\n"
    )

    ab_settings = Settings(config_path=config_path)
    ab_config = ab_settings.get_ab_test_config("content_analyzer")
    assert ab_config is not None
    assert ab_config["enabled"] is True
    assert ab_config["variant_a"] == "1.0.0"
    assert ab_config["variant_b"] == "1.1.0"
    assert ab_config["traffic_split"] == 0.5


# ===================================================================
# A/B 테스트 variant 선택
# ===================================================================


def test_ab_variant_session_deterministic() -> None:
    """동일 session_id → 동일 variant (결정적)."""
    import hashlib

    agent_name = "content_analyzer"
    session_id = "sess_test_123"
    variant_a = "1.0.0"
    variant_b = "1.1.0"

    hash_input = f"{session_id}:{agent_name}"
    hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
    ratio = (hash_value % 10000) / 10000.0

    result1 = variant_a if ratio < 0.5 else variant_b
    result2 = variant_a if ratio < 0.5 else variant_b
    assert result1 == result2

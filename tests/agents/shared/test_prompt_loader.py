"""
PromptLoader 단위 테스트.

YAML 기반 프롬프트 로더의 기능과 보안 검증을 테스트한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agents.shared.prompt_loader import (
    PromptLoader,
    PromptLoadError,
    get_prompt_base_dir,
)

# ===================================================================
# 실제 YAML 파일 로딩 테스트
# ===================================================================


def test_load_single_prompt() -> None:
    """단일 프롬프트 에이전트(content_analyzer)의 system_prompt를 로드한다."""
    loader = PromptLoader(base_dir="prompts")
    prompt = loader.load("podcast", "content_analyzer")

    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "콘텐츠 분석" in prompt or "분석 전문가" in prompt or "팟캐스트 분석가" in prompt


def test_load_multi_prompt_by_key() -> None:
    """다중 프롬프트 에이전트(podcast_reasoning)의 개별 키를 로드한다."""
    loader = PromptLoader(base_dir="prompts")

    got_prompt = loader.load("podcast", "podcast_reasoning", "got")
    tot_prompt = loader.load("podcast", "podcast_reasoning", "tot")
    cot_prompt = loader.load("podcast", "podcast_reasoning", "cot")

    assert isinstance(got_prompt, str)
    assert isinstance(tot_prompt, str)
    assert isinstance(cot_prompt, str)
    # 각 프롬프트가 서로 다른 내용이어야 한다
    assert got_prompt != tot_prompt
    assert tot_prompt != cot_prompt


@pytest.mark.parametrize(
    "mode, agent, expected_keys, expected_count",
    [
        ("podcast", "content_analyzer", ["system_prompt"], 1),
        ("podcast", "podcast_reasoning", ["got", "tot", "cot"], 3),
    ],
)
def test_load_all(
    mode: str, agent: str, expected_keys: list[str], expected_count: int
) -> None:
    """load_all()이 단일/다중 프롬프트를 올바르게 반환한다."""
    loader = PromptLoader(base_dir="prompts")
    prompts = loader.load_all(mode, agent)

    assert len(prompts) == expected_count
    for key in expected_keys:
        assert key in prompts


@pytest.mark.parametrize(
    "mode, agent",
    [
        ("podcast", "content_analyzer"),
        ("podcast", "podcast_reasoning"),
        ("shared", "learning"),
    ],
)
def test_get_version(mode: str, agent: str) -> None:
    """프롬프트 파일의 버전이 유효한 semver 형식이다."""
    import re

    loader = PromptLoader(base_dir="prompts")
    version = loader.get_version(mode, agent)
    assert re.match(r"^\d+\.\d+\.\d+$", version), f"잘못된 버전 형식: {version}"


def test_cache_hit_and_clear() -> None:
    """같은 파일을 두 번 로드하면 캐시에서 반환하고, clear 시 비운다."""
    loader = PromptLoader(base_dir="prompts")

    prompt1 = loader.load("podcast", "content_analyzer")
    prompt2 = loader.load("podcast", "content_analyzer")
    assert prompt1 == prompt2
    assert "podcast/content_analyzer" in loader._cache

    loader.clear_cache()
    assert len(loader._cache) == 0


# ===================================================================
# 보안 검증 테스트
# ===================================================================


def test_security_disallowed_base_dir() -> None:
    """허용되지 않은 디렉토리 이름은 거부한다."""
    with pytest.raises(PromptLoadError, match="허용되지 않은"):
        PromptLoader(base_dir="/etc/passwords")


@pytest.mark.parametrize(
    "mode, agent, match_pattern",
    [
        ("podcast", "nonexistent_agent", "프롬프트 파일 없음"),
        ("podcast", "content_analyzer", "찾을 수 없음"),
    ],
    ids=["nonexistent_file", "nonexistent_key"],
)
def test_nonexistent_raises(mode: str, agent: str, match_pattern: str) -> None:
    """존재하지 않는 파일/키 로드 시 에러를 발생시킨다."""
    loader = PromptLoader(base_dir="prompts")
    with pytest.raises(PromptLoadError, match=match_pattern):
        if "찾을 수 없음" in match_pattern:
            loader.load(mode, agent, "nonexistent_key")
        else:
            loader.load(mode, agent)


def test_path_traversal_prevented(tmp_path: Path) -> None:
    """경로 조작(../)이 감지되면 접근을 거부한다."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "podcast").mkdir()

    loader = PromptLoader.__new__(PromptLoader)
    loader._base_dir = prompts_dir.resolve()
    loader._cache = {}

    with pytest.raises(PromptLoadError, match="경로 조작 감지"):
        loader._load_yaml("../../etc", "passwd")


@pytest.mark.parametrize(
    "content, match_pattern",
    [
        ("{{invalid:: yaml: [", "YAML 파싱 실패"),
        ("- item1\n- item2\n", "유효하지 않은 YAML 구조"),
        ('system_prompt: "테스트 프롬프트"\n', "필수 필드 'version' 누락"),
        ('version: "1.0.0"\nagent: no_prompt\n', "system_prompt.*또는.*prompts.*누락"),
    ],
    ids=["invalid_yaml", "non_dict", "missing_version", "missing_prompt"],
)
def test_yaml_validation_errors(
    tmp_path: Path, content: str, match_pattern: str
) -> None:
    """잘못된 YAML 파일에 대한 검증 에러를 테스트한다."""
    prompts_dir = tmp_path / "prompts"
    (prompts_dir / "podcast").mkdir(parents=True)

    test_file = prompts_dir / "podcast" / "bad_agent.yaml"
    test_file.write_text(content)

    loader = PromptLoader.__new__(PromptLoader)
    loader._base_dir = prompts_dir.resolve()
    loader._cache = {}

    with pytest.raises(PromptLoadError, match=match_pattern):
        loader._load_yaml("podcast", "bad_agent")


def test_oversized_file_rejected(tmp_path: Path) -> None:
    """파일 크기가 제한을 초과하면 거부한다."""
    prompts_dir = tmp_path / "prompts"
    (prompts_dir / "podcast").mkdir(parents=True)

    big_file = prompts_dir / "podcast" / "big_agent.yaml"
    big_file.write_text("x" * 200_000)

    loader = PromptLoader.__new__(PromptLoader)
    loader._base_dir = prompts_dir.resolve()
    loader._cache = {}

    with pytest.raises(PromptLoadError, match="파일 크기 초과"):
        loader._load_yaml("podcast", "big_agent")


# ===================================================================
# 환경변수 테스트
# ===================================================================


def test_get_prompt_base_dir_default_and_env() -> None:
    """기본값 'prompts'와 환경변수 PROMPT_DIR 오버라이드를 검증한다."""
    original = os.environ.pop("PROMPT_DIR", None)
    try:
        assert get_prompt_base_dir() == "prompts"

        os.environ["PROMPT_DIR"] = "prompts_staging"
        assert get_prompt_base_dir() == "prompts_staging"
    finally:
        if original is not None:
            os.environ["PROMPT_DIR"] = original
        else:
            os.environ.pop("PROMPT_DIR", None)


# ===================================================================
# BaseAgent 통합 테스트
# ===================================================================


@pytest.mark.parametrize(
    "import_path, agent_cls_name",
    [
        ("src.agents.podcast.content_analyzer", "ContentAnalyzerAgent"),
        ("src.agents.podcast.podcast_reasoning", "PodcastReasoningAgent"),
        ("src.agents.podcast.batch_validator", "BatchValidatorAgent"),
        ("src.agents.shared.learning", "LearningAgent"),
    ],
)
def test_agent_loads_prompts_and_version(
    import_path: str, agent_cls_name: str
) -> None:
    """에이전트 생성 시 YAML 프롬프트가 로드되고 유효한 semver 버전이다."""
    import importlib
    import re

    module = importlib.import_module(import_path)
    agent_cls = getattr(module, agent_cls_name)
    agent = agent_cls()

    # 프롬프트 버전 확인 (semver 형식)
    assert agent.prompt_version is not None
    assert re.match(r"^\d+\.\d+\.\d+$", agent.prompt_version), (
        f"{agent_cls_name} 버전이 잘못된 형식: {agent.prompt_version}"
    )

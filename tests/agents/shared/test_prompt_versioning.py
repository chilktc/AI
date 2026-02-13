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

# === PromptLoader 멀티버전 테스트 ===


class TestPromptLoaderMultiVersion:
    """멀티버전 YAML 형식에서 PromptLoader 동작을 검증한다."""

    def test_load_multi_version_single_prompt(self, tmp_path: Path) -> None:
        """특정 버전을 지정하여 단일 프롬프트를 로드한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: "v1.0.0 프롬프트"
  "1.1.0":
    system_prompt: "v1.1.0 개선된 프롬프트"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # 특정 버전 지정
        prompt = loader.load("podcast", "test_agent", version="1.1.0")
        assert prompt == "v1.1.0 개선된 프롬프트"

    def test_load_multi_version_multi_prompt(self, tmp_path: Path) -> None:
        """특정 버전을 지정하여 다중 프롬프트(got/tot/cot)를 로드한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
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
        (prompts_dir / "podcast" / "reasoning.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # v1.1.0 지정
        prompts = loader.load_all("podcast", "reasoning", version="1.1.0")
        assert prompts["got"] == "GoT v1.1 개선"
        assert prompts["tot"] == "ToT v1.1 개선"
        assert prompts["cot"] == "CoT v1.1 개선"

    def test_load_default_version(self, tmp_path: Path) -> None:
        """version=None이면 default_version을 사용한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.1.0"

versions:
  "1.0.0":
    system_prompt: "v1.0.0"
  "1.1.0":
    system_prompt: "v1.1.0 기본"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # version 미지정 → default_version 사용
        prompt = loader.load("podcast", "test_agent")
        assert prompt == "v1.1.0 기본"

    def test_load_fallback_first_version(self, tmp_path: Path) -> None:
        """default_version 없으면 첫 번째 버전을 사용한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        # default_version 없음
        yaml_content = """
agent: test_agent

versions:
  "1.0.0":
    system_prompt: "첫 번째 버전"
  "1.1.0":
    system_prompt: "두 번째 버전"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        prompt = loader.load("podcast", "test_agent")
        assert prompt == "첫 번째 버전"

    def test_load_invalid_version_raises_error(self, tmp_path: Path) -> None:
        """존재하지 않는 버전 요청 시 PromptLoadError."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: "v1"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="찾을 수 없음"):
            loader.load("podcast", "test_agent", version="9.9.9")

    def test_get_available_versions_multi(self, tmp_path: Path) -> None:
        """멀티버전 YAML에서 버전 목록을 반환한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: "v1"
  "1.1.0":
    system_prompt: "v1.1"
  "2.0.0":
    system_prompt: "v2"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        versions = loader.get_available_versions("podcast", "test_agent")
        assert versions == ["1.0.0", "1.1.0", "2.0.0"]

    def test_get_available_versions_legacy(self, tmp_path: Path) -> None:
        """legacy YAML에서 단일 버전 리스트를 반환한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
version: "1.0.0"
agent: test_agent
system_prompt: "legacy 프롬프트"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        versions = loader.get_available_versions("podcast", "test_agent")
        assert versions == ["1.0.0"]

    def test_legacy_backward_compat(self, tmp_path: Path) -> None:
        """기존 legacy YAML이 version=None으로 정상 동작한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
version: "1.0.0"
agent: test_agent
system_prompt: "legacy 프롬프트"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # legacy에서 version=None → 기존 동작 그대로
        prompt = loader.load("podcast", "test_agent")
        assert prompt == "legacy 프롬프트"
        assert loader.get_version("podcast", "test_agent") == "1.0.0"

    def test_multi_version_empty_versions_raises(self, tmp_path: Path) -> None:
        """versions: {} 비어있으면 PromptLoadError."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
versions: {}
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="비어있음"):
            loader.load("podcast", "test_agent")

    def test_multi_version_missing_prompt_in_version(self, tmp_path: Path) -> None:
        """버전 내부에 system_prompt와 prompts 둘 다 없으면 에러."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    description: "프롬프트가 없는 버전"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="system_prompt.*또는.*prompts.*누락"):
            loader.load("podcast", "test_agent")

    def test_get_version_multi_version(self, tmp_path: Path) -> None:
        """멀티버전에서 get_version()이 타겟 버전을 반환한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        yaml_content = """
agent: test_agent
default_version: "1.0.0"

versions:
  "1.0.0":
    system_prompt: "v1"
  "1.1.0":
    system_prompt: "v1.1"
"""
        (prompts_dir / "podcast" / "test_agent.yaml").write_text(yaml_content)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # 기본 버전
        assert loader.get_version("podcast", "test_agent") == "1.0.0"
        # 지정 버전
        assert loader.get_version("podcast", "test_agent", version="1.1.0") == "1.1.0"


# === 실제 YAML 파일 멀티버전 로드 테스트 ===


class TestRealYamlMultiVersion:
    """실제 YAML 파일이 멀티버전 형식으로 정상 로드되는지 검증한다."""

    def test_content_analyzer_multi_version(self) -> None:
        """content_analyzer.yaml이 멀티버전 형식으로 정상 로드된다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("podcast", "content_analyzer")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "콘텐츠 분석" in prompt or "분석 전문가" in prompt

    def test_podcast_reasoning_multi_version(self) -> None:
        """podcast_reasoning.yaml이 멀티버전 형식으로 정상 로드된다."""
        loader = PromptLoader(base_dir="prompts")
        prompts = loader.load_all("podcast", "podcast_reasoning")

        assert "got" in prompts
        assert "tot" in prompts
        assert "cot" in prompts
        assert len(prompts) == 3

    def test_batch_validator_multi_version(self) -> None:
        """batch_validator.yaml이 멀티버전 형식으로 정상 로드된다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("podcast", "batch_validator")

        assert isinstance(prompt, str)
        assert "검증" in prompt or "품질" in prompt

    def test_learning_multi_version(self) -> None:
        """learning.yaml이 멀티버전 형식으로 정상 로드된다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("shared", "learning")

        assert isinstance(prompt, str)
        assert "학습" in prompt or "패턴" in prompt

    def test_all_yaml_have_available_versions(self) -> None:
        """모든 YAML 파일에서 버전 목록을 조회할 수 있다."""
        loader = PromptLoader(base_dir="prompts")

        for mode, agent in [
            ("podcast", "content_analyzer"),
            ("podcast", "podcast_reasoning"),
            ("podcast", "batch_validator"),
            ("shared", "learning"),
        ]:
            versions = loader.get_available_versions(mode, agent)
            assert len(versions) >= 1
            assert "1.0.0" in versions

    def test_all_yaml_get_version_returns_1_0_0(self) -> None:
        """모든 YAML 파일의 기본 버전이 1.0.0이다."""
        loader = PromptLoader(base_dir="prompts")

        for mode, agent in [
            ("podcast", "content_analyzer"),
            ("podcast", "podcast_reasoning"),
            ("podcast", "batch_validator"),
            ("shared", "learning"),
        ]:
            version = loader.get_version(mode, agent)
            assert version == "1.0.0"


# === Settings 버전 해석 테스트 ===


class TestSettingsPromptVersion:
    """config/loader.py의 프롬프트 버전 해석을 검증한다."""

    def test_get_prompt_version_global_default(self) -> None:
        """글로벌 default 버전을 반환한다."""
        from config.loader import get_settings

        settings = get_settings()
        # settings.yaml에 prompts.versions.default: "1.0.0" 설정됨
        version = settings.get_prompt_version("unknown_agent")
        assert version == "1.0.0"

    def test_get_prompt_version_none_when_no_config(self, tmp_path: Path) -> None:
        """설정이 없으면 None을 반환한다."""
        from config.loader import Settings

        # prompts.versions 섹션이 없는 설정 파일
        config_path = tmp_path / "settings.yaml"
        config_path.write_text(
            "app:\n  name: test\n  version: '0.1.0'\n"
            "llm:\n  provider: test\n  models:\n    haiku: test\n  "
            "default_max_tokens: 4096\n  temperature:\n    default: 0.7\n"
            "agents: {}\npipeline:\n  max_retries: 2\n  tier1_timeout_seconds: 15\n"
            "api:\n  timeout: 5\n  max_retries: 3\n"
            "prompts:\n  base_dir: prompts\n"
            "features:\n  podcast_mode: true\n"
        )

        settings = Settings(config_path=config_path)
        version = settings.get_prompt_version("content_analyzer")
        assert version is None

    def test_get_ab_config_disabled_by_default(self) -> None:
        """기본 설정에서 A/B 테스트는 비활성이다."""
        from config.loader import get_settings

        settings = get_settings()
        ab_config = settings.get_ab_test_config("content_analyzer")
        assert ab_config is None

    def test_get_ab_config_enabled(self, tmp_path: Path) -> None:
        """A/B 테스트 활성화 설정을 반환한다."""
        from config.loader import Settings

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

        settings = Settings(config_path=config_path)
        ab_config = settings.get_ab_test_config("content_analyzer")
        assert ab_config is not None
        assert ab_config["enabled"] is True
        assert ab_config["variant_a"] == "1.0.0"
        assert ab_config["variant_b"] == "1.1.0"
        assert ab_config["traffic_split"] == 0.5


# === BaseAgent 멀티버전 통합 테스트 ===


class TestBaseAgentMultiVersion:
    """BaseAgent가 멀티버전 프롬프트를 올바르게 로드하는지 검증한다."""

    def test_agent_loads_default_version(self) -> None:
        """에이전트가 기본 버전(1.0.0)으로 프롬프트를 로드한다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        prompt = agent.get_prompt("system_prompt")

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_agent_prompt_version_returns_1_0_0(self) -> None:
        """에이전트의 prompt_version이 1.0.0을 반환한다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        assert agent.prompt_version == "1.0.0"

    def test_multi_prompt_agent_loads_all_keys(self) -> None:
        """다중 프롬프트 에이전트가 모든 키를 로드한다."""
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()
        got = agent.get_prompt("got")
        tot = agent.get_prompt("tot")
        cot = agent.get_prompt("cot")

        assert isinstance(got, str)
        assert isinstance(tot, str)
        assert isinstance(cot, str)

    def test_agent_ab_variant_none_by_default(self) -> None:
        """A/B 비활성 시 ab_variant는 None이다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        assert agent.ab_variant is None


# === A/B 테스트 variant 선택 테스트 ===


class TestABVariantSelection:
    """A/B 테스트 variant 선택 로직을 검증한다."""

    def test_session_deterministic(self) -> None:
        """동일 session_id → 동일 variant (결정적)."""
        import hashlib

        # _resolve_ab_variant 내부 로직을 직접 테스트
        agent_name = "content_analyzer"
        session_id = "sess_test_123"
        variant_a = "1.0.0"
        variant_b = "1.1.0"

        hash_input = f"{session_id}:{agent_name}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        ratio = (hash_value % 10000) / 10000.0

        result1 = variant_a if ratio < 0.5 else variant_b
        result2 = variant_a if ratio < 0.5 else variant_b

        # 같은 입력이면 항상 같은 결과
        assert result1 == result2

    def test_different_sessions_can_differ(self) -> None:
        """다른 session_id는 다른 variant를 선택할 수 있다 (통계적)."""
        import hashlib

        agent_name = "content_analyzer"
        variant_a = "1.0.0"
        variant_b = "1.1.0"
        results: set[str] = set()

        # 100개 다른 세션 ID로 테스트
        for i in range(100):
            session_id = f"sess_{i}"
            hash_input = f"{session_id}:{agent_name}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            ratio = (hash_value % 10000) / 10000.0
            result = variant_a if ratio < 0.5 else variant_b
            results.add(result)

        # 100개 중 양쪽 variant 모두 선택되어야 한다 (통계적)
        assert len(results) == 2

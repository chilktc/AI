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

# 테스트용 프롬프트 디렉토리 (프로젝트 루트의 prompts/)
_PROMPTS_DIR = Path("prompts")


# === 실제 YAML 파일 로딩 테스트 ===


class TestPromptLoaderLoad:
    """단일 프롬프트 로딩 테스트."""

    def test_load_single_prompt(self) -> None:
        """단일 프롬프트 에이전트(content_analyzer)의 system_prompt를 로드한다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("podcast", "content_analyzer")

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # 프롬프트 내용에 핵심 키워드가 포함되어야 한다
        assert "콘텐츠 분석" in prompt or "분석 전문가" in prompt

    def test_load_multi_prompt_by_key(self) -> None:
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

    def test_load_shared_agent(self) -> None:
        """shared 모드의 에이전트(learning) 프롬프트를 로드한다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("shared", "learning")

        assert isinstance(prompt, str)
        assert "학습" in prompt or "패턴" in prompt

    def test_load_batch_validator(self) -> None:
        """batch_validator 프롬프트를 로드한다."""
        loader = PromptLoader(base_dir="prompts")
        prompt = loader.load("podcast", "batch_validator")

        assert isinstance(prompt, str)
        assert "검증" in prompt or "품질" in prompt


class TestPromptLoaderLoadAll:
    """전체 프롬프트 로딩 테스트."""

    def test_load_all_single_prompt_agent(self) -> None:
        """단일 프롬프트 에이전트는 {"system_prompt": ...} 형태를 반환한다."""
        loader = PromptLoader(base_dir="prompts")
        prompts = loader.load_all("podcast", "content_analyzer")

        assert "system_prompt" in prompts
        assert len(prompts) == 1

    def test_load_all_multi_prompt_agent(self) -> None:
        """다중 프롬프트 에이전트는 각 키별 프롬프트를 반환한다."""
        loader = PromptLoader(base_dir="prompts")
        prompts = loader.load_all("podcast", "podcast_reasoning")

        assert "got" in prompts
        assert "tot" in prompts
        assert "cot" in prompts
        assert len(prompts) == 3


class TestPromptLoaderVersion:
    """버전 조회 테스트."""

    def test_get_version(self) -> None:
        """프롬프트 파일의 버전을 반환한다."""
        loader = PromptLoader(base_dir="prompts")
        version = loader.get_version("podcast", "content_analyzer")

        assert version == "1.0.0"

    def test_get_version_multi_prompt_agent(self) -> None:
        """다중 프롬프트 에이전트도 동일하게 버전을 반환한다."""
        loader = PromptLoader(base_dir="prompts")
        version = loader.get_version("podcast", "podcast_reasoning")

        assert version == "1.0.0"

    def test_get_version_shared_agent(self) -> None:
        """shared 모드 에이전트의 버전을 반환한다."""
        loader = PromptLoader(base_dir="prompts")
        version = loader.get_version("shared", "learning")

        assert version == "1.0.0"


class TestPromptLoaderCache:
    """캐싱 테스트."""

    def test_cache_prevents_repeated_file_reads(self) -> None:
        """같은 파일을 두 번 로드하면 캐시에서 반환한다."""
        loader = PromptLoader(base_dir="prompts")

        # 첫 번째 로드 — 파일에서 읽음
        prompt1 = loader.load("podcast", "content_analyzer")
        # 두 번째 로드 — 캐시에서 반환
        prompt2 = loader.load("podcast", "content_analyzer")

        assert prompt1 == prompt2
        # 캐시에 항목이 있는지 확인
        assert "podcast/content_analyzer" in loader._cache

    def test_clear_cache(self) -> None:
        """캐시를 초기화하면 비어있어야 한다."""
        loader = PromptLoader(base_dir="prompts")
        loader.load("podcast", "content_analyzer")

        assert len(loader._cache) > 0
        loader.clear_cache()
        assert len(loader._cache) == 0


# === 보안 검증 테스트 ===


class TestPromptLoaderSecurity:
    """보안 대책 검증 테스트."""

    def test_disallowed_base_dir_raises_error(self) -> None:
        """허용되지 않은 디렉토리 이름은 거부한다."""
        with pytest.raises(PromptLoadError, match="허용되지 않은"):
            PromptLoader(base_dir="/etc/passwords")

    def test_allowed_base_dirs(self) -> None:
        """화이트리스트에 포함된 디렉토리는 허용한다."""
        # prompts는 실제로 존재하므로 인스턴스 생성 성공
        loader = PromptLoader(base_dir="prompts")
        assert loader is not None

    def test_nonexistent_file_raises_error(self) -> None:
        """존재하지 않는 YAML 파일 로드 시 에러를 발생시킨다."""
        loader = PromptLoader(base_dir="prompts")
        with pytest.raises(PromptLoadError, match="프롬프트 파일 없음"):
            loader.load("podcast", "nonexistent_agent")

    def test_nonexistent_prompt_key_raises_error(self) -> None:
        """존재하지 않는 프롬프트 키 로드 시 에러를 발생시킨다."""
        loader = PromptLoader(base_dir="prompts")
        with pytest.raises(PromptLoadError, match="찾을 수 없음"):
            loader.load("podcast", "content_analyzer", "nonexistent_key")

    def test_path_traversal_prevented(self, tmp_path: Path) -> None:
        """경로 조작(../)이 감지되면 접근을 거부한다."""
        # tmp_path에 prompts 디렉토리 생성
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "podcast").mkdir()

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        # 경로 조작 시도 — base_dir 밖으로 나가려는 경로
        with pytest.raises(PromptLoadError, match="경로 조작 감지"):
            loader._load_yaml("../../etc", "passwd")

    def test_oversized_file_rejected(self, tmp_path: Path) -> None:
        """파일 크기가 제한을 초과하면 거부한다."""
        # 임시 디렉토리에 큰 YAML 파일 생성
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        big_file = prompts_dir / "podcast" / "big_agent.yaml"
        # 100KB 초과 파일 생성
        big_file.write_text("x" * 200_000)

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="파일 크기 초과"):
            loader._load_yaml("podcast", "big_agent")

    def test_invalid_yaml_raises_error(self, tmp_path: Path) -> None:
        """유효하지 않은 YAML 파일은 파싱 에러를 발생시킨다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        bad_file = prompts_dir / "podcast" / "bad_agent.yaml"
        bad_file.write_text("{{invalid:: yaml: [")

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="YAML 파싱 실패"):
            loader._load_yaml("podcast", "bad_agent")

    def test_non_dict_yaml_raises_error(self, tmp_path: Path) -> None:
        """YAML 파싱 결과가 dict가 아니면 에러를 발생시킨다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        list_file = prompts_dir / "podcast" / "list_agent.yaml"
        list_file.write_text("- item1\n- item2\n")

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="유효하지 않은 YAML 구조"):
            loader._load_yaml("podcast", "list_agent")

    def test_missing_version_field_raises_error(self, tmp_path: Path) -> None:
        """version 필드가 없는 YAML 파일은 즉시 실패한다 (fail-fast)."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        # version 필드 누락 — system_prompt만 있음
        no_version_file = prompts_dir / "podcast" / "no_version.yaml"
        no_version_file.write_text('system_prompt: "테스트 프롬프트"\n')

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="필수 필드 'version' 누락"):
            loader._load_yaml("podcast", "no_version")

    def test_missing_prompt_fields_raises_error(self, tmp_path: Path) -> None:
        """system_prompt와 prompts 둘 다 없는 YAML은 실패한다."""
        prompts_dir = tmp_path / "prompts"
        (prompts_dir / "podcast").mkdir(parents=True)

        # version만 있고 프롬프트 필드 없음
        no_prompt_file = prompts_dir / "podcast" / "no_prompt.yaml"
        no_prompt_file.write_text('version: "1.0.0"\nagent: no_prompt\n')

        loader = PromptLoader.__new__(PromptLoader)
        loader._base_dir = prompts_dir.resolve()
        loader._cache = {}

        with pytest.raises(PromptLoadError, match="system_prompt.*또는.*prompts.*누락"):
            loader._load_yaml("podcast", "no_prompt")


# === 환경변수 테스트 ===


class TestGetPromptBaseDir:
    """get_prompt_base_dir() 환경변수 테스트."""

    def test_default_base_dir(self) -> None:
        """환경변수 없으면 기본값 'prompts'를 반환한다."""
        # 환경변수가 없는 상태에서 테스트
        original = os.environ.pop("PROMPT_DIR", None)
        try:
            assert get_prompt_base_dir() == "prompts"
        finally:
            if original is not None:
                os.environ["PROMPT_DIR"] = original

    def test_env_override(self) -> None:
        """PROMPT_DIR 환경변수가 설정되면 해당 값을 반환한다."""
        original = os.environ.get("PROMPT_DIR")
        try:
            os.environ["PROMPT_DIR"] = "prompts_staging"
            assert get_prompt_base_dir() == "prompts_staging"
        finally:
            if original is not None:
                os.environ["PROMPT_DIR"] = original
            else:
                os.environ.pop("PROMPT_DIR", None)


# === BaseAgent 통합 테스트 ===


class TestBaseAgentPromptIntegration:
    """BaseAgent에 PromptLoader가 올바르게 통합되었는지 테스트."""

    def test_content_analyzer_loads_prompts(self) -> None:
        """ContentAnalyzerAgent 생성 시 YAML 프롬프트가 로드된다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        prompt = agent.get_prompt("system_prompt")

        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_podcast_reasoning_loads_multi_prompts(self) -> None:
        """PodcastReasoningAgent 생성 시 GoT/ToT/CoT 프롬프트가 로드된다."""
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()

        got = agent.get_prompt("got")
        tot = agent.get_prompt("tot")
        cot = agent.get_prompt("cot")

        assert isinstance(got, str)
        assert isinstance(tot, str)
        assert isinstance(cot, str)

    def test_batch_validator_loads_prompts(self) -> None:
        """BatchValidatorAgent 생성 시 YAML 프롬프트가 로드된다."""
        from src.agents.podcast.batch_validator import BatchValidatorAgent

        agent = BatchValidatorAgent()
        prompt = agent.get_prompt("system_prompt")

        assert isinstance(prompt, str)

    def test_learning_agent_loads_prompts(self) -> None:
        """LearningAgent 생성 시 YAML 프롬프트가 로드된다."""
        from src.agents.shared.learning import LearningAgent

        agent = LearningAgent()
        prompt = agent.get_prompt("system_prompt")

        assert isinstance(prompt, str)

    def test_get_prompt_invalid_key_raises_error(self) -> None:
        """존재하지 않는 프롬프트 키 접근 시 KeyError를 발생시킨다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()
        with pytest.raises(KeyError, match="찾을 수 없음"):
            agent.get_prompt("nonexistent_key")

    def test_prompt_version_returns_semver(self) -> None:
        """YAML 프롬프트가 있는 에이전트는 prompt_version이 SemVer를 반환한다."""
        from src.agents.podcast.content_analyzer import ContentAnalyzerAgent

        agent = ContentAnalyzerAgent()

        assert agent.prompt_version is not None
        assert agent.prompt_version == "1.0.0"

    def test_prompt_version_multi_prompt_agent(self) -> None:
        """다중 프롬프트 에이전트도 prompt_version이 정상 반환된다."""
        from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent

        agent = PodcastReasoningAgent()

        assert agent.prompt_version is not None
        assert agent.prompt_version == "1.0.0"

    def test_prompt_version_shared_agent(self) -> None:
        """shared 모드 에이전트도 prompt_version이 정상 반환된다."""
        from src.agents.shared.learning import LearningAgent

        agent = LearningAgent()

        assert agent.prompt_version is not None
        assert agent.prompt_version == "1.0.0"

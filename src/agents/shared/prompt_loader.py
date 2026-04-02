"""
PromptLoader — YAML 기반 프롬프트 로더.

[Shared Infrastructure — 인터페이스 변경 금지]
기존 public 메서드(load, load_all, get_version,
get_available_versions, clear_cache)의 시그니처와 동작을 변경하지 마시오.
신규 메서드 추가만 허용. 수정 시 전체 테스트(pytest tests/ -v) 통과 필수.

에이전트별 프롬프트를 YAML 파일에서 로드하고 캐싱한다.
보안 대책으로 yaml.safe_load()만 사용하고, 경로 조작(Path Traversal)을 방지한다.

멀티버전 지원 (v8):
    - legacy 형식: 최상위에 version + system_prompt/prompts (하위 호환)
    - 멀티버전 형식: versions 키 아래에 여러 버전 공존
    - default_version: 명시적 버전 미지정 시 사용할 기본 버전

사용법:
    loader = PromptLoader(base_dir="prompts")

    # 단일 프롬프트 에이전트 (legacy 또는 멀티버전 기본 버전)
    prompt = loader.load("podcast", "content_analyzer")

    # 특정 버전 지정 (멀티버전)
    prompt = loader.load("podcast", "content_analyzer", version="1.1.0")

    # 다중 프롬프트 에이전트 (GoT/ToT/CoT 등)
    prompts = loader.load_all("podcast", "podcast_reasoning")
    got_prompt = prompts["got"]

    # 버전 조회
    version = loader.get_version("podcast", "content_analyzer")

    # 사용 가능한 버전 목록 조회 (멀티버전)
    versions = loader.get_available_versions("podcast", "content_analyzer")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.utils.logger import get_agent_logger

# 프롬프트 파일 최대 크기 (바이트) — 과도하게 큰 파일 로드 방지
_MAX_FILE_SIZE_BYTES = 100_000  # 100KB

# 허용되는 프롬프트 디렉토리 이름 화이트리스트
_ALLOWED_BASE_DIRS = {"prompts", "prompts_dev", "prompts_staging", "prompts_prod"}

logger = get_agent_logger("prompt_loader")


class PromptLoadError(Exception):
    """프롬프트 로딩 실패 시 발생하는 예외."""

    pass


class PromptLoader:
    """
    YAML 기반 프롬프트 로더 — 에이전트별 프롬프트 파일 관리.

    보안 대책:
        - yaml.safe_load()만 사용 (코드 실행 방지)
        - Path.resolve() + base_dir 범위 제한 (경로 조작 방지)
        - 파일 크기 검증 (과도한 로드 방지)
        - 디렉토리 이름 화이트리스트 (환경변수 조작 방지)

    멀티버전 지원:
        - versions 키가 있으면 → 멀티버전 형식
        - versions 키가 없으면 → legacy 형식 (기존 동작 유지)
        - default_version 또는 첫 번째 버전을 기본값으로 사용

    Args:
        base_dir: 프롬프트 YAML 파일이 저장된 기본 디렉토리 (기본: "prompts")
    """

    def __init__(self, base_dir: str = "prompts") -> None:
        # 화이트리스트 검증 — 허용된 디렉토리 이름만 사용 가능
        dir_name = Path(base_dir).name
        if dir_name not in _ALLOWED_BASE_DIRS:
            raise PromptLoadError(
                f"허용되지 않은 프롬프트 디렉토리: '{dir_name}'. "
                f"허용 목록: {_ALLOWED_BASE_DIRS}"
            )

        # 프로젝트 루트 기준 절대 경로로 변환
        self._base_dir = Path(base_dir).resolve()
        # YAML 파일 캐시 (파일 경로 → 파싱된 dict)
        self._cache: dict[str, dict[str, Any]] = {}

    # --- 멀티버전 핵심 메서드 ---

    def _is_multi_version(self, data: dict[str, Any]) -> bool:
        """YAML 데이터가 멀티버전 형식인지 판별한다."""
        return "versions" in data and isinstance(data["versions"], dict)

    def _extract_version_data(
        self,
        data: dict[str, Any],
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        멀티버전 YAML에서 특정 버전의 데이터를 추출한다.

        legacy 형식이면 data를 그대로 반환 (하위 호환).
        멀티버전 형식이면 지정된 버전 또는 기본 버전을 선택한다.

        버전 해석 우선순위:
            1. version 파라미터 (명시적 지정)
            2. YAML 내부 default_version
            3. versions의 첫 번째 키 (fallback)

        Args:
            data: _load_yaml()이 반환한 raw YAML dict
            version: 명시적으로 지정할 버전 (None이면 기본 버전 사용)

        Returns:
            해당 버전의 프롬프트 데이터 dict

        Raises:
            PromptLoadError: 버전을 찾을 수 없을 때
        """
        # legacy 형식 — 그대로 반환
        if not self._is_multi_version(data):
            return data

        versions = data["versions"]

        # 타겟 버전 결정
        target_version = version
        if target_version is None:
            # default_version → 첫 번째 버전 순서로 fallback
            target_version = data.get("default_version")
            if target_version is None:
                # 첫 번째 버전을 기본값으로 사용
                target_version = next(iter(versions))

        if target_version not in versions:
            available = list(versions.keys())
            raise PromptLoadError(
                f"프롬프트 버전 '{target_version}'을 찾을 수 없음. "
                f"사용 가능한 버전: {available}"
            )

        return dict(versions[target_version])

    def get_available_versions(self, mode: str, agent_name: str) -> list[str]:
        """
        에이전트의 사용 가능한 프롬프트 버전 목록을 반환한다.

        멀티버전 YAML: versions 키의 모든 버전을 리스트로 반환
        legacy YAML: [version] 1개 리스트 반환

        Args:
            mode: 에이전트 모드 ("podcast", "shared")
            agent_name: 에이전트 이름

        Returns:
            버전 문자열 리스트 (예: ["1.0.0", "1.1.0"])
        """
        data = self._load_yaml(mode, agent_name)

        if self._is_multi_version(data):
            return list(data["versions"].keys())

        # legacy 형식 — version 필드 1개만 반환
        return [str(data["version"])]

    # --- 프롬프트 로딩 ---

    def load(
        self,
        mode: str,
        agent_name: str,
        prompt_key: str = "system_prompt",
        *,
        version: str | None = None,
    ) -> str:
        """
        단일 프롬프트를 로드한다.

        Args:
            mode: 에이전트 모드 ("podcast", "shared")
            agent_name: 에이전트 이름 (예: "content_analyzer")
            prompt_key: 프롬프트 키 (기본: "system_prompt")
            version: 로드할 버전 (None이면 기본 버전 사용, 멀티버전 전용)

        Returns:
            프롬프트 문자열

        Raises:
            PromptLoadError: 파일 없음, 키 없음, 버전 없음, 보안 위반 시
        """
        raw_data = self._load_yaml(mode, agent_name)
        data = self._extract_version_data(raw_data, version)

        # 단일 프롬프트 구조: 최상위에 system_prompt
        if prompt_key == "system_prompt" and "system_prompt" in data:
            return str(data["system_prompt"])

        # 다중 프롬프트 구조: prompts.{key}.system_prompt
        prompts_section = data.get("prompts", {})
        if prompt_key in prompts_section:
            sub = prompts_section[prompt_key]
            if isinstance(sub, dict) and "system_prompt" in sub:
                return str(sub["system_prompt"])

        raise PromptLoadError(
            f"프롬프트 키 '{prompt_key}'를 찾을 수 없음: {mode}/{agent_name}.yaml"
        )

    def load_user_prompt(
        self,
        mode: str,
        agent_name: str,
        prompt_key: str = "user_prompt",
        *,
        version: str | None = None,
    ) -> str:
        """
        단일 프롬프트 에이전트나 다중 프롬프트 에이전트의 user_prompt를 로드한다.

        Args:
            mode: 에이전트 모드 ("podcast", "shared")
            agent_name: 에이전트 이름 (예: "script_generator")
            prompt_key: 프롬프트 키 (기본: "user_prompt")
            version: 로드할 버전 (None이면 기본 버전 사용, 멀티버전 전용)

        Returns:
            프롬프트 문자열

        Raises:
            PromptLoadError: 파일 없음, 키 없음, 버전 없음, 보안 위반 시
        """
        raw_data = self._load_yaml(mode, agent_name)
        data = self._extract_version_data(raw_data, version)

        # 다중 프롬프트 구조 (prompts.키.user_prompt)부터 확인
        prompts_section = data.get("prompts", {})
        if prompt_key in prompts_section:
            sub = prompts_section[prompt_key]
            if isinstance(sub, dict) and "user_prompt" in sub:
                return str(sub["user_prompt"])

        # 단일 프롬프트 구조: 최상위에 user_prompt가 있을 때 (prompt_key 무시)
        if "user_prompt" in data:
            return str(data["user_prompt"])

        raise PromptLoadError(
            f"유저 프롬프트(키 '{prompt_key}')를 찾을 수 없음: {mode}/{agent_name}.yaml"
        )

    def load_all(
        self,
        mode: str,
        agent_name: str,
        *,
        version: str | None = None,
    ) -> dict[str, str]:
        """
        에이전트의 모든 프롬프트를 로드한다.

        단일 프롬프트 에이전트: {"system_prompt": "..."}
        다중 프롬프트 에이전트: {"got": "...", "tot": "...", "cot": "..."}

        Args:
            mode: 에이전트 모드 ("podcast", "shared")
            agent_name: 에이전트 이름
            version: 로드할 버전 (None이면 기본 버전 사용, 멀티버전 전용)

        Returns:
            프롬프트 이름 → 프롬프트 문자열 dict
        """
        raw_data = self._load_yaml(mode, agent_name)
        data = self._extract_version_data(raw_data, version)
        result: dict[str, str] = {}

        # 단일 프롬프트 구조
        if "system_prompt" in data:
            result["system_prompt"] = str(data["system_prompt"])

        # 다중 프롬프트 구조
        prompts_section = data.get("prompts", {})
        for key, value in prompts_section.items():
            if isinstance(value, dict) and "system_prompt" in value:
                result[key] = str(value["system_prompt"])

        if not result:
            raise PromptLoadError(f"프롬프트를 찾을 수 없음: {mode}/{agent_name}.yaml")

        return result

    def get_version(
        self,
        mode: str,
        agent_name: str,
        *,
        version: str | None = None,
    ) -> str:
        """
        프롬프트 파일의 버전을 반환한다 (SemVer 형식).

        멀티버전: 지정 버전 또는 기본 버전을 반환
        legacy: 최상위 version 필드를 반환

        Args:
            mode: 에이전트 모드
            agent_name: 에이전트 이름
            version: 명시적 버전 지정 (None이면 기본 버전)

        Returns:
            SemVer 문자열 (예: "1.0.0")
        """
        data = self._load_yaml(mode, agent_name)

        # legacy 형식
        if not self._is_multi_version(data):
            return str(data["version"])

        # 멀티버전 형식 — 타겟 버전 결정
        target_version = version
        if target_version is None:
            target_version = data.get("default_version")
            if target_version is None:
                target_version = next(iter(data["versions"]))

        if target_version not in data["versions"]:
            available = list(data["versions"].keys())
            raise PromptLoadError(
                f"프롬프트 버전 '{target_version}'을 찾을 수 없음. "
                f"사용 가능한 버전: {available}"
            )

        return str(target_version)

    # --- YAML 로딩 + 보안 검증 ---

    def _load_yaml(self, mode: str, agent_name: str) -> dict[str, Any]:
        """
        YAML 파일을 로드하고 캐싱한다.

        보안 검증:
            1. 경로 조작 방지 (Path.resolve() + base_dir 범위 확인)
            2. yaml.safe_load()만 사용 (코드 실행 방지)
            3. 파일 크기 검증 (과도한 로드 방지)

        검증 분기:
            - legacy 형식: version 필수 + system_prompt/prompts 중 하나 필수
            - 멀티버전 형식: versions 키 존재 + 비어있지 않음
        """
        cache_key = f"{mode}/{agent_name}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        # 파일 경로 구성 + 경로 조작 방지
        file_path = (self._base_dir / mode / f"{agent_name}.yaml").resolve()
        self._validate_path(file_path)

        # 파일 존재 확인
        if not file_path.exists():
            raise PromptLoadError(f"프롬프트 파일 없음: {file_path}")

        # 파일 크기 검증
        file_size = file_path.stat().st_size
        if file_size > _MAX_FILE_SIZE_BYTES:
            raise PromptLoadError(
                f"프롬프트 파일 크기 초과: {file_path} "
                f"({file_size} > {_MAX_FILE_SIZE_BYTES} bytes)"
            )

        # yaml.safe_load()로 안전하게 파싱 (yaml.load() 사용 금지)
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PromptLoadError(f"YAML 파싱 실패: {file_path} — {e}") from e

        if not isinstance(data, dict):
            raise PromptLoadError(f"유효하지 않은 YAML 구조: {file_path}")

        # --- 형식 분기 검증 ---
        if self._is_multi_version(data):
            # 멀티버전 형식 — versions가 비어있으면 에러
            if len(data["versions"]) == 0:
                raise PromptLoadError(
                    f"'versions' 필드가 비어있음: {file_path}. " f"최소 1개 버전이 존재해야 한다."
                )
            # 각 버전에 프롬프트가 존재하는지 검증
            for ver_key, ver_data in data["versions"].items():
                if not isinstance(ver_data, dict):
                    raise PromptLoadError(f"버전 '{ver_key}'의 데이터가 dict가 아님: {file_path}")
                if "system_prompt" not in ver_data and "prompts" not in ver_data:
                    raise PromptLoadError(
                        f"버전 '{ver_key}'에 'system_prompt' 또는 'prompts' 필드 누락: "
                        f"{file_path}. 최소 하나는 존재해야 한다."
                    )
            # 멀티버전 로그 — default_version 포함
            default_ver = data.get("default_version", next(iter(data["versions"])))
            logger.info(
                "프롬프트 로드 완료 (멀티버전): %s/%s (%d개 버전, default=%s)",
                mode,
                agent_name,
                len(data["versions"]),
                default_ver,
            )
        else:
            # legacy 형식 — 기존 검증 로직 유지
            # 필수 필드 검증 — version 누락 시 즉시 실패 (fail-fast)
            if "version" not in data:
                raise PromptLoadError(
                    f"필수 필드 'version' 누락: {file_path}. "
                    f"모든 프롬프트 YAML은 SemVer version 필드를 포함해야 한다. "
                    f"(PROMPT_SECURITY.md 7-1 참고)"
                )

            # 프롬프트 존재 검증 — system_prompt 또는 prompts 중 하나 필수
            if "system_prompt" not in data and "prompts" not in data:
                raise PromptLoadError(
                    f"'system_prompt' 또는 'prompts' 필드 누락: {file_path}. "
                    f"최소 하나는 존재해야 한다."
                )

            logger.info(
                "프롬프트 로드 완료: %s/%s (v%s)",
                mode,
                agent_name,
                data["version"],
            )

        # 캐시에 저장
        self._cache[cache_key] = data

        return data

    def _validate_path(self, resolved_path: Path) -> None:
        """
        경로 조작(Path Traversal) 방지.

        resolve()된 경로가 base_dir 범위 안에 있는지 검증한다.
        """
        try:
            resolved_path.relative_to(self._base_dir)
        except ValueError:
            raise PromptLoadError(
                f"경로 조작 감지 — 접근 거부: {resolved_path} " f"(base_dir: {self._base_dir})"
            )

    def clear_cache(self) -> None:
        """캐시를 초기화한다 (테스트 또는 프롬프트 핫리로드 시 사용)."""
        self._cache.clear()


def get_prompt_base_dir() -> str:
    """
    환경변수에서 프롬프트 디렉토리를 가져온다.

    PROMPT_DIR 환경변수가 설정되어 있으면 해당 값을 사용하고,
    없으면 기본값 "prompts"를 반환한다.
    """
    return os.getenv("PROMPT_DIR", "prompts")

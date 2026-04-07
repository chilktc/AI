"""
설정 로더 — YAML 파일과 환경변수를 통합 관리.

[Shared Infrastructure — 인터페이스 변경 금지]
기존 public 메서드/프로퍼티(get_settings, get_model_id, get_agent_config,
get_prompt_version, get_ab_test_config, llm_provider 등)의
시그니처와 동작을 변경하지 마시오.
신규 메서드 추가만 허용. 수정 시 전체 테스트(pytest tests/ -v) 통과 필수.

사용법:
    from config.loader import get_settings
    settings = get_settings()
    model_id = settings.get_model_id("sonnet")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()


def _deep_merge(base: dict, update: dict) -> dict:
    """기본 설정(base)에 환경별 설정(update)을 깊은 복사로 덮어쓰는 함수"""
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# 설정 파일 경로 (프로젝트 루트 기준)
_CONFIG_DIR = Path(__file__).parent
_SETTINGS_PATH = _CONFIG_DIR / "settings.yaml"


class Settings:
    """
    통합 설정 관리자.

    YAML 파일을 기본값으로 사용하고, 환경변수로 오버라이드할 수 있다.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """설정 파일을 로드하고, APP_ENV에 따라 환경별 설정을 오버레이한다."""
        # 1. 기본 settings.yaml 로드
        base_path = config_path or _SETTINGS_PATH
        with open(base_path, encoding="utf-8") as f:
            self._config: dict[str, Any] = yaml.safe_load(f)

        # 2. [B-5 핵심] APP_ENV에 따른 추가 설정 로드 (예: settings.production.yaml)
        env = os.getenv("APP_ENV", "development").lower()
        if env != "development":
            env_settings_path = _CONFIG_DIR / f"settings.{env}.yaml"
            if env_settings_path.exists():
                with open(env_settings_path, encoding="utf-8") as f:
                    env_config = yaml.safe_load(f)
                    if env_config:
                        # 기존 설정 위에 환경별 설정을 덮어씀
                        self._config = _deep_merge(self._config, env_config)

    @property
    def app_name(self) -> str:
        """앱 이름 반환."""
        return str(self._config["app"]["name"])

    @property
    def app_version(self) -> str:
        """앱 버전 반환."""
        return str(self._config["app"]["version"])

    # --- LLM 설정 ---

    @property
    def llm_provider(self) -> str:
        """LLM 프로바이더. 환경변수 LLM_PROVIDER로 오버라이드 가능."""
        env_value = os.getenv("LLM_PROVIDER")
        if env_value:
            return env_value
        return str(self._config["llm"].get("provider", "anthropic"))

    @property
    def bedrock_region(self) -> str:
        """AWS Bedrock 리전. 환경변수 AWS_REGION으로 오버라이드 가능."""
        env_value = os.getenv("AWS_REGION")
        if env_value:
            return env_value
        return str(self._config["llm"].get("bedrock", {}).get("region", "ap-northeast-2"))

    @property
    def bedrock_config(self) -> dict[str, Any]:
        """AWS Bedrock 설정 전체를 반환한다."""
        return cast(
            dict[str, Any],
            self._config["llm"].get("bedrock", {}),
        )

    @property
    def prompt_caching_config(self) -> dict[str, Any]:
        """프롬프트 캐싱 설정을 반환한다.

        Returns:
            {"enabled": bool, "min_tokens": int}
        """
        return cast(
            dict[str, Any],
            self._config.get("llm", {}).get("prompt_caching", {}),
        )

    def get_model_id(self, model_key: str) -> str:
        """
        모델 키에 해당하는 Anthropic 직접 API 모델 ID를 반환한다.

        환경변수 LLM_MODEL_{KEY}로 오버라이드 가능.
        예: LLM_MODEL_SONNET=claude-sonnet-4-20250514

        Args:
            model_key: 모델 키 (haiku, sonnet, opus)

        Returns:
            모델 ID 문자열
        """
        # 환경변수 오버라이드 확인
        env_key = f"LLM_MODEL_{model_key.upper()}"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

        return str(self._config["llm"]["models"][model_key])

    def get_bedrock_model_id(self, model_key: str) -> str:
        """
        모델 키에 해당하는 AWS Bedrock 모델 ID를 반환한다.

        환경변수 LLM_BEDROCK_MODEL_{KEY}로 오버라이드 가능.
        예: LLM_BEDROCK_MODEL_SONNET=anthropic.claude-sonnet-4-5-20250929-v2:0

        Args:
            model_key: 모델 키 (haiku, sonnet, opus)

        Returns:
            Bedrock 모델 ID 문자열
        """
        # 환경변수 오버라이드 확인
        env_key = f"LLM_BEDROCK_MODEL_{model_key.upper()}"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

        bedrock_models = self._config["llm"].get("bedrock_models", {})
        if model_key in bedrock_models:
            return str(bedrock_models[model_key])

        # fallback: 기본 Anthropic 모델 ID 사용
        return self.get_model_id(model_key)

    def get_openai_model_id(self, model_key: str) -> str:
        """
        모델 키에 해당하는 OpenAI 모델 ID를 반환한다.

        환경변수 LLM_OPENAI_MODEL_{KEY}로 오버라이드 가능.
        예: LLM_OPENAI_MODEL_SONNET=gpt-4o

        Args:
            model_key: 모델 키 (haiku, sonnet, opus)

        Returns:
            OpenAI 모델 ID 문자열
        """
        # 환경변수 오버라이드 확인
        env_key = f"LLM_OPENAI_MODEL_{model_key.upper()}"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value

        openai_models = self._config["llm"].get("openai_models", {})
        if model_key in openai_models:
            return str(openai_models[model_key])

        # fallback: 기본 모델
        return "gpt-4o-mini"

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """
        에이전트별 설정을 반환한다.

        Args:
            agent_name: 에이전트 이름 (예: content_analyzer, batch_validator)

        Returns:
            에이전트 설정 dict (model, max_tokens, temperature 등)
        """
        agent_config = self._config.get("agents", {}).get(agent_name, {})

        # 모델 키를 실제 모델 ID로 변환
        if "model" in agent_config:
            model_key = agent_config["model"]
            agent_config = {**agent_config, "model_id": self.get_model_id(model_key)}

        # temperature가 없으면 기본값 사용
        if "temperature" not in agent_config:
            agent_config["temperature"] = self._config["llm"]["temperature"]["default"]

        # max_tokens가 없으면 기본값 사용
        if "max_tokens" not in agent_config:
            agent_config["max_tokens"] = self._config["llm"]["default_max_tokens"]

        return cast(dict[str, Any], agent_config)

    # --- 파이프라인 설정 ---

    @property
    def max_retries(self) -> int:
        """파이프라인 TIER 3 → TIER 2 재시도 상한."""
        return int(self._config["pipeline"]["max_retries"])

    @property
    def max_critical_retries(self) -> int:
        """CRITICAL_FAIL 전용 재시도 상한."""
        return int(self._config["pipeline"].get("max_critical_retries", 4))

    @property
    def tier0_timeout(self) -> int:
        """TIER 0 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("tier0_timeout_seconds", 10))

    @property
    def tier1_timeout(self) -> int:
        """TIER 1 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("tier1_timeout_seconds", 30))

    @property
    def tier2_timeout(self) -> int:
        """TIER 2 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("tier2_timeout_seconds", 140))

    @property
    def tier3_timeout(self) -> int:
        """TIER 3 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("tier3_timeout_seconds", 50))

    @property
    def tier4_timeout(self) -> int:
        """TIER 4 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("tier4_timeout_seconds", 10))

    @property
    def async_timeout(self) -> int:
        """비동기 작업 타임아웃 (초)."""
        return int(self._config.get("pipeline", {}).get("async_timeout_seconds", 30))

    # --- API 설정 ---

    @property
    def api_base_url(self) -> str:
        """백엔드 API 기본 URL. 환경변수 BACKEND_API_URL로 설정.

        GitHub Actions에서 미등록 Secret은 빈 문자열로 치환되므로
        빈 문자열인 경우에도 기본값을 사용한다.
        """
        val = os.getenv("BACKEND_API_URL", "").strip()
        return val if val else "http://localhost:8080/api/v1"

    @property
    def api_timeout(self) -> int:
        """API 기본 타임아웃 (초)."""
        return int(self._config["api"]["timeout"])

    @property
    def api_max_retries(self) -> int:
        """API 최대 재시도 횟수."""
        return int(self._config["api"]["max_retries"])

    @property
    def allowed_origins(self) -> list[str]:
        """CORS 허용 오리진 목록. 환경변수로 전달받거나 기본값을 쓴다."""
        origins_str = os.getenv("ALLOWED_ORIGINS", "*")
        return [o.strip() for o in origins_str.split(",")]

    # --- 프롬프트 버전 관리 (v8) ---

    def get_prompt_version(self, agent_name: str) -> str | None:
        """
        에이전트별 프롬프트 타겟 버전을 반환한다.

        해석 우선순위:
            1. prompts.versions.{agent_name} (에이전트별 핀닝)
            2. prompts.versions.default (글로벌 기본값)
            3. None (PromptLoader의 YAML 내부 default_version 사용)

        Args:
            agent_name: 에이전트 이름 (예: "content_analyzer")

        Returns:
            타겟 버전 문자열 또는 None
        """
        prompts_config = self._config.get("prompts", {})
        versions_config = prompts_config.get("versions", {})

        # 에이전트별 핀닝 확인
        agent_version = versions_config.get(agent_name)
        if agent_version is not None:
            return str(agent_version)

        # 글로벌 기본값 확인
        default_version = versions_config.get("default")
        if default_version is not None:
            return str(default_version)

        return None

    def get_ab_test_config(self, agent_name: str) -> dict[str, Any] | None:
        """
        에이전트별 A/B 테스트 설정을 반환한다.

        prompts.ab_tests.{agent_name}에서 enabled=true인 설정을 반환한다.
        비활성이거나 설정이 없으면 None을 반환한다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            A/B 테스트 설정 dict 또는 None

        반환 형식 예시:
            {
                "enabled": True,
                "variant_a": "1.0.0",
                "variant_b": "1.1.0",
                "traffic_split": 0.5,
                "assignment": "session",
            }
        """
        prompts_config = self._config.get("prompts", {})
        ab_tests = prompts_config.get("ab_tests", {})

        ab_config = ab_tests.get(agent_name)
        if ab_config is None:
            return None

        if not isinstance(ab_config, dict):
            return None

        # enabled가 true인 경우만 반환
        if not bool(ab_config.get("enabled", False)):
            return None

        return cast(dict[str, Any], ab_config)

    # --- 모니터링 설정 ---

    @property
    def langsmith_tracing_enabled(self) -> bool:
        """LangSmith 트레이싱 활성화 여부 (settings.yaml 기준)."""
        monitoring = self._config.get("monitoring", {})
        langsmith = monitoring.get("langsmith", {})
        return bool(langsmith.get("tracing_enabled", False))

    # --- 저장소 설정 ---

    @property
    def storage_mode(self) -> str:
        """저장소 모드. STORAGE_MODE 환경변수로 오버라이드 가능."""
        return os.getenv(
            "STORAGE_MODE",
            self._config.get("storage", {}).get("mode", "local"),
        )

    @property
    def s3_bucket(self) -> str:
        """S3 버킷명."""
        return os.getenv(
            "AWS_S3_BUCKET",
            self._config.get("storage", {}).get("s3", {}).get("bucket", "mindlog-images"),
        )

    @property
    def s3_upload_prefix(self) -> str:
        """S3 업로드 prefix."""
        return str(self._config.get("storage", {}).get("s3", {}).get("upload_prefix", "vis"))

    @property
    def circuit_breaker_config(self) -> dict[str, Any]:
        """Circuit Breaker 설정을 반환한다."""
        return cast(dict[str, Any], self._config.get("llm", {}).get("circuit_breaker", {}))

    @property
    def pii_sanitization_enabled(self) -> bool:
        """PII 정제 활성화 여부를 반환한다."""
        return bool(
            self._config.get("security", {}).get("pii_sanitization", {}).get("enabled", True)
        )



# 싱글톤 인스턴스 (모듈 레벨에서 한 번만 로드)
_settings_instance: Settings | None = None


def get_settings() -> Settings:
    """설정 싱글톤 인스턴스를 반환한다."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

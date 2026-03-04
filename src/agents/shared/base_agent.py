"""
BaseAgent — 모든 에이전트의 공통 부모 클래스.

[Shared Infrastructure — 인터페이스 변경 금지]
기존 public 메서드(process, __call__, call_llm, call_llm_json,
get_prompt, create_message)의 시그니처와 동작을 변경하지 마시오.
신규 메서드 추가만 허용. 수정 시 전체 테스트(pytest tests/ -v) 통과 필수.

에이전트마다 반복되는 공통 코드를 한 곳에 모아
코드 중복을 방지하고 프로토콜 규격 변경에 유연하게 대응한다.

포함 기능:
    - LLM 클라이언트 자동 초기화
    - 처리 시간 자동 측정 (audit.processing_time_ms)
    - 로깅 (에이전트명, TIER 정보)
    - 메시지 프로토콜 v2.0 엔벨로프 생성
    - 멀티버전 프롬프트 지원 + A/B 테스트 (v8)

각 에이전트는 이 클래스를 상속하고 process() 메서드만 구현하면 된다.
"""

from __future__ import annotations

import contextvars
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Any

from config.loader import get_settings
from src.agents.shared.llm_client import LLMClient
from src.agents.shared.prompt_loader import PromptLoader, PromptLoadError, get_prompt_base_dir
from src.models.agent_state import AgentState
from src.models.message import (
    MessageAudit,
    MessageEnvelope,
    MessageMetadata,
    MessageType,
    Priority,
)
from src.utils.logger import get_agent_logger

# A/B 테스트 시 async 태스크별 활성 variant를 격리하는 ContextVar
# LangGraph 병렬 실행에서 태스크별 독립 버전 선택이 필요하다
_active_ab_variant: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_ab_variant", default=None
)


class BaseAgent(ABC):
    """
    모든 에이전트의 기본 클래스.

    Args:
        name: 에이전트 이름 (예: content_analyzer, batch_validator)
        tier: TIER 레벨 (0-4, 비동기/독립은 None)
        model_override: 설정 대신 직접 모델 ID를 지정할 때 사용

    사용 예시:
        class ContentAnalyzerAgent(BaseAgent):
            def __init__(self):
                super().__init__(name="content_analyzer", tier=1)

            async def process(self, state: AgentState) -> dict[str, Any]:
                # 에이전트 로직 구현
                return {"content_analysis": {...}}
    """

    def __init__(
        self,
        name: str,
        tier: int | None = None,
        model_override: str | None = None,
    ) -> None:
        self.name = name
        self.tier = tier
        self.logger = get_agent_logger(name)
        self.llm_client = LLMClient(
            agent_name=name,
            model_override=model_override,
        )
        # LLM 호출 횟수 추적 (audit용)
        self._llm_call_count = 0
        # 프롬프트 로더 초기화 — YAML 파일에서 프롬프트를 로드한다
        self._prompt_loader = PromptLoader(base_dir=get_prompt_base_dir())
        self._prompt_mode = self._resolve_mode()

        # --- v8: 멀티버전 + A/B 테스트 ---
        self._target_version = self._resolve_target_version()
        self._ab_config = self._resolve_ab_config()

        # 기본 프롬프트 로드 (타겟 버전 사용)
        self._prompts: dict[str, str] = self._load_prompts()
        # 프롬프트 버전 — YAML에서 로드 성공 시 SemVer, 실패 시 None
        self._prompt_version: str | None = self._load_prompt_version()

        # A/B 테스트 활성 시 양쪽 variant 프롬프트를 미리 로드
        self._ab_prompts: dict[str, dict[str, str]] = {}
        if self._ab_config is not None:
            self._preload_ab_variants()

        # 현재 실행에서 선택된 A/B variant (Telemetry 추적용)
        self._current_ab_variant: str | None = None

        # I/O 스냅샷 — 직전 실행의 입출력 기록 (모니터링용)
        self._last_input_snapshot: dict[str, Any] | None = None
        self._last_output_snapshot: dict[str, Any] | None = None

    # --- v8: 버전 해석 ---

    def _resolve_target_version(self) -> str | None:
        """
        settings.yaml에서 이 에이전트의 타겟 프롬프트 버전을 가져온다.

        해석 우선순위:
            1. settings.yaml prompts.versions.{agent_name}
            2. settings.yaml prompts.versions.default
            3. None (PromptLoader YAML 내부 default_version 사용)
        """
        try:
            settings = get_settings()
            return settings.get_prompt_version(self.name)
        except Exception:
            # settings 로드 실패 시 None (PromptLoader 기본 동작)
            return None

    def _resolve_ab_config(self) -> dict[str, Any] | None:
        """
        settings.yaml에서 A/B 테스트 설정을 가져온다.

        enabled=true인 설정만 반환, 없으면 None.
        """
        try:
            settings = get_settings()
            return settings.get_ab_test_config(self.name)
        except Exception:
            return None

    def _preload_ab_variants(self) -> None:
        """
        A/B 테스트 활성 시 양쪽 variant의 프롬프트를 미리 로드한다.

        variant_a와 variant_b 모두 YAML에 존재해야 한다.
        로드 실패 시 A/B 비활성화 (fallback to default).
        """
        if self._ab_config is None:
            return

        variant_a = str(self._ab_config.get("variant_a", ""))
        variant_b = str(self._ab_config.get("variant_b", ""))

        try:
            prompts_a = self._prompt_loader.load_all(
                self._prompt_mode, self.name, version=variant_a
            )
            prompts_b = self._prompt_loader.load_all(
                self._prompt_mode, self.name, version=variant_b
            )
            self._ab_prompts[variant_a] = prompts_a
            self._ab_prompts[variant_b] = prompts_b
            self.logger.info(
                "A/B 테스트 프리로드 완료: %s (A=%s, B=%s)",
                self.name,
                variant_a,
                variant_b,
            )
        except PromptLoadError as e:
            # variant 로드 실패 → A/B 비활성화
            self.logger.warning(
                "A/B 테스트 프리로드 실패 → 비활성화: %s — %s",
                self.name,
                str(e),
            )
            self._ab_config = None
            self._ab_prompts = {}

    def _resolve_ab_variant(self, session_id: str) -> str:
        """
        세션 ID 기반으로 A/B variant를 결정적으로 선택한다.

        동일 session_id + agent_name → 항상 동일한 variant 반환.
        hash 기반이므로 균등 분포에 가깝다.

        Args:
            session_id: 세션 ID (AgentState에서 가져옴)

        Returns:
            선택된 버전 문자열 (variant_a 또는 variant_b)
        """
        assert self._ab_config is not None  # noqa: S101

        variant_a = str(self._ab_config["variant_a"])
        variant_b = str(self._ab_config["variant_b"])
        traffic_split = float(self._ab_config.get("traffic_split", 0.5))
        assignment = str(self._ab_config.get("assignment", "session"))

        if assignment == "session":
            # 결정적 할당 — session_id + agent_name 조합의 hash
            hash_input = f"{session_id}:{self.name}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)  # noqa: S324
            ratio = (hash_value % 10000) / 10000.0
        else:
            # 요청 단위 랜덤 — time.monotonic 기반 의사 랜덤
            import random

            ratio = random.random()  # noqa: S311

        return variant_a if ratio < traffic_split else variant_b

    # --- 프롬프트 로딩 ---

    def _load_prompts(self) -> dict[str, str]:
        """
        에이전트별 프롬프트를 YAML에서 로드한다.

        v8: settings.yaml에서 지정된 타겟 버전으로 로드한다.
        프롬프트 파일이 없으면 빈 dict를 반환한다 (하위 호환).
        """
        try:
            return self._prompt_loader.load_all(
                self._prompt_mode, self.name, version=self._target_version
            )
        except PromptLoadError:
            # 프롬프트 파일이 없는 에이전트도 정상 동작 (다른 개발자 담당 등)
            self.logger.debug(
                "프롬프트 YAML 없음: %s/%s — 하드코딩 프롬프트 사용 가능",
                self._prompt_mode,
                self.name,
            )
            return {}

    def _load_prompt_version(self) -> str | None:
        """
        프롬프트 YAML의 버전(SemVer)을 로드한다.

        v8: settings에서 지정된 타겟 버전을 반환한다.
        프롬프트 파일이 없는 에이전트는 None을 반환한다.
        """
        if not self._prompts:
            return None
        try:
            return self._prompt_loader.get_version(
                self._prompt_mode, self.name, version=self._target_version
            )
        except PromptLoadError:
            return None

    def _resolve_mode(self) -> str:
        """
        에이전트가 속한 모드를 추론한다.

        모듈 경로를 검사하여 podcast/conversation/shared를 판별한다.
        판별 불가 시 "shared"를 기본값으로 반환한다.
        """
        module = type(self).__module__ or ""
        if ".podcast." in module or "podcast" in module:
            return "podcast"
        elif ".conversation." in module or "conversation" in module:
            return "conversation"
        return "shared"

    @property
    def prompt_version(self) -> str | None:
        """
        현재 로드된 프롬프트의 SemVer 버전을 반환한다.

        YAML 파일이 없는 에이전트는 None을 반환한다.
        Telemetry Agent 등 외부에서 버전을 추적할 때 사용한다.
        """
        return self._prompt_version

    @property
    def ab_variant(self) -> str | None:
        """
        현재 실행에서 선택된 A/B variant를 반환한다.

        A/B 테스트가 비활성이면 None.
        Telemetry에서 어떤 variant로 실행되었는지 추적할 때 사용한다.
        """
        return self._current_ab_variant

    def get_prompt(self, key: str = "system_prompt") -> str:
        """
        YAML에서 로드된 프롬프트를 반환한다.

        A/B 테스트 활성 시: contextvars에서 현재 variant를 읽어
        해당 variant의 프롬프트를 반환한다.
        A/B 비활성 시: 기본 프롬프트를 반환한다.

        Args:
            key: 프롬프트 키 (단일 프롬프트: "system_prompt", 다중: "got"/"tot"/"cot" 등)

        Returns:
            프롬프트 문자열

        Raises:
            KeyError: 해당 키의 프롬프트가 없을 때
        """
        # A/B 테스트 활성 시 — contextvars에서 variant 확인
        active_variant = _active_ab_variant.get()
        if active_variant is not None and active_variant in self._ab_prompts:
            variant_prompts = self._ab_prompts[active_variant]
            if key not in variant_prompts:
                raise KeyError(
                    f"프롬프트 키 '{key}'를 찾을 수 없음 "
                    f"(에이전트: {self.name}, variant: {active_variant}). "
                    f"사용 가능한 키: {list(variant_prompts.keys())}"
                )
            return variant_prompts[key]

        # 기본 프롬프트 반환
        if key not in self._prompts:
            raise KeyError(
                f"프롬프트 키 '{key}'를 찾을 수 없음 (에이전트: {self.name}). "
                f"사용 가능한 키: {list(self._prompts.keys())}"
            )
        return self._prompts[key]

    @abstractmethod
    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        에이전트 핵심 로직.

        자기 담당 필드만 포함한 dict를 반환한다.
        LangGraph StateGraph가 반환된 dict를 기존 상태에 자동 merge한다.

        Args:
            state: 현재 AgentState (전체 상태 읽기 가능)

        Returns:
            업데이트할 필드만 포함한 dict
        """
        ...

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        """
        LangGraph 노드 함수로 사용하기 위한 호출 인터페이스.

        v8: A/B 테스트 활성 시 session_id로 variant를 결정하고
        contextvars에 설정하여 process() 내부의 get_prompt() 호출이
        올바른 variant 프롬프트를 반환하도록 한다.
        """
        tier_label = f"TIER {self.tier}" if self.tier is not None else "ASYNC"
        version_label = f" (prompt v{self._prompt_version})" if self._prompt_version else ""

        # A/B 테스트 variant 결정
        ab_label = ""
        token: contextvars.Token[str | None] | None = None
        if self._ab_config is not None and self._ab_prompts:
            session_id = state.get("session_id", "unknown")
            variant = self._resolve_ab_variant(str(session_id))
            self._current_ab_variant = variant
            token = _active_ab_variant.set(variant)
            ab_label = f" [A/B: {variant}]"

        self.logger.info("[%s] %s 시작%s%s", tier_label, self.name, version_label, ab_label)

        # LLM 호출 카운터 초기화
        self._llm_call_count = 0
        self.llm_client.reset_total_usage()
        start_time = time.monotonic()

        # I/O 스냅샷 — 입력 상태 기록
        self._last_input_snapshot = self._sanitize_state_snapshot(state)

        try:
            result = await self._traced_process(state, tier_label)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            # I/O 스냅샷 — 출력 결과 기록
            self._last_output_snapshot = result

            self.logger.info(
                "[%s] %s 완료 (%dms, LLM %d회)%s",
                tier_label,
                self.name,
                elapsed_ms,
                self._llm_call_count,
                ab_label,
            )
            return result

        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            self.logger.error(
                "[%s] %s 실패 (%dms) — %s: %s",
                tier_label,
                self.name,
                elapsed_ms,
                type(e).__name__,
                str(e),
            )
            raise

        finally:
            # contextvars 정리 — 이전 값으로 복원
            if token is not None:
                _active_ab_variant.reset(token)
                self._current_ab_variant = None

    async def _traced_process(
        self, state: AgentState, tier_label: str,
    ) -> dict[str, Any]:
        """
        LangSmith 트레이싱으로 감싼 process() 실행.

        langsmith가 설치되어 있으면 에이전트 이름으로 child span을 생성하여
        Fan-out 노드 내부의 개별 에이전트가 LangSmith UI에 표시된다.
        langsmith가 없으면 process()를 직접 실행한다 (graceful degradation).

        메타데이터에 프롬프트 버전, A/B variant, 모델 정보를 포함하여
        LangSmith에서 에이전트별 필터링과 성능 분석이 가능하다.
        """
        try:
            from langsmith import traceable  # type: ignore[import-untyped]
        except ImportError:
            return await self.process(state)

        mode = state.get("mode", "unknown")

        @traceable(
            name=self.name,
            run_type="chain",
            tags=[tier_label, f"mode:{mode}"],
            metadata={
                "agent_name": self.name,
                "tier": self.tier,
                "prompt_version": self._prompt_version,
                "ab_variant": self._current_ab_variant,
                "model_id": self.llm_client.model_id,
            },
        )
        async def _run(s: AgentState) -> dict[str, Any]:
            return await self.process(s)

        return await _run(state)

    async def _traced_llm_call(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs: Any,
    ) -> str:
        """
        LangSmith LLM 스팬으로 감싼 LLM 호출.

        settings.yaml의 monitoring.langsmith.tracing_enabled=true이고
        langsmith가 설치되어 있으면 run_type="llm" child 스팬을 생성하여
        LangSmith 대시보드의 LLM Count, Token Usage, Cost가 표시된다.
        비활성 또는 미설치 시 llm_client.generate()를 직접 호출한다.
        """
        # 설정 확인 — tracing 비활성 시 직접 호출
        try:
            if not get_settings().langsmith_tracing_enabled:
                return await self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    **kwargs,
                )
        except Exception:
            pass

        # langsmith 미설치 시 직접 호출 (graceful degradation)
        try:
            from langsmith import traceable  # type: ignore[import-untyped]
        except ImportError:
            return await self.llm_client.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                **kwargs,
            )

        @traceable(
            name=self.llm_client.model_id,
            run_type="llm",
            metadata={
                "ls_provider": self.llm_client.provider,
                "ls_model_name": self.llm_client.model_id,
            },
        )
        async def _llm_run(
            messages: list[dict[str, str]],
            model: str,
            **kw: Any,
        ) -> dict[str, Any]:
            text = await self.llm_client.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                **kwargs,
            )
            usage = self.llm_client.last_usage or {}
            return {
                "text": text,
                "usage_metadata": {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            }

        result = await _llm_run(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=self.llm_client.model_id,
        )
        return str(result["text"]) if isinstance(result, dict) else str(result)

    async def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs: Any,
    ) -> str:
        """
        LLM 텍스트 생성 + 호출 횟수 자동 추적.

        process() 내에서 self.llm_client.generate() 대신 이 메서드를 사용하면
        audit.llm_calls가 자동으로 집계된다.
        """
        self._llm_call_count += 1
        return await self._traced_llm_call(
            system_prompt=system_prompt,
            user_message=user_message,
            **kwargs,
        )

    async def call_llm_json(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        LLM JSON 생성 + 호출 횟수 자동 추적.

        process() 내에서 self.llm_client.generate_json() 대신 이 메서드를 사용하면
        audit.llm_calls가 자동으로 집계된다.
        """
        self._llm_call_count += 1
        raw_text = await self._traced_llm_call(
            system_prompt=system_prompt,
            user_message=user_message,
            **kwargs,
        )
        return self.llm_client._parse_json_response(raw_text)

    async def call_image_gen(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> dict[str, Any]:
        """
        이미지 생성 API를 호출하고 로컬에 저장한다.

        Visualization Agent에서 사용한다.
        LLM 프로바이더와 무관하게 항상 OpenAI Images API를 통해 이미지를 생성한다.
        생성된 이미지는 data/outputs/images/ 폴더에 PNG로 저장된다.

        Args:
            prompt: 이미지 생성 프롬프트 (영문 권장)
            model: 이미지 모델 (기본: dall-e-3)
            size: 이미지 크기 (기본: 1024x1024)
            quality: 이미지 품질 (standard / hd)

        Returns:
            {"url": "임시 URL", "local_path": "로컬 저장 경로"} 형태의 dict
        """
        import os
        from pathlib import Path

        import httpx
        import openai

        client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
        )

        response = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )

        image_url = response.data[0].url or ""
        self.logger.info("이미지 생성 완료: model=%s, size=%s", model, size)

        # 로컬 저장 — data/outputs/images/{timestamp}_{agent_name}.png
        local_path = ""
        try:
            images_dir = Path("data/outputs/images")
            images_dir.mkdir(parents=True, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{self.name}.png"
            file_path = images_dir / filename

            async with httpx.AsyncClient(timeout=30) as http_client:
                img_response = await http_client.get(image_url)
                img_response.raise_for_status()
                file_path.write_bytes(img_response.content)

            local_path = str(file_path)
            self.logger.info("이미지 로컬 저장 완료: %s", local_path)
        except Exception as e:
            self.logger.warning("이미지 로컬 저장 실패: %s", e)

        return {"url": image_url, "local_path": local_path}

    def create_message(
        self,
        receiver: str,
        message_type: MessageType,
        payload: dict[str, Any],
        session_id: str,
        mode: str = "podcast",
        priority: Priority = Priority.HIGH,
    ) -> MessageEnvelope:
        """
        다른 에이전트에게 보낼 메시지 엔벨로프를 생성한다.

        독립 에이전트(Memory, Knowledge 등)에 요청을 보낼 때 사용한다.
        메시지 프로토콜 v2.0 규격을 자동으로 따른다.

        Args:
            receiver: 수신 에이전트 이름
            message_type: 메시지 유형 (request, response 등)
            payload: 요청/응답 데이터
            session_id: 세션 ID
            mode: 실행 모드 (conversation / podcast)
            priority: 메시지 우선순위

        Returns:
            프로토콜 v2.0 규격의 MessageEnvelope
        """
        return MessageEnvelope(
            sender=self.name,
            receiver=receiver,
            message_type=message_type,
            payload=payload,
            metadata=MessageMetadata(
                session_id=session_id,
                mode=mode,  # type: ignore[arg-type]
                interaction_unit="episode" if mode == "podcast" else "turn",
                tier=self.tier,
                priority=priority,
            ),
            audit=MessageAudit(
                processing_time_ms=0,
                llm_calls=self._llm_call_count,
                status="ok",
            ),
        )

    # ------------------------------------------------------------------
    # 모니터링 — 실행 메트릭 및 I/O 스냅샷
    # ------------------------------------------------------------------

    def get_execution_metrics(self) -> dict[str, Any]:
        """직전 실행의 성능 메트릭을 반환한다.

        Telemetry 콜백 핸들러나 외부 모니터링 시스템에서
        에이전트별 성능 데이터를 수집할 때 사용한다.

        Returns:
            에이전트 이름, TIER, 프롬프트 버전, A/B variant,
            LLM 호출 횟수, 토큰 사용량, 모델 ID를 포함한 dict
        """
        return {
            "agent_name": self.name,
            "tier": self.tier,
            "prompt_version": self._prompt_version,
            "ab_variant": self._current_ab_variant,
            "llm_call_count": self._llm_call_count,
            "token_usage": self.llm_client.last_usage,
            "total_token_usage": self.llm_client.total_usage,
            "model_id": self.llm_client.model_id,
        }

    @property
    def last_input_snapshot(self) -> dict[str, Any] | None:
        """직전 실행의 입력 상태 스냅샷을 반환한다."""
        return self._last_input_snapshot

    @property
    def last_output_snapshot(self) -> dict[str, Any] | None:
        """직전 실행의 출력 결과 스냅샷을 반환한다."""
        return self._last_output_snapshot

    @staticmethod
    def _sanitize_state_snapshot(
        state: AgentState,
        max_chars: int = 2000,
    ) -> dict[str, Any]:
        """AgentState에서 모니터링용 스냅샷을 생성한다.

        민감정보 보호를 위해 문자열 값은 max_chars로 잘라내고,
        user_input은 길이만 기록한다.

        Args:
            state: 현재 AgentState
            max_chars: 문자열 값의 최대 길이

        Returns:
            sanitize된 상태 dict
        """
        snapshot: dict[str, Any] = {}
        for key, value in state.items():
            if key == "user_input":
                # 사용자 원문은 길이만 기록 (민감정보 보호)
                snapshot[key] = f"<len={len(str(value))}>"
            elif isinstance(value, str) and len(value) > max_chars:
                snapshot[key] = value[:max_chars] + "...<truncated>"
            elif isinstance(value, dict):
                # dict는 키 목록만 기록
                snapshot[key] = {
                    "_keys": list(value.keys()),
                    "_size": len(value),
                }
            else:
                snapshot[key] = value
        return snapshot

"""
LLM 클라이언트 — 멀티 프로바이더 (Anthropic + AWS Bedrock + 커스텀) 래퍼.

[Shared Infrastructure — 인터페이스 변경 금지]
기존 public 메서드(generate, generate_json, register_provider,
unregister_provider)의 시그니처와 동작을 변경하지 마시오.
신규 메서드 추가만 허용. 수정 시 전체 테스트(pytest tests/ -v) 통과 필수.

모든 에이전트가 이 클라이언트를 통해 LLM을 호출한다.
provider 설정에 따라 Anthropic SDK 직접 호출 또는 AWS Bedrock을 통해 호출한다.
register_provider()를 통해 외부 프로바이더(예: Ollama)를 플러그인으로 추가할 수 있다.

프로바이더 선택 우선순위:
    1. LLMClient 생성자의 provider_override 파라미터
    2. 환경변수 LLM_PROVIDER
    3. config/settings.yaml의 llm.provider 값

모델 ID는 config/settings.yaml에서 관리하며, 환경변수로 오버라이드 가능.
API 모델이 변경되어도 이 파일과 설정 파일만 수정하면 된다.
"""

from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from config.loader import get_settings


class LLMClient:
    """
    멀티 프로바이더 LLM 비동기 클라이언트.

    Anthropic 직접 API, AWS Bedrock, 커스텀 프로바이더를 동적으로 전환할 수 있다.
    에이전트별 모델과 파라미터를 설정에서 자동으로 가져온다.

    커스텀 프로바이더는 register_provider()로 런타임에 등록한다.
    dev/ 폴더의 부트스트랩 스크립트에서 Ollama 등 로컬 프로바이더를 등록하는 방식.

    Args:
        agent_name: 에이전트 이름 (설정에서 모델/토큰/temperature 조회용)
        model_override: 설정 대신 직접 모델 ID를 지정할 때 사용
        provider_override: 설정 대신 직접 프로바이더를 지정 ("anthropic" | "bedrock" | 커스텀)

    사용 예시:
        # 기본 사용 (settings.yaml의 provider 따름)
        client = LLMClient(agent_name="content_analyzer")
        result = await client.generate(
            system_prompt="너는 콘텐츠 분석가야.",
            user_message="오늘 기분이 안 좋아요.",
        )

        # Bedrock 명시 사용
        client = LLMClient(agent_name="content_analyzer", provider_override="bedrock")
    """

    # 외부 프로바이더 레지스트리 — register_provider()로 등록 (로컬 개발 전용)
    _custom_providers: dict[str, type] = {}

    @classmethod
    def register_provider(cls, name: str, provider_class: type) -> None:
        """
        외부 프로바이더를 등록한다 (로컬 개발 전용).

        등록된 프로바이더는 provider_override 또는 LLM_PROVIDER 환경변수로 활성화한다.
        dev/ 폴더의 부트스트랩 스크립트에서 호출하는 것을 권장한다.

        Args:
            name: 프로바이더 이름 (예: "ollama")
            provider_class: generate() 메서드를 가진 클래스.
                시그니처: async generate(system_prompt, user_message,
                max_tokens, temperature) → str
        """
        cls._custom_providers[name] = provider_class

    @classmethod
    def unregister_provider(cls, name: str) -> None:
        """
        등록된 외부 프로바이더를 제거한다 (테스트 정리용).

        Args:
            name: 제거할 프로바이더 이름
        """
        cls._custom_providers.pop(name, None)

    def __init__(
        self,
        agent_name: str,
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> None:
        settings = get_settings()
        agent_config = settings.get_agent_config(agent_name)

        # 프로바이더 결정 — override > 환경변수 > 설정 파일
        self._provider = provider_override or os.getenv("LLM_PROVIDER") or settings.llm_provider

        # 커스텀 프로바이더 인스턴스 (등록된 경우에만 사용)
        self._custom_provider_instance: Any = None

        # 프로바이더별 클라이언트 및 모델 ID 설정
        if self._provider in self._custom_providers:
            # 커스텀 프로바이더 (로컬 개발용 — dev/ 에서 등록)
            self._init_custom_provider(agent_config, model_override)
        elif self._provider == "bedrock":
            self._init_bedrock_client(settings)
            # Bedrock 전용 모델 ID — agent_config.model_id는 Anthropic 직접 API ID이므로
            # Bedrock에서는 반드시 get_bedrock_model_id()를 사용해야 한다.
            model_key = agent_config.get("model", "sonnet")
            self._model_id = model_override or settings.get_bedrock_model_id(model_key)
        elif self._provider == "openai":
            import openai

            self._openai_client = openai.AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )
            # OpenAI 전용 모델 ID — agent_config.model_id는 Anthropic 직접 API ID이므로
            # OpenAI에서는 반드시 get_openai_model_id()를 사용해야 한다.
            model_key = agent_config.get("model", "sonnet")
            self._model_id = model_override or settings.get_openai_model_id(model_key)
        else:
            # Anthropic 직접 API (기본)
            self._anthropic_client = anthropic.AsyncAnthropic()
            self._model_id = model_override or agent_config.get(
                "model_id", settings.get_model_id(agent_config.get("model", "sonnet"))
            )

        # 공통 파라미터
        self._max_tokens: int = agent_config.get("max_tokens", 4096)
        self._temperature: float = agent_config.get("temperature", 0.7)

        # 토큰 사용량 추적 — 직전 LLM 호출의 토큰 수를 저장한다
        self._last_usage: dict[str, int] | None = None
        # 누적 토큰 사용량 — 이 클라이언트 인스턴스의 전체 토큰 합산
        self._total_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def _init_custom_provider(
        self,
        agent_config: dict[str, Any],
        model_override: str | None,
    ) -> None:
        """
        커스텀 프로바이더를 초기화한다 (로컬 개발 전용).

        커스텀 프로바이더는 모델 매핑, base_url, timeout 등을
        자체 설정 파일(예: dev/ollama_config.yaml)에서 관리한다.
        """
        provider_cls = self._custom_providers[self._provider]
        model_key = agent_config.get("model", "sonnet")
        # 모델 ID는 override가 있으면 사용, 없으면 모델 키를 그대로 전달
        # (커스텀 프로바이더가 내부적으로 매핑)
        self._model_id = model_override or model_key
        self._custom_provider_instance = provider_cls(
            model_id=self._model_id,
        )

    def _init_bedrock_client(self, settings: Any) -> None:
        """
        AWS Bedrock 클라이언트를 초기화한다.

        boto3가 설치되어 있지 않으면 ImportError를 발생시킨다.
        AWS 인증은 환경변수(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        또는 IAM Role을 통해 자동으로 처리된다.
        """
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "AWS Bedrock 사용을 위해 boto3가 필요합니다. " "'pip install boto3'를 실행해주세요."
            ) from e

        # 리전 결정 — 환경변수 > 설정 파일
        region = os.getenv("AWS_REGION") or settings.bedrock_region
        bedrock_config = settings.bedrock_config

        # 엔드포인트 URL (선택)
        endpoint_url = bedrock_config.get("endpoint_url")
        kwargs: dict[str, Any] = {
            "service_name": "bedrock-runtime",
            "region_name": region,
        }
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._bedrock_client = boto3.client(**kwargs)

    @property
    def model_id(self) -> str:
        """현재 사용 중인 모델 ID."""
        return self._model_id

    @property
    def provider(self) -> str:
        """현재 사용 중인 프로바이더 ('anthropic' 또는 'bedrock')."""
        return self._provider

    @property
    def last_usage(self) -> dict[str, int] | None:
        """직전 LLM 호출의 토큰 사용량을 반환한다.

        Returns:
            {"input_tokens": N, "output_tokens": N, "total_tokens": N} 또는 None
        """
        return self._last_usage

    @property
    def total_usage(self) -> dict[str, int]:
        """이 클라이언트 인스턴스의 누적 토큰 사용량을 반환한다."""
        return self._total_usage.copy()

    def reset_total_usage(self) -> None:
        """누적 토큰 사용량을 초기화한다."""
        self._total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """토큰 사용량을 기록한다 (직전 + 누적)."""
        total = input_tokens + output_tokens
        self._last_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
        }
        self._total_usage["input_tokens"] += input_tokens
        self._total_usage["output_tokens"] += output_tokens
        self._total_usage["total_tokens"] += total

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """
        텍스트 응답을 생성한다.

        프로바이더에 따라 Anthropic 직접 API 또는 AWS Bedrock을 통해 호출한다.

        Args:
            system_prompt: 시스템 프롬프트 (에이전트 역할 정의)
            user_message: 사용자 메시지 (처리할 입력)
            max_tokens: 최대 토큰 수 (None이면 에이전트 설정값 사용)
            temperature: 샘플링 온도 (None이면 에이전트 설정값 사용)

        Returns:
            LLM이 생성한 텍스트 응답
        """
        actual_max_tokens = max_tokens or self._max_tokens
        actual_temperature = temperature or self._temperature

        if self._provider in self._custom_providers:
            # 커스텀 프로바이더 디스패치 (로컬 개발용)
            result: str = await self._custom_provider_instance.generate(
                system_prompt, user_message, actual_max_tokens, actual_temperature
            )
            return result
        elif self._provider == "bedrock":
            return await self._generate_bedrock(
                system_prompt, user_message, actual_max_tokens, actual_temperature
            )
        elif self._provider == "openai":
            return await self._generate_openai(
                system_prompt, user_message, actual_max_tokens, actual_temperature
            )
        else:
            return await self._generate_anthropic(
                system_prompt, user_message, actual_max_tokens, actual_temperature
            )

    # temperature를 지원하지 않는 OpenAI 모델 접두사 (reasoning 계열)
    _OPENAI_NO_TEMPERATURE_PREFIXES = ("o1", "o3", "o4", "gpt-5")

    async def _generate_openai(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """OpenAI 직접 API를 통한 텍스트 생성."""
        kwargs: dict[str, Any] = {
            "model": self._model_id,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        # reasoning 계열 모델은 temperature를 지원하지 않음
        if not self._model_id.startswith(self._OPENAI_NO_TEMPERATURE_PREFIXES):
            kwargs["temperature"] = temperature
        response = await self._openai_client.chat.completions.create(**kwargs)
        # 토큰 사용량 기록
        if response.usage:
            self._record_usage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
            )
        return response.choices[0].message.content

    async def _generate_anthropic(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Anthropic 직접 API를 통한 텍스트 생성."""
        response = await self._anthropic_client.messages.create(
            model=self._model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        # 토큰 사용량 기록
        self._record_usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        # 첫 번째 content block에서 텍스트 추출 (TextBlock 가정)
        return response.content[0].text  # type: ignore[union-attr]

    async def _generate_bedrock(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """
        AWS Bedrock을 통한 텍스트 생성.

        Bedrock의 Anthropic Claude Messages API 형식을 사용한다.
        boto3는 동기 클라이언트이므로 asyncio.to_thread로 감싸서 비동기 처리한다.
        """
        import asyncio

        request_body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }
        )

        # boto3는 동기 SDK — 이벤트루프 블로킹 방지를 위해 스레드풀에서 실행
        response = await asyncio.to_thread(
            self._bedrock_client.invoke_model,
            modelId=self._model_id,
            body=request_body,
            contentType="application/json",
            accept="application/json",
        )

        # 응답 파싱 (strict=False: 제어 문자 허용)
        response_body = json.loads(response["body"].read(), strict=False)
        # 토큰 사용량 기록 (Bedrock Anthropic 응답 형식)
        usage = response_body.get("usage", {})
        self._record_usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
        return str(response_body["content"][0]["text"])

    async def generate_json(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        JSON 구조화된 응답을 생성한다.

        시스템 프롬프트에 JSON 형식을 요청하는 내용을 포함해야 한다.
        응답에서 JSON을 추출하여 dict로 파싱한다.

        Args:
            system_prompt: 시스템 프롬프트 (JSON 출력 형식 명시 필수)
            user_message: 사용자 메시지
            max_tokens: 최대 토큰 수
            temperature: 샘플링 온도

        Returns:
            파싱된 JSON dict

        Raises:
            json.JSONDecodeError: JSON 파싱 실패 시
        """
        raw_response = await self.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # JSON 블록 추출 시도 (```json ... ``` 형식 대응)
        return self.parse_json_response(raw_response)

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any]:
        """
        LLM 응답 텍스트에서 JSON을 추출한다.

        마크다운 코드 블록(```json ... ```)이나 순수 JSON 텍스트 모두 처리.
        """
        cleaned = text.strip()

        # 마크다운 JSON 코드 블록 제거
        if cleaned.startswith("```"):
            # 첫 번째 줄(```json)과 마지막 줄(```) 제거
            lines = cleaned.split("\n")
            # 시작 마커 제거
            if lines[0].startswith("```"):
                lines = lines[1:]
            # 끝 마커 제거
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        # strict=False: 로컬 LLM(Ollama 등)이 JSON 문자열 내에
        # 제어 문자(줄바꿈, 탭 등)를 포함할 수 있으므로 허용한다.
        result: dict[str, Any] = json.loads(cleaned, strict=False)
        return result

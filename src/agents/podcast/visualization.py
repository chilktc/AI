"""
Visualization Agent — AWS Bedrock & S3 실전 연동 버전.
특징: settings.yaml 기반 설정 + S3 자동 업로드 + 내부 재시도.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import boto3  # type: ignore

from config.loader import get_settings
from src.agents.shared.base_agent import BaseAgent, ContentBlockedError
from src.models.agent_state import AgentState
from src.utils.logger import get_agent_logger

logger = get_agent_logger("visualization")

# AWS Titan 콘텐츠 정책 위반 키워드 — image_prompt에서 제거
_BLOCKED_EN: frozenset[str] = frozenset(
    {
        "person",
        "people",
        "human",
        "face",
        "portrait",
        "body",
        "hand",
        "hands",
        "eye",
        "eyes",
        "child",
        "woman",
        "man",
        "violence",
        "blood",
        "weapon",
        "gun",
        "knife",
        "death",
        "injury",
        "harm",
        "abuse",
        "kill",
        "attack",
        "doctor",
        "surgery",
        "hospital",
        "injection",
        "medical",
        "nude",
        "naked",
        "sexual",
    }
)

_BLOCKED_KO: frozenset[str] = frozenset(
    {
        "사람",
        "얼굴",
        "인간",
        "초상",
        "신체",
        "손",
        "눈",
        "아이",
        "여자",
        "남자",
        "여성",
        "남성",
        "어린이",
        "폭력",
        "피",
        "무기",
        "총",
        "칼",
        "죽음",
        "부상",
        "상해",
        "학대",
        "살인",
        "공격",
        "의사",
        "수술",
        "병원",
        "주사",
        "의료",
        "환자",
    }
)

BLOCKED_KEYWORDS: frozenset[str] = _BLOCKED_EN | _BLOCKED_KO

SAFE_FALLBACK_PROMPT = (
    "A strictly 2D flat abstract art. Extreme minimalism. "
    "Soft muted gradient with 2 simple geometric shapes. "
    "Dominant empty space. Fine grainy matte texture."
)


def _sanitize_image_prompt(prompt: str) -> str:
    """image_prompt에서 AWS 콘텐츠 정책 위반 키워드를 제거한다."""
    words = prompt.split()
    sanitized = [w for w in words if w.lower().strip(".,;:!?\"'()") not in BLOCKED_KEYWORDS]
    result = " ".join(sanitized)
    return result if result.strip() else SAFE_FALLBACK_PROMPT


class VisualizationAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="visualization", tier=2)
        settings = get_settings()
        self.max_retries = settings.max_retries
        self.bucket_name = settings.s3_bucket
        self.s3_client = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", settings.bedrock_region),
        )

    async def process(self, state: AgentState) -> dict[str, Any]:
        """이미지 기획부터 최종 S3 업로드까지 수행"""

        # SKIP_VISUALIZATION 환경변수로 이미지 생성 스킵
        if os.environ.get("SKIP_VISUALIZATION") == "true":
            return {"visual_data": {"status": "skipped"}}

        emotion = state.get("emotion_vectors", {})
        content = state.get("content_analysis", {})
        user_id = state.get("user_id", "anonymous")

        # CRISIS 폴백 — LLM/이미지 생성 미호출, placeholder image_url 반환
        # 백엔드 ingest_podcast_episodes()는 image_url 필수 → 빈 문자열 불가
        safety_flags: dict = state.get("safety_flags", {})
        if safety_flags.get("status") == "crisis":
            from src.agents.shared.safety_constants import CRISIS_FALLBACK_VALUES

            logger.info("[Visualization] CRISIS 폴백 — 이미지 생성 미호출")
            return {"visual_data": CRISIS_FALLBACK_VALUES["visual_data"]}

        # 1. [기획] 이미지 프롬프트 생성 (settings.yaml의 visualization.model 사용)
        system_prompt = self.get_prompt("system_prompt")
        user_context = (
            f"Emotion: {emotion}\nContent: {content}\nMode: {state.get('mode', 'podcast')}"
        )

        try:
            planning = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_context,
            )
        except Exception as e:
            logger.error("[Visualization] LLM 호출 실패 — 빈 이미지로 처리: %s", e)
            return {
                "visual_data": {
                    "status": "failed",
                    "error": "llm_call_failed",
                    "image_url": None,
                    "style_type": "abstract",
                    "interpretation": "",
                    "color_palette": [],
                }
            }
        image_prompt: str = planning.get("image_prompt") or ""
        image_prompt = _sanitize_image_prompt(image_prompt)

        # 2. [생성 및 검증] 자체 재시도 로직 가동
        result = await self._internal_generate_flow(image_prompt, user_id)

        return {
            "visual_data": {
                "image_url": result.get("url"),
                "s3_key": result.get("s3_key", ""),
                "status": result.get("status"),
                "retry_count": result.get("retry_count"),
                "error": result.get("error"),
                "style_type": str(planning.get("style_type") or "abstract"),
                "interpretation": str(planning.get("interpretation") or ""),
                "original_prompt": image_prompt,
            }
        }

    async def _internal_generate_flow(
        self, prompt: str, user_id: str, current_retry: int = 0
    ) -> dict[str, Any]:
        """내부 생성-업로드 루프 (settings.yaml의 image_model 사용)"""
        try:
            settings = get_settings()
            agent_config = settings.get_agent_config(self.name)
            image_model = agent_config.get("image_model", "amazon.titan-image-generator-v2:0")

            raw_res = await self.call_image_gen(
                prompt=prompt,
                model=image_model,
            )

            if not raw_res or "image_binary" not in raw_res:
                raise ValueError("이미지 데이터 생성 실패")

            upload_prefix = settings.s3_upload_prefix
            file_name = f"{user_id}_{uuid.uuid4().hex[:8]}.png"
            s3_key = f"{upload_prefix}/{file_name}"

            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=raw_res["image_binary"],
                ContentType="image/png",
            )

            return {
                "url": f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}",
                "s3_key": s3_key,
                "status": "completed",
                "retry_count": current_retry,
            }

        except ContentBlockedError as e:
            self.logger.warning(
                "AWS 콘텐츠 정책 차단 — 안전 프롬프트로 재시도 (%d/%d): %s",
                current_retry + 1,
                self.max_retries,
                e,
            )
            if current_retry < self.max_retries:
                return await self._internal_generate_flow(
                    SAFE_FALLBACK_PROMPT, user_id, current_retry + 1
                )
            return {
                "url": None,
                "status": "failed",
                "error": "content_blocked",
                "retry_count": current_retry,
            }

        except Exception as e:
            if current_retry < self.max_retries:
                wait_time = (current_retry + 1) * 2
                self.logger.warning(
                    "이미지 생성 재시도 (%d/%d): %s",
                    current_retry + 1,
                    self.max_retries,
                    e,
                )
                await asyncio.sleep(wait_time)
                return await self._internal_generate_flow(prompt, user_id, current_retry + 1)

            self.logger.error("이미지 생성 최종 실패 (%d회 재시도 후): %s", current_retry, e)
            return {"url": None, "status": "failed", "error": str(e), "retry_count": current_retry}


async def visualization_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Visualization Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = VisualizationAgent()
    return await agent(state)

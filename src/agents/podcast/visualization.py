"""
Visualization Agent — AWS Bedrock & S3 실전 연동 버전.
특징: settings.yaml 기반 설정 + S3 자동 업로드 + 내부 재시도.
"""
from __future__ import annotations

import asyncio
import os
import uuid
import logging
from typing import Any

import boto3  # type: ignore

from config.loader import get_settings
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)


class VisualizationAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="visualization", tier=2)
        settings = get_settings()
        self.max_retries = settings.max_retries
        self.bucket_name = settings.s3_bucket
        self.s3_client = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', settings.bedrock_region),
        )

    async def process(self, state: AgentState) -> dict[str, Any]:
        """이미지 기획부터 최종 S3 업로드까지 수행"""

        # SKIP_VISUALIZATION 환경변수로 이미지 생성 스킵
        if os.environ.get("SKIP_VISUALIZATION") == "true":
            return {"visual_data": {"status": "skipped"}}

        emotion = state.get("emotion_vectors", {})
        content = state.get("content_analysis", {})
        user_id = state.get("user_id", "anonymous")

        # 1. [기획] 이미지 프롬프트 생성 (settings.yaml의 visualization.model 사용)
        system_prompt = self.get_prompt("system_prompt")
        user_context = f"Emotion: {emotion}\nContent: {content}\nMode: {state.get('mode', 'podcast')}"

        planning = await self.call_llm_json(
            system_prompt=system_prompt,
            user_message=user_context,
        )
        image_prompt = planning.get("image_prompt")

        # 2. [생성 및 검증] 자체 재시도 로직 가동
        result = await self._internal_generate_flow(image_prompt, user_id)

        return {
            "visual_data": {
                "image_url": result.get("url"),
                "status": result.get("status"),
                "retry_count": result.get("retry_count"),
                "error": result.get("error"),
                "style_type": planning.get("style_type"),
                "interpretation": planning.get("interpretation"),
                "original_prompt": image_prompt
            }
        }

    async def _internal_generate_flow(self, prompt: str, user_id: str, current_retry: int = 0) -> dict[str, Any]:
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
                ContentType='image/png'
            )

            return {
                "url": f"https://{self.bucket_name}.s3.amazonaws.com/{s3_key}",
                "status": "completed",
                "retry_count": current_retry
            }

        except Exception as e:
            if current_retry < self.max_retries:
                wait_time = (current_retry + 1) * 2
                self.logger.warning(
                    "이미지 생성 재시도 (%d/%d): %s",
                    current_retry + 1, self.max_retries, e,
                )
                await asyncio.sleep(wait_time)
                return await self._internal_generate_flow(prompt, user_id, current_retry + 1)

            self.logger.error("이미지 생성 최종 실패 (%d회 재시도 후): %s", current_retry, e)
            return {
                "url": None,
                "status": "failed",
                "error": str(e),
                "retry_count": current_retry
            }


# --- 노드 래퍼 ---
visualization_agent = VisualizationAgent()
async def visualization_node(state: AgentState) -> dict[str, Any]:
    return await visualization_agent(state)

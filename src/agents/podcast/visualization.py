"""
Visualization Agent — AWS Bedrock & S3 실전 연동 버전.
특징: Claude 3.5 Sonnet 기반 기획 + S3 자동 업로드 + 내부 재시도.
"""
from __future__ import annotations

import asyncio
import boto3 # type: ignore
import uuid
import logging
import os
from typing import Any
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)

class VisualizationAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(name="visualization", tier=2)
        self.max_retries = 2
        self.s3_client = boto3.client('s3', region_name='ap-northeast-2') 
        # ✅ 인프라 팀에서 지정해준 새 버킷명으로 수정 완료
        self.bucket_name = "t7-mindlog-ai-assets" 

    async def process(self, state: AgentState) -> dict[str, Any]:
        """이미지 기획부터 최종 S3 업로드까지 수행"""
        
        """
        입력을 최적화하여 이미지 프롬프트를 기획하고,
        실제 이미지 생성 API를 통해 PNG를 획득한다.
        """
        # 0. SKIP_VISUALIZATION 환경변수로 이미지 생성 스킵 (프롬프트 최적화 시)
        if os.environ.get("SKIP_VISUALIZATION") == "true":
            return {"visual_data": {"status": "skipped"}}

        # 1. 입력값 최적화: 의논된 대로 감정 벡터와 콘텐츠 분석 데이터만 사용
        # final_output 등 불필요한 필드는 참조하지 않음으로써 토큰 효율 극대화
        emotion = state.get("emotion_vectors", {})
        content = state.get("content_analysis", {})
        user_id = state.get("user_id", "anonymous")
        
        # 1. [기획] 이미지 프롬프트 생성
        # ✅ Bedrock 카탈로그 중 가장 똑똑한 Claude 3.5 Sonnet을 사용하여 섬세한 묘사를 이끌어냅니다.
        planning_model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        
        system_prompt = self.get_prompt("system_prompt")
        user_context = f"Emotion: {emotion}\nContent: {content}\nMode: {state.get('mode', 'podcast')}"
        
        # 기획 단계에서 고성능 모델 사용
        planning = await self.call_llm_json(
            system_prompt=system_prompt, 
            user_message=user_context,
            model=planning_model 
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
        """내부 생성-업로드 루프 (AWS Titan Image Generator 사용 제안)"""
        try:
            # ✅ 이미지 생성 모델도 Bedrock용 Titan 모델로 변경 가능합니다.
            # 일단은 기존 DALL-E 3 구조를 유지하되, Bedrock 전용 모델(Titan)로 테스트 시 아래 model명을 변경하세요.
            raw_res = await self.call_image_gen(
                prompt=prompt, 
                model="amazon.titan-image-generator-v1" # Bedrock 이미지 모델 ID
            )
            
            if not raw_res or "image_binary" not in raw_res:
                raise ValueError("이미지 데이터 생성 실패")

            # S3 파일명 및 ai-generated/ 경로 설정
            file_name = f"{user_id}_{uuid.uuid4().hex[:8]}.png"
            s3_key = f"ai-generated/{file_name}"

            # S3 업로드 (읽기/쓰기 권한 확인 완료)
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
                logger.warning(f"[Visualization] 실패 재시도 중... ({current_retry + 1}/{self.max_retries}) - 사유: {e}")
                await asyncio.sleep(wait_time)
                return await self._internal_generate_flow(prompt, user_id, current_retry + 1)
            
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
"""
Visualization Agent — 감정 및 주제 기반 1024x1024 추상화 PNG 이미지 생성.
재시도(Retry) 로직 및 배치 시스템 접근성 최적화 버전.
"""
from __future__ import annotations

import asyncio
from typing import Any
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState

class VisualizationAgent(BaseAgent):
    """
    사용자의 감정 수치와 콘텐츠 분석 데이터를 바탕으로 
    이미지 가이드라인에 따른 추상화 PNG 이미지를 직접 생성한다.
    """

    def __init__(self) -> None:
        super().__init__(name="visualization", tier=2)
        # 기본 재시도 횟수 설정 (필요 시 외부에서 조절 가능)
        self.max_retries = 2 

    async def process(self, state: AgentState) -> dict[str, Any]:
        """기본 워크플로우: 프롬프트 기획 -> 이미지 생성(재시도 포함)"""
        
        # 1. 입력값 최적화
        emotion = state.get("emotion_vectors", {})
        content = state.get("content_analysis", {})
        
        # 2. [기획 단계] 이미지 전략 수립 (LLM 호출)
        system_prompt = self.get_prompt("system_prompt")
        user_context = (
            f"Emotion Vectors: {emotion}\n"
            f"Content Analysis: {content}\n"
            f"Mode: {state.get('mode', 'podcast')}"
        )
        
        planning = await self.call_llm_json(
            system_prompt=system_prompt,
            user_message=user_context
        )
        
        image_prompt = planning.get("image_prompt")
        
        # 3. [실행 단계] 이미지 생성 호출 (재시도 로직 메서드 활용)
        # 내부 로직과 외부 배치가 공통으로 사용하는 핵심 메서드 호출
        generation_result = await self.generate_with_retry(
            prompt=image_prompt,
            model="dall-e-3" # 모델명 차후 수정 필요
        )
        
        # 4. 결과 반환 (이슈 S-2 필드명 동기화 준수)
        return {
            "visual_data": {
                "image_url": generation_result.get("url"),
                "local_path": generation_result.get("local_path"),
                "style_type": planning.get("style_type"),
                "interpretation": planning.get("interpretation"),
                "original_prompt": image_prompt,
                "resolution": "1024x1024",
                "status": generation_result.get("status", "completed"),
                "retry_count": generation_result.get("retry_count", 0)
            }
        }

    async def generate_with_retry(self, prompt: str, model: str = "dall-e-3", retry_count: int = 0) -> dict[str, Any]:
        """
        실제 이미지 생성 API를 호출하며 실패 시 재시도한다.
        이 메서드는 외부(배치 시스템 등)에서 이미지 주소만 다시 따고 싶을 때 직접 호출 가능하다.
        """
        try:
            # 이미지 생성 API 호출 (S3 업로드 및 확장자 처리는 call_image_gen 내부에서 수행된다고 가정)
            result = await self.call_image_gen(
                prompt=prompt,
                model=model,
                size="1024x1024",
                quality="standard"
            )

            # 성공 여부 확인 (URL이 없으면 실패로 간주)
            if not result or not result.get("url"):
                raise ValueError("Image URL is missing from generation result")

            result["status"] = "completed"
            result["retry_count"] = retry_count
            return result

        except Exception as e:
            # 재시도 횟수가 남았는지 확인
            if retry_count < self.max_retries:
                wait_time = (retry_count + 1) * 2  # 점진적으로 대기 시간 증가 (지수 백오프)
                print(f"⚠️ [Visualization] 생성 실패 ({e}). {wait_time}초 후 재시도... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
                
                # 재귀적으로 재시도 호출
                return await self.generate_with_retry(prompt, model, retry_count + 1)
            else:
                # 최종 실패 시 보고
                print(f"❌ [Visualization] 최종 생성 실패: {e}")
                return {
                    "url": None,
                    "local_path": None,
                    "status": "failed",
                    "error": str(e),
                    "retry_count": retry_count
                }

# --- 싱글톤 + 노드 래퍼 ---
visualization_agent = VisualizationAgent()

async def visualization_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Visualization Agent."""
    return await visualization_agent(state)
"""
Visualization Agent — 감정 및 주제 기반 1024x1024 추상화 PNG 이미지 생성.

TIER: 비동기 (팟캐스트 TIER 2 병렬)
모델: 프롬프트 기획(Sonnet 4) + 이미지 생성(DALL-E 3)
"""
from __future__ import annotations

import os
from typing import Any
from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState

class VisualizationAgent(BaseAgent):
    """
    사용자의 감정 수치와 콘텐츠 분석 데이터를 바탕으로 
    이미지 가이드라인에 따른 추상화 PNG 이미지를 직접 생성한다.
    """

    def __init__(self) -> None:
        # 아키텍처 명세에 따라 에이전트 이름 및 TIER 설정
        super().__init__(name="visualization", tier=2)

    async def process(self, state: AgentState) -> dict[str, Any]:
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
        
        # 2. [기획 단계] 시스템 프롬프트(YAML) 기반 이미지 전략 수립
        # 스타일 가이드라인(Organic vs Geometric)에 따른 영문 프롬프트 생성
        system_prompt = self.get_prompt("system_prompt")
        user_context = (
            f"Emotion Vectors: {emotion}\n"
            f"Content Analysis: {content}\n"
            f"Mode: {state.get('mode', 'podcast')}"
        )
        
        # 기획 결과물 (image_prompt, style_type, interpretation 포함)
        planning = await self.call_llm_json(
            system_prompt=system_prompt,
            user_message=user_context
        )
        
        image_prompt = planning.get("image_prompt")
        
        # 3. [실행 단계] 실제 이미지 생성 API(DALL-E 3 등) 호출
        # 가이드라인에 따라 1024x1024 정사각형 PNG 생성을 보장한다.
        generation_result = await self.call_image_gen(
            prompt=image_prompt,
            model="dall-e-3", # 고품질 추상화 생성을 위해 DALL-E 3 사용
            size="1024x1024", # 1:1 정사각형 해상도 명시
            quality="standard"
        )
        
        # 4. [중요] 필드명 동기화: visualization_result -> visual_data (이슈 S-2 해결)
        # 최종 PNG URL과 해석을 AgentState 규격에 맞춰 반환한다.
        return {
            "visual_data": {
                "image_url": generation_result.get("url"),
                "local_path": generation_result.get("local_path"),
                "style_type": planning.get("style_type"),
                "interpretation": planning.get("interpretation"),
                "original_prompt": image_prompt,
                "resolution": "1024x1024",
                "status": "completed"
            }
        }

# --- 싱글톤 + 노드 래퍼 ---
# 모든 개발자가 workflow.py에서 이 노드 함수를 통해 시각화 기능을 호출함
visualization_agent = VisualizationAgent()

async def visualization_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Visualization Agent."""
    return await visualization_agent(state)
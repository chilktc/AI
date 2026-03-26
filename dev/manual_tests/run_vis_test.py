import asyncio
from src.agents.podcast.visualization import visualization_agent
from src.models.agent_state import AgentState

async def run_test():
    # 시각적 솔루션을 직접 주지 않고, 이성적 판단이 필요한 '상황'만 전달합니다.
    state = AgentState(
        user_id="dev2_tester",
        session_id="test_session_02",
        # [변경] mode를 'empathy'가 아닌 'conversation'으로 설정하여 이성적 접근을 유도합니다.
        mode="conversation", 
        emotion_vectors={"primary_emotion": "neutral", "intensity": 0.4},
        # [변경] 위로가 아닌 '구조화'와 '정리'가 필요한 이성적 테마를 전달합니다.
        content_analysis={"main_theme": "복잡한 프로젝트 우선순위에 대한 객관적인 구조화와 논리적 상황 정리"}
    )

    print("🎨 Visualization Agent 작동 시작...")
    result = await visualization_agent.process(state)
    
    vis = result["visual_data"]
    print(f"\n✅ 결과 확인")
    # 성공 시 style_type이 'hard_sharp'로 출력되어야 합니다.
    print(f"- 선택된 스타일: {vis['style_type']}") 
    print(f"- AI 해석: {vis['interpretation']}")
    print(f"- 이미지 URL: {vis['image_url']}")

if __name__ == "__main__":
    asyncio.run(run_test())
import asyncio
import os
import json
from src.agents.podcast.episode_memory import episode_memory_agent
from src.models.agent_state import AgentState

async def test_memory_full_cycle():
    print("🧪 [Memory Agent] 통합 기능 검증을 시작합니다...")

    # --- STEP 1: 새로운 기억 저장 테스트 ---
    test_text = "오늘은 KT Cloud와 로컬 DB를 연동하는 중요한 이정표를 세운 날이다."
    test_meta = {"category": "development", "milestone": "RAG_integration"}
    
    print("\n[1/2] 저장(Save) 테스트 중...")
    save_success = await episode_memory_agent._save_to_store(test_text, test_meta)
    
    if save_success:
        print("✅ 저장 성공: mock_db.json에 데이터가 기록되었습니다.")
    else:
        print("❌ 저장 실패: 로직을 확인해 주세요.")
        return

    # --- STEP 2: 저장된 데이터 인출 테스트 ---
    print("\n[2/2] 인출(Retrieve) 테스트 중...")
    state = AgentState(
        user_input="오늘 무슨 일이 있었지?",
        user_id="dev_user_2",
        mode="podcast"
    )
    
    # 에이전트 실행 (process 함수 호출)
    result = await episode_memory_agent(state)
    memory_data = result.get("memory_results", {})
    items = memory_data.get("items", [])

    print("\n" + "="*50)
    if any(test_text in item.get('text', '') for item in items):
        print("✅ 인출 성공: 방금 저장한 기억을 정상적으로 불러왔습니다.")
        print(f"📊 현재 DB 총 기억 수: {len(items)}건")
        
        # 마지막으로 저장된 데이터 출력
        last_item = items[-1]
        print(f"📝 최근 기억: {last_item.get('text')}")
        print(f"🔢 벡터 포함 여부: {'Yes' if last_item.get('vector') else 'No'}")
    else:
        print("❌ 인출 실패: 저장된 데이터를 찾을 수 없습니다.")
    print("="*50)

if __name__ == "__main__":
    try:
        asyncio.run(test_memory_full_cycle())
    except Exception as e:
        print(f"🚨 테스트 중 에러 발생: {e}")
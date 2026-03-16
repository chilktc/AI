import asyncio
import os
import sys

# 프로젝트 루트 경로 인식
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from src.agents.podcast.episode_memory import episode_memory_agent
from src.models.agent_state import AgentState

async def run_integration_test():
    print("🚀 [KT Cloud] 구조화된 데이터 정합성 검증 시작...")
    state = AgentState(user_input="프로젝트 기록 찾아줘", user_id="dev_user_2", mode="podcast")

    result = await episode_memory_agent(state)
    
    # BaseMemoryAgent의 응답 구조에 맞게 데이터를 가져옵니다.
    # result['memory_results']는 이제 {'items': [...], 'summary': ...} 형태입니다.
    memory_data = result.get("memory_results", {})
    memories = memory_data.get("items", []) # 'items' 키에서 실제 리스트 인출
    
    print("\n" + "="*50)
    if isinstance(memories, list) and len(memories) > 0:
        print(f"✅ 연동 및 데이터 구조 확인 성공! (총 {len(memories)}건)")
        for i, mem in enumerate(memories):
            print(f"[{i+1}] {mem.get('text')}")
    else:
        print("❌ 데이터를 찾지 못했습니다. 에이전트의 _retrieve_from_store 반환값을 확인하세요.")
        print(f"상세 내용: {memory_data}")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_integration_test())
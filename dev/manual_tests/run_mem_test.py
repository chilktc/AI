import asyncio
import json
import os
import sys

# 프로젝트 루트 경로 인식
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from src.agents.podcast.episode_memory import EpisodeMemoryAgent
from src.models.agent_state import AgentState

class MockEpisodeMemoryAgent(EpisodeMemoryAgent):
    async def process(self, state: AgentState) -> dict:
        mock_path = os.path.join(current_dir, "mock_memory.json")
        
        with open(mock_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_results = data.get("mock_results", [])
        
        formatted = [
            {
                "text": res.get("text"),
                "timestamp": res.get("metadata", {}).get("timestamp"),
                "emotion_tag": res.get("metadata", {}).get("emotion_tag"),
                "score": res.get("score")
            }
            for res in raw_results
        ]
        
        # ✅ AttributeError 방지: output_key가 없으면 _output_key를, 둘 다 없으면 기본값을 사용합니다.
        key = getattr(self, "output_key", getattr(self, "_output_key", "memory_results"))
        return {key: formatted}

async def run_test():
    print(f"🧠 {EpisodeMemoryAgent.__name__} 검증 시작...")
    agent = MockEpisodeMemoryAgent()
    state = AgentState(user_id="dev_user_2", emotion_vectors={"anxiety": 0.8}, mode="podcast")

    result = await agent.process(state)
    
    # ✅ 여기서도 안전하게 키를 가져옵니다.
    output_key = getattr(agent, "output_key", getattr(agent, "_output_key", "memory_results"))
    memories = result.get(output_key, [])
    
    print(f"\n📡 [{output_key}] 필드 데이터 인출 성공!")
    print("-" * 60)
    if not memories:
        print("💡 데이터가 없습니다. JSON 파일의 'mock_results' 키를 확인해 주세요.")
    else:
        for i, mem in enumerate(memories):
            print(f"[{i+1}] {mem['text']}")
    print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run_test())
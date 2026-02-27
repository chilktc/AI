from __future__ import annotations

from src.agents.shared.base_memory import BaseMemoryAgent
from src.models.agent_state import AgentState


class EpisodeMemoryAgent(BaseMemoryAgent):
    """
    ✅ 팟캐스트용 Episode Memory Agent (독립 호출, tier=None)

    [1차 제출 기본안]
    - 팟캐스트용 메모리를 "memory_results"로 출력합니다.
      (Reasoning/Personalizer가 그냥 memory_results만 읽어도 동작)

    - 과거 방송(에피소드) 히스토리/세그먼트/요약 등 "콘텐츠 메타데이터" 중심
    - 대화용 메모리(민감 정보)와 절대 섞이지 않도록 저장소(namespace/index)를 분리합니다.

    output_key:
      - memory_results            ✅ (팟캐스트 기본)
    namespace:
      - mem_podcast_episode       ✅
    """

    def __init__(self) -> None:
        super().__init__(
            name="episode_memory",
            output_key="memory_results",          # ✅ 팟캐스트를 기본 키로
            namespace="mem_podcast_episode",
            tier=None,
        )


episode_memory_agent = EpisodeMemoryAgent()


async def episode_memory_node(state: AgentState):
    return await episode_memory_agent(state)
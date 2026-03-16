from __future__ import annotations
import httpx
import json
import os
import datetime
from typing import Any
from src.agents.shared.base_memory import BaseMemoryAgent
from src.models.agent_state import AgentState

class EpisodeMemoryAgent(BaseMemoryAgent):
    """
    ✅ KT Cloud RAG Suite 연동 팟캐스트 메모리 에이전트
    - 인출(Retrieve): KT Cloud 임베딩 확인 후 mock_db.json에서 읽기
    - 저장(Save): KT Cloud 임베딩 후 mock_db.json에 쓰기
    """

    def __init__(self) -> None:
        super().__init__(
            name="episode_memory",
            output_key="memory_results",
            namespace="mem_podcast_episode",
            tier=None,
        )
        # KT Cloud 설정 (배포하신 엔드포인트와 토큰)
        self.endpoint = "https://no753ozr79oq.proxy.aifoundry.ktcloud.com/v1/embeddings"
        self.api_token = "kt_cctc5n6h10bzzwhdhrpsopw4tiwr0yvz59f270tuhy1tl54pwr18swmcvmzajsg8e"

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        BaseMemoryAgent의 흐름을 따르되, 
        우리가 정의한 인출(_retrieve_from_store) 로직을 사용하여 결과를 반환합니다.
        """
        query = state.get("memory_query")
        if not query:
            query = str(state.get("user_input", ""))

        # 1. 기억 인출 (Mock DB에서 가져오기)
        items = await self._retrieve_from_store(query)

        # 2. 결과 구조화 (스크립트 에이전트가 읽을 수 있는 규격)
        payload = {
            "items": items,
            "summary": f"'{query}'와 관련된 과거 기록을 {len(items)}건 찾았습니다.",
            "suggested_personalization": {"topic": "Restoration of Color"},
            "_meta": {
                "namespace": "mem_podcast_episode",
                "engine": "mock_db",
                "status": "success"
            }
        }

        return {"memory_results": payload}

    async def _retrieve_from_store(self, query: str) -> list[dict]:
        """
        [인출] KT Cloud와 통신 확인 후 로컬 mock_db.json에서 데이터를 읽어옵니다.
        """
        # KT Cloud 임베딩 확인 (연결성 테스트용)
        async with httpx.AsyncClient() as client:
            try:
                headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
                payload = {"model": "upstage/embedding-query", "input": query}
                await client.post(self.endpoint, headers=headers, json=payload, timeout=5.0)
            except:
                pass 

        # 로컬 파일에서 데이터 읽기
        db_path = os.path.join(os.getcwd(), "mock_db.json")
        if not os.path.exists(db_path):
            return []

        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _save_to_store(self, text: str, metadata: dict = None) -> bool:
        """
        [저장] 입력된 텍스트를 임베딩하여 mock_db.json에 추가합니다.
        """
        print(f"💾 [DEBUG] 새로운 기억 저장 시작: {text[:20]}...")

        # 1. KT Cloud 임베딩 API 호출 (저장용 벡터 생성)
        vector = []
        async with httpx.AsyncClient() as client:
            try:
                headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
                payload = {"model": "upstage/embedding-query", "input": text}
                response = await client.post(self.endpoint, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    vector = response.json()['data'][0]['embedding']
                    print(f"✅ 임베딩 성공 (차원: {len(vector)})")
            except Exception as e:
                print(f"⚠️ 임베딩 실패 (벡터 없이 저장): {e}")

        # 2. 로컬 mock_db.json 읽기 및 업데이트
        db_path = os.path.join(os.getcwd(), "mock_db.json")
        db_data = []
        
        if os.path.exists(db_path):
            with open(db_path, "r", encoding="utf-8") as f:
                db_data = json.load(f)

        # 3. 새로운 데이터 구조 생성
        new_entry = {
            "text": text,
            "vector": vector,
            "score": 1.0,
            "metadata": metadata or {
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "type": "user_log"
            }
        }
        
        db_data.append(new_entry)

        # 4. 파일 쓰기
        try:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db_data, f, ensure_ascii=False, indent=2)
            print(f"✅ mock_db.json 업데이트 완료! (현재 총 {len(db_data)}건)")
            return True
        except Exception as e:
            print(f"❌ 파일 쓰기 실패: {e}")
            return False

# 싱글톤 및 노드 래퍼
episode_memory_agent = EpisodeMemoryAgent()

async def episode_memory_node(state: AgentState):
    return await episode_memory_agent(state)
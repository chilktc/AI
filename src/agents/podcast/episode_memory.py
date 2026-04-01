from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

import httpx

from src.agents.shared.base_memory import BaseMemoryAgent
from src.models.agent_state import AgentState

# mock_db.json 경로 — 프로젝트 루트 기준 data/cache/ 하위
_MOCK_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "cache" / "mock_db.json"


class EpisodeMemoryAgent(BaseMemoryAgent):
    """
    KT Cloud RAG Suite 연동 팟캐스트 메모리 에이전트.

    - 인출(Retrieve): KT Cloud 임베딩 확인 후 mock_db.json에서 읽기
    - 저장(Save): KT Cloud 임베딩 후 mock_db.json에 추가
    """

    def __init__(self) -> None:
        super().__init__(
            name="episode_memory",
            output_key="memory_results",
            namespace="mem_podcast_episode",
            tier=None,
        )
        # KT Cloud 설정 — 환경변수에서 로드
        self.endpoint = os.getenv("KT_CLOUD_ENDPOINT", "")
        self.api_token = os.getenv("KT_CLOUD_API_TOKEN", "")
        if not self.endpoint or not self.api_token:
            self.logger.warning(
                "KT Cloud 자격증명 미설정 (KT_CLOUD_ENDPOINT, KT_CLOUD_API_TOKEN). "
                "임베딩 연결 테스트가 건너뛰어집니다."
            )

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
        """[인출] KT Cloud 연결 확인 후 로컬 mock_db.json에서 데이터를 읽는다."""
        # KT Cloud 임베딩 연결 확인 (자격증명이 설정된 경우에만)
        if self.endpoint and self.api_token:
            async with httpx.AsyncClient() as client:
                try:
                    headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
                    payload = {"model": "upstage/embedding-query", "input": query}
                    await client.post(self.endpoint, headers=headers, json=payload, timeout=5.0)
                except Exception as e:
                    self.logger.debug("KT Cloud 연결 확인 실패: %s", e)

        # 로컬 파일에서 데이터 읽기
        if not _MOCK_DB_PATH.exists():
            return []

        with open(_MOCK_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _save_to_store(self, text: str, metadata: dict = None) -> bool:
        """[저장] 텍스트를 임베딩하여 mock_db.json에 추가한다."""
        self.logger.debug("새로운 기억 저장 시작: %s...", text[:20])

        # 1. KT Cloud 임베딩 API 호출 (자격증명이 설정된 경우에만)
        vector: list = []
        if self.endpoint and self.api_token:
            async with httpx.AsyncClient() as client:
                try:
                    headers = {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"}
                    payload = {"model": "upstage/embedding-query", "input": text}
                    response = await client.post(self.endpoint, headers=headers, json=payload, timeout=10.0)

                    if response.status_code == 200:
                        vector = response.json()["data"][0]["embedding"]
                        self.logger.info("임베딩 성공 (차원: %d)", len(vector))
                except Exception as e:
                    self.logger.warning("임베딩 실패 (벡터 없이 저장): %s", e)

        # 2. 로컬 mock_db.json 읽기 및 업데이트
        db_data: list = []

        if _MOCK_DB_PATH.exists():
            with open(_MOCK_DB_PATH, "r", encoding="utf-8") as f:
                db_data = json.load(f)

        # 3. 새로운 데이터 구조 생성
        new_entry = {
            "text": text,
            "vector": vector,
            "score": 1.0,
            "metadata": metadata or {
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "type": "user_log",
            },
        }

        db_data.append(new_entry)

        # 4. 파일 쓰기
        try:
            _MOCK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_MOCK_DB_PATH, "w", encoding="utf-8") as f:
                json.dump(db_data, f, ensure_ascii=False, indent=2)
            self.logger.info("mock_db.json 업데이트 완료 (현재 총 %d건)", len(db_data))
            return True
        except Exception as e:
            self.logger.error("파일 쓰기 실패: %s", e)
            return False

async def episode_memory_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Episode Memory.

    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = EpisodeMemoryAgent()
    return await agent(state)
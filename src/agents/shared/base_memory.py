from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class BaseMemoryAgent(BaseAgent):
    """
    ✅ Shared Engine (공통 엔진) - v1.1.0
    자식 클래스에서 _retrieve_from_store와 _save_to_store만 구현하면
    KT Cloud RAG든 로컬 JSON이든 바로 연동됩니다.
    """

    def __init__(
        self,
        *,
        name: str,
        output_key: str,
        namespace: str,
        tier: int | None = None,
    ) -> None:
        super().__init__(name=name, tier=tier)
        self._output_key = output_key
        self._namespace = namespace

    async def process(self, state: AgentState) -> dict[str, Any]:
        """메모리 검색 및 결과 정리 공통 흐름"""
        _user_id = str(state.get("user_id", ""))  # noqa: F841
        mode = str(state.get("mode", "podcast"))
        scope = str(state.get("memory_scope", "all"))

        query = state.get("memory_query")
        if not query:
            query = str(state.get("user_input", ""))

        # ============================================================
        # 1. STORAGE LOOKUP (자식 클래스에서 오버라이딩한 로직 호출)
        # ============================================================
        # 우리가 만든 EpisodeMemoryAgent가 구현한 _retrieve_from_store를 호출합니다.
        items = await self._retrieve_from_store(str(query))

        # 만약 자식에서 데이터를 못 가져왔다면, 기존처럼 LLM에게 '추론'을 시켜 백업합니다.
        if not items:
            try:
                result = await self.call_llm_json(
                    system_prompt=self.get_prompt("system_prompt"),
                    user_message=(
                        f"[Memory Search Placeholder]\n"
                        f"- namespace: {self._namespace}\n"
                        f"- query: {query}\n"
                        "실제 DB 결과가 없어 LLM이 가상의 맥락을 제안합니다."
                    ),
                )
                items = result.get("items", [])
            except KeyError:
                items = []

        # ============================================================
        # 2. 결과 패키징 (Base 구조 유지)
        # ============================================================
        payload = {
            "items": items,
            "summary": f"'{query}'에 대한 {self._namespace} 도메인의 검색 결과입니다.",
            "suggested_personalization": {},  # 필요 시 자식에서 채움
            "_meta": {"namespace": self._namespace, "scope": scope, "mode": mode},
        }

        return {self._output_key: payload}

    # ----------------------------------------------------------------
    # 💡 개발자 2님이 앞으로 채우셔야 할 핵심 구멍(Interface)
    # ----------------------------------------------------------------

    async def _retrieve_from_store(self, query: str) -> list[dict]:
        """
        [인출] 실제 저장소(KT Cloud, Mock DB 등)에서 데이터를 가져오는 로직.
        자식 클래스에서 반드시 구현해야 합니다.
        """
        return []

    async def _save_to_store(self, text: str, metadata: dict) -> bool:
        """
        [저장] 오늘의 대화를 내일의 기억으로 저장하는 로직.
        사용자 로그가 끝나는 시점에 호출될 예정입니다.
        """
        # TODO: 여기에 KT Cloud Ingestion API나 파일 쓰기 로직을 넣으시면 됩니다.
        return True

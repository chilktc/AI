from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class BaseMemoryAgent(BaseAgent):
    """
    Shared Memory Engine (v1.2.0)
    - retrieve + save 트리거 포함
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
        query = state.get("memory_query") or str(state.get("user_input", ""))

        # ============================================================
        # 0. SAVE TRIGGER (신규)
        # ============================================================
        if state.get("memory_write"):
            text = state.get("memory_text", "")
            metadata = state.get("memory_metadata", {})

            if text:
                await self._save_to_store(text, metadata)

        # ============================================================
        # 1. RETRIEVE
        # ============================================================
        items = await self._retrieve_from_store(str(query))

        if not items:
            try:
                result = await self.call_llm_json(
                    system_prompt=self.get_prompt("system_prompt"),
                    user_message=(
                        f"[Memory Search Placeholder]\n"
                        f"- namespace: {self._namespace}\n"
                        f"- query: {query}"
                    ),
                )
                items = result.get("items", [])
            except KeyError:
                items = []

        # ============================================================
        # 2. PACKAGING
        # ============================================================
        payload = {
            "items": items,
            "summary": f"'{query}' 관련 기억 검색 결과",
            "suggested_personalization": {},
            "_meta": {"namespace": self._namespace},
        }

        return {self._output_key: payload}

    async def _retrieve_from_store(self, query: str) -> list[dict]:
        return []

    async def _save_to_store(self, text: str, metadata: dict) -> bool:
        return True

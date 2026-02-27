from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class BaseMemoryAgent(BaseAgent):
    """
    ✅ Shared Engine (공통 엔진)

    이 클래스는 "메모리 검색의 공통 흐름"만 담습니다.
    (쿼리 준비 → 저장소 조회 → 결과 정리 → AgentState에 dict 반환)

    ------------------------------------------------------
    Shared Engine, Distinct Agents (코드는 1개, 인스턴스는 2개)
    ------------------------------------------------------
    - 엔진(검색 흐름)은 하나로 유지
    - 배포(인스턴스)는 2개로 분리:
        A) EpisodeMemoryAgent (팟캐스트용) → memory_results
        B) MemoryAgent        (대화용)     → personal_memory_results

    -------------------------
    왜 이렇게 하냐? (쉽게)
    -------------------------
    1) 개인정보 안전(Privacy by Design)
       - 대화 메모리: 개인 고민/취약 정보(민감 데이터)
       - 팟캐스트 메모리: 과거 에피소드 요약/주제/세그먼트(콘텐츠 메타데이터)
       → 섞이면, "민감 상담 내용이 방송 스크립트에 섞여 나갈" 위험이 생깁니다.
       → 그래서 저장소(인덱스/namespace/table)를 구조적으로 분리합니다.

    2) 성능 목표가 다름
       - 대화: 빠른 응답(실시간성)
       - 팟캐스트: 더 깊은 검색(맥락/정확성)

    -------------------------
    DB/VectorDB 붙일 때는 어디를 바꾸나?
    -------------------------
    process() 안의 "TODO: STORAGE LOOKUP" 블록만 교체하면 됩니다.
    - Pinecone 검색 / SQL 조회 / MCP 호출로 대체
    - 반드시 self._namespace(또는 index명)를 분기해서 "저장소를 분리"하세요.
      이게 가장 중요한 안전장치입니다.
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
        self._namespace = namespace  # ✅ 데이터 도메인 분리 스위치(핵심)

    async def process(self, state: AgentState) -> dict[str, Any]:
        user_id = str(state.get("user_id", ""))
        mode = str(state.get("mode", "podcast"))
        scope = str(state.get("memory_scope", "all"))

        query = state.get("memory_query")
        if not query:
            query = str(state.get("user_input", ""))

        # ============================================================
        # TODO: STORAGE LOOKUP  (여기만 실제 DB/VectorDB/MCP로 교체)
        # ============================================================
        # ✅ 매우 중요:
        # - self._namespace를 사용하여 저장소를 분리합니다.
        #   예: mem_conversation / mem_podcast_episode
        #
        # 예시(개념):
        # if self._namespace == "mem_conversation":
        #     hits = pinecone.search(index="user_profile_index", namespace=user_id, query=query)
        # else:
        #     hits = pinecone.search(index="podcast_episode_index", namespace=user_id, query=query)
        #
        # 현재는 “로컬 검증(스모크 테스트)” 단계이므로,
        # placeholder로 LLM 기반 JSON을 사용합니다.
        try:
            result = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=(
                    f"[Memory Search]\n"
                    f"- user_id: {user_id}\n"
                    f"- mode: {mode}\n"
                    f"- namespace: {self._namespace}\n"
                    f"- scope: {scope}\n"
                    f"- query: {query}\n\n"
                    "반드시 JSON으로 반환:\n"
                    "{\n"
                    '  "items": list[{"title": str, "content": str, "type": str, "score": float}],\n'
                    '  "summary": str,\n'
                    '  "suggested_personalization": dict\n'
                    "}\n"
                ),
            )
        except KeyError:
            # 프롬프트가 없어도 파이프라인이 깨지지 않도록 빈 결과 반환
            result = {"items": [], "summary": "", "suggested_personalization": {}}

        # 타입 보정(merge 안정성)
        items = result.get("items", [])
        if not isinstance(items, list):
            items = []

        suggested = result.get("suggested_personalization", {})
        if not isinstance(suggested, dict):
            suggested = {}

        payload = {
            "items": items,
            "summary": str(result.get("summary", "")),
            "suggested_personalization": suggested,
            "_meta": {"namespace": self._namespace, "scope": scope, "mode": mode},
        }

        return {self._output_key: payload}
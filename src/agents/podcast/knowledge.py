"""
Knowledge Agent
전문 심리상담 지식 검색 (Expert RAG) 에이전트.
CBT, DBT 등 심리치료 기법, 정신건강 전문 지식을 검색하여 근거 기반 응답을 제공합니다.

독립 에이전트: Podcast Reasoning Agent가 필요 시 조건부 호출.
"""

import json
from datetime import datetime
from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class KnowledgeAgent(BaseAgent):
    """
    전문 지식 검색 에이전트 (Expert RAG)
    """

    def __init__(
        self,
        db_client: Any | None = None,
        pinecone_client: Any | None = None,
        embedding_client: Any | None = None,
    ):
        super().__init__(name="knowledge")

        self.db_client = db_client
        self.pinecone_client = pinecone_client
        self.embedding_client = embedding_client

    async def process(self, state: AgentState) -> dict:
        """
        LangGraph 노드 함수 (비동기)
        """
        start_time = datetime.now()

        # 실제 환경에서는 보통 독립적으로 query와 context를 받지만
        # LangGraph State에서는 최상위 필드로 오거나 파편화되어 있을 수 있습니다.
        query = state.get("user_input", "")
        domain_hints = state.get("domain_hints", [])
        user_context = state.get("user_context", {})

        self.logger.info("[KnowledgeAgent] Processing knowledge search for query: %s", query)

        try:
            # 1. 쿼리 확장 및 도메인 분류 (LLM 기반)
            expanded = await self._expand_query(query, domain_hints)

            # 2. 벡터 DB 검색 (전문 쿼리 기준)
            vector_results = await self._search_knowledge_base(
                query=expanded.get("professional_query", query),
                domains=expanded.get("selected_domains", []),
            )

            if not vector_results:
                self.logger.info("[KnowledgeAgent] No relevant knowledge found in Vector DB.")
                return {
                    "knowledge_results": {
                        "documents": [],
                        "synthesis": "No relevant knowledge found",
                    },
                    "recommended_approaches": [],
                }

            # 3. PostgreSQL(또는 지원 DB)에서 전체 메타데이터 및 문서 원문 조회
            doc_ids = [r.get("id") for r in vector_results if "id" in r]
            documents = await self._get_documents(doc_ids)

            # 4. 사용자 맥락 적합성 평가 (LLM 검증)
            applicability = await self._assess_applicability(documents, user_context)

            # 5. 지식 종합 및 권장사항 형태 텍스트 생성 (LLM)
            synthesis = await self._synthesize_knowledge(query, documents, applicability)

            # 6. 최종 결과 정리
            result = self._build_output(documents, vector_results, applicability, synthesis)

            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.info(
                f"[KnowledgeAgent] Completed in {processing_time:.2f}ms. Generated {len(result.get('recommended_approaches', []))} recommendations."
            )

            return result

        except Exception as e:
            self.logger.error("[KnowledgeAgent] Error during knowledge retrieval: %s", e)
            return {
                "knowledge_results": {"documents": [], "synthesis": f"Error occurred: {str(e)}"},
                "recommended_approaches": [],
            }

    async def _expand_query(self, query: str, domain_hints: list[str]) -> dict[str, Any]:
        """쿼리를 전문가 용어로 확장하고 탐색할 도메인 지정 (LLM)"""
        system_prompt = self.get_prompt("expand_query")

        user_prompt = self._prompt_loader.load_user_prompt(self._prompt_mode, "knowledge", "expand_query")
        user_message = user_prompt.format(
            query=query,
            domain_hints=json.dumps(domain_hints)
        )

        try:
            # LLMClient의 generate_json 사용
            response_json = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            return response_json
        except Exception as e:
            self.logger.warning("[KnowledgeAgent] Expand query failed, using fallback: %s", e)
            return {
                "professional_query": query,
                "selected_domains": domain_hints or ["general_psychology"],
                "search_keywords": [],
            }

    async def _search_knowledge_base(self, query: str, domains: list[str]) -> list[dict[str, Any]]:
        """Pinecone 등 벡터 데이터베이스에서 관련 문서를 검색합니다."""
        if not self.embedding_client or not self.pinecone_client:
            self.logger.warning("[KnowledgeAgent] Vector DB and Embedding client not provided.")
            return []

        try:
            # 외부 클라이언트를 통한 임베딩 및 검색 수행 (Mock 또는 실제 구현 호환)
            embedding = await self.embedding_client.get_embedding(query)

            results = await self.pinecone_client.query(
                index="expert_knowledge",
                vector=embedding,
                filter={"domain": {"$in": domains}},
                top_k=5,
                include_metadata=True,
            )
            return results.get("matches", [])
        except Exception as e:
            self.logger.error("[KnowledgeAgent] Vector search failed: %s", e)
            return []

    async def _get_documents(self, doc_ids: list[str]) -> list[dict[str, Any]]:
        """RDB에서 벡터 검색된 문서들의 원문/상세 메타데이터 조회"""
        if not self.db_client or not doc_ids:
            return []

        try:
            # 실제 DB가 연결된 경우 async sql 쿼리를 실행하는 부분
            query = "SELECT id, title, content, domain, source, evidence_level, contraindications FROM knowledge_base WHERE id = ANY($1)"
            docs = await self.db_client.fetch(query, doc_ids)
            return [dict(d) for d in docs]
        except Exception as e:
            self.logger.error("[KnowledgeAgent] DB document fetch failed: %s", e)
            # 임시로 더미 데이터 혹은 빈 리스트 반환
            return []

    async def _assess_applicability(
        self, documents: list[dict], user_context: dict
    ) -> dict[str, dict]:
        """사용자 맥락을 기반으로 각 문서 지식의 적합성을 평가합니다 (LLM)"""
        if not documents:
            return {}

        system_prompt = self.get_prompt("assess_applicability")

        docs_text = "\n\n".join(
            [
                f"{i+1}. Title: {d.get('title')}\n   Content: {str(d.get('content'))[:300]}...\n   Contraindications: {d.get('contraindications', 'None')}"
                for i, d in enumerate(documents)
            ]
        )

        user_prompt = self._prompt_loader.load_user_prompt(self._prompt_mode, "knowledge", "assess_applicability")
        user_message = user_prompt.format(
            age_group=user_context.get('age_group', 'unknown'),
            culture=user_context.get('cultural_background', 'unknown'),
            previous_approaches=user_context.get('previous_approaches', []),
            docs_text=docs_text
        )

        try:
            scores_list = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            # 리스트를 딕셔너리로 맵핑
            result = {}
            for s in scores_list:
                doc_id = str(s.get("doc_id", ""))
                result[doc_id] = {
                    "score": s.get("applicability_score", 0.5),
                    "notes": s.get("notes", ""),
                }
            return result
        except Exception as e:
            self.logger.warning("[KnowledgeAgent] Applicability assessment failed: %s", e)
            return {
                str(i + 1): {"score": 0.5, "notes": "assessment failed"}
                for i in range(len(documents))
            }

    async def _synthesize_knowledge(
        self, query: str, documents: list[dict], applicability: dict
    ) -> dict[str, Any]:
        """조회된 문서들과 사용성 평가 결과를 바탕으로 최종 권장사항을 종합 생성합니다 (LLM)"""
        if not documents:
            return {
                "synthesis": "No evidence.",
                "recommended_approaches": [],
                "evidence_level": "low",
            }

        system_prompt = self.get_prompt("synthesize_knowledge")

        docs_text = "\n\n".join(
            [
                f"{i+1}. {d.get('title')} (Applicability: {applicability.get(str(i+1), {}).get('score', 0.5)})\n"
                f"   {str(d.get('content'))[:500]}...\n   Source: {d.get('source')}"
                for i, d in enumerate(documents)
            ]
        )

        user_prompt = self._prompt_loader.load_user_prompt(self._prompt_mode, "knowledge", "synthesize_knowledge")
        user_message = user_prompt.format(
            query=query,
            docs_text=docs_text
        )

        try:
            result = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            return result
        except Exception as e:
            self.logger.warning("[KnowledgeAgent] Knowledge synthesis failed: %s", e)
            return {
                "synthesis": "Synthesis failed.",
                "recommended_approaches": [],
                "evidence_level": "low",
            }

    def _build_output(
        self,
        documents: list[dict],
        vector_results: list[dict],
        applicability: dict,
        synthesis: dict,
    ) -> dict[str, Any]:
        """최종 Dictionary Output 구조화"""
        enriched_docs = []
        for i, doc in enumerate(documents):
            # 벡터 결과와 DB 문서 간 순서/길이가 호환된다고 가정 (안전성을 위해 get 사용)
            v_score = vector_results[i].get("score", 0.0) if i < len(vector_results) else 0.0
            app_data = applicability.get(str(i + 1), {"score": 0.5, "notes": ""})

            enriched_docs.append(
                {
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "content": str(doc.get("content"))[:200] + "...",  # 일부만 포함
                    "source": doc.get("source"),
                    "relevance_score": v_score,
                    "applicability_score": app_data.get("score"),
                    "applicability_notes": app_data.get("notes"),
                }
            )

        return {
            "knowledge_results": {
                "documents": enriched_docs,
                "synthesis": synthesis.get("synthesis", ""),
            },
            "recommended_approaches": synthesis.get("recommended_approaches", []),
        }


async def create_knowledge_node(
    db_client: Any | None = None,
    pinecone_client: Any | None = None,
    embedding_client: Any | None = None,
):
    """LangGraph 노드 생성 팩토리"""
    agent = KnowledgeAgent(
        db_client=db_client, pinecone_client=pinecone_client, embedding_client=embedding_client
    )

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

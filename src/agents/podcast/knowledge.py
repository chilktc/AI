"""
Knowledge Agent
전문 심리상담 지식 검색 (Expert RAG) 에이전트.
CBT, DBT 등 심리치료 기법, 정신건강 전문 지식을 검색하여 근거 기반 응답을 제공합니다.

독립 에이전트: Podcast Reasoning Agent가 필요 시 조건부 호출.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any, cast

import httpx

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

        # KT Cloud RAG Suite 설정 (search() 메서드에서 사용)
        # Parser: 쿼리 전처리/정제
        self.parser_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_PARSER_ENDPOINT", "")
        self.parser_token = os.getenv("KT_CLOUD_KNOWLEDGE_PARSER_TOKEN", "")
        # Embedding (Query): 벡터 분산 변환
        self.kt_embedding_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_ENDPOINT", "")
        self.kt_embedding_token = os.getenv("KT_CLOUD_KNOWLEDGE_EMBEDDING_QUERY_TOKEN", "")
        # TextGen (Qwen3): 검색 결과 요약/합성
        self.kt_textgen_endpoint = os.getenv("KT_CLOUD_KNOWLEDGE_TEXTGEN_ENDPOINT", "")
        self.kt_textgen_token = os.getenv("KT_CLOUD_KNOWLEDGE_TEXTGEN_TOKEN", "")
        # Pinecone: 벡터 DB
        self.kt_pinecone_api_key = os.getenv("PINECONE_API_KEY", "")
        self.kt_pinecone_index = os.getenv("PINECONE_INDEX_KNOWLEDGE", "expert-knowledge")
        self.kt_pinecone_host = ""

    async def process(self, state: AgentState) -> dict:
        """
        LangGraph 노드 함수 (비동기)
        """
        start_time = datetime.now()

        # 실제 환경에서는 보통 독립적으로 query와 context를 받지만
        # LangGraph State에서는 최상위 필드로 오거나 파편화되어 있을 수 있습니다.
        query = state.get("user_input", "")
        domain_hints = cast(list[str], state.get("domain_hints", []))
        user_context = cast(dict[str, Any], state.get("user_context", {}))

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
            doc_ids: list[str] = [str(r.get("id")) for r in vector_results if "id" in r]
            documents = await self._get_documents(doc_ids)

            # 4. 사용자 맥락 적합성 평가 (LLM 검증)
            applicability = await self._assess_applicability(documents, user_context)

            # 5. 지식 종합 및 권장사항 형태 텍스트 생성 (LLM)
            synthesis = await self._synthesize_knowledge(query, documents, applicability)

            # 6. 최종 결과 정리
            result = self._build_output(documents, vector_results, applicability, synthesis)

            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.logger.info(
                "[KnowledgeAgent] Completed in %.2fms. " "Generated %d recommendations.",
                processing_time,
                len(result.get("recommended_approaches", [])),
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

        user_prompt = self._prompt_loader.load_user_prompt(
            self._prompt_mode, "knowledge", "expand_query"
        )
        user_message = user_prompt.format(query=query, domain_hints=json.dumps(domain_hints))

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
                index="expert-knowledge",
                vector=embedding,
                filter={"domain": {"$in": domains}},
                top_k=5,
                include_metadata=True,
            )
            matches: list[dict[str, Any]] = results.get("matches", [])
            return matches
        except Exception as e:
            self.logger.error("[KnowledgeAgent] Vector search failed: %s", e)
            return []

    async def _get_documents(self, doc_ids: list[str]) -> list[dict[str, Any]]:
        """RDB에서 벡터 검색된 문서들의 원문/상세 메타데이터 조회"""
        if not self.db_client or not doc_ids:
            return []

        try:
            # 실제 DB가 연결된 경우 async sql 쿼리를 실행하는 부분
            query = (
                "SELECT id, title, content, domain, source,"
                " evidence_level, contraindications"
                " FROM knowledge_base WHERE id = ANY($1)"
            )
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
                f"{i+1}. Title: {d.get('title')}\n"
                f"   Content: {str(d.get('content'))[:300]}...\n"
                f"   Contraindications: "
                f"{d.get('contraindications', 'None')}"
                for i, d in enumerate(documents)
            ]
        )

        user_prompt = self._prompt_loader.load_user_prompt(
            self._prompt_mode, "knowledge", "assess_applicability"
        )
        user_message = user_prompt.format(
            age_group=user_context.get("age_group", "unknown"),
            culture=user_context.get("cultural_background", "unknown"),
            previous_approaches=user_context.get("previous_approaches", []),
            docs_text=docs_text,
        )

        try:
            scores_response = await self.call_llm_json(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            # LLM 응답에서 scores 리스트 추출
            scores_list: list[dict[str, Any]] = cast(
                list[dict[str, Any]],
                scores_response.get("scores", scores_response.get("results", [])),
            )
            # 리스트를 딕셔너리로 맵핑
            result: dict[str, dict[str, Any]] = {}
            for s in scores_list:
                if not isinstance(s, dict):
                    continue
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
                f"{i+1}. {d.get('title')} "
                f"(Applicability: "
                f"{applicability.get(str(i+1), {}).get('score', 0.5)}"
                f")\n"
                f"   {str(d.get('content'))[:500]}...\n"
                f"   Source: {d.get('source')}"
                for i, d in enumerate(documents)
            ]
        )

        user_prompt = self._prompt_loader.load_user_prompt(
            self._prompt_mode, "knowledge", "synthesize_knowledge"
        )
        user_message = user_prompt.format(query=query, docs_text=docs_text)

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

    # ============================================================
    # KT Cloud RAG Suite — search() 인터페이스 (신규)
    # PodcastReasoningAgent DI 호출용. KnowledgeAgentStub과 동일한 시그니처.
    # 기존 process() Legacy 로직과 완전 독립.
    #
    # 파이프라인: Parser → Embedding → Pinecone → TextGen
    # ============================================================
    async def search(
        self,
        query: str,
        domain: str = "mental_health",
    ) -> dict:
        """
        KT Cloud RAG Suite + Pinecone을 통한 전문 지식 검색.

        파이프라인:
            1. Parser API  → 쿼리를 전문 심리 용어로 전처리/정제
            2. Embedding API → 전처리된 쿼리를 벡터로 변환
            3. Pinecone      → expert-knowledge 인덱스에서 유사 문서 검색
            4. TextGen API   → 검색된 문서들을 바탕으로 요약문 생성

        Args:
            query: 검색 쿼리 (사용자 입력)
            domain: 지식 도메인 (기본: mental_health)

        Returns:
            {"articles": [...], "guidelines": []} 구조의 검색 결과
        """
        if not self.kt_embedding_endpoint or not self.kt_embedding_token:
            self.logger.warning(
                "[KnowledgeAgent] KT RAG Suite 미설정 — 빈 결과 반환"
            )
            return {"articles": [], "guidelines": []}

        try:
            # 1. Parser: 쿼리 전처리 (선택적 — 미설정 시 원본 쿼리 사용)
            parsed_query = await self._parse_query(query)

            # 2. Embedding: 벡터 변환
            vector = await self._embed_query(parsed_query)
            if not vector:
                self.logger.warning("[KnowledgeAgent] 임베딩 실패 — 빈 결과 반환")
                return {"articles": [], "guidelines": []}

            # 3. Pinecone: 벡터 검색
            matches = await self._query_pinecone(vector, domain)
            if not matches:
                self.logger.info("[KnowledgeAgent] Pinecone 검색 결과 없음")
                return {"articles": [], "guidelines": []}

            # 3-1. Backend RDB: Pinecone top_k chunk_id로 원문 조회
            chunk_ids = [m.get("id") for m in matches if m.get("id")]
            score_map = {m.get("id"): m.get("score", 0.0) for m in matches if m.get("id")}
            documents = await self._fetch_documents_from_backend(chunk_ids)

            # 4. 결과를 articles 구조로 매핑 (Pinecone metadata 대신 RDB 원문 사용)
            articles = [
                {
                    "id": doc.get("id", ""),
                    "title": doc.get("title", ""),
                    "content": doc.get("content", ""),
                    "score": score_map.get(doc.get("id"), 0.0),
                    "domain": doc.get("domain", domain),
                    "source": doc.get("source", ""),
                    "page": doc.get("page"),
                }
                for doc in documents
            ]

            # 5. TextGen: 검색 결과 요약 (선택적 — 미설정 시 스킵)
            summary = await self._generate_synthesis(query, articles)
            if summary:
                articles.insert(0, {
                    "id": "_synthesis",
                    "title": "검색 결과 종합",
                    "content": summary,
                    "score": 1.0,
                    "domain": domain,
                    "source": "KT RAG Suite TextGen",
                    "evidence_level": "synthesis",
                })

            self.logger.info(
                "[KnowledgeAgent] KT RAG Suite search 완료 — %d건 반환",
                len(articles),
            )
            return {"articles": articles, "guidelines": []}

        except Exception as e:
            self.logger.error(
                "[KnowledgeAgent] KT RAG Suite search 실패: %s", e
            )
            return {"articles": [], "guidelines": []}

    # ============================================================
    # search() 내부 헬퍼 — KT Cloud API + Pinecone
    # EpisodeMemoryAgent의 패턴을 재사용.
    # ============================================================

    async def _parse_query(self, query: str) -> str:
        """Parser API로 쿼리를 전문 심리 용어로 전처리한다.

        Parser가 미설정이면 원본 쿼리를 그대로 반환한다 (graceful degradation).
        """
        if not self.parser_endpoint or not self.parser_token:
            return query

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    self.parser_endpoint,
                    headers={"Authorization": f"Bearer {self.parser_token}"},
                    json={"text": query},
                    timeout=10.0,
                )
                r.raise_for_status()
                parsed = r.json().get("parsed_text", query)
                self.logger.info("[KnowledgeAgent] Parser 완료: '%s' → '%s'", query[:50], parsed[:50])
                return str(parsed)
        except Exception as e:
            self.logger.warning("[KnowledgeAgent] Parser 실패 — 원본 쿼리 사용: %s", e)
            return query

    async def _embed_query(self, text: str) -> list[float]:
        """KT Cloud Embedding API로 텍스트를 벡터로 변환한다.

        EpisodeMemoryAgent._embed()와 동일한 패턴.
        """
        if not self.kt_embedding_endpoint or not self.kt_embedding_token:
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    self.kt_embedding_endpoint,
                    headers={"Authorization": f"Bearer {self.kt_embedding_token}"},
                    json={"model": "embedding-query", "input": text},
                    timeout=10.0,
                )
                r.raise_for_status()
                data = r.json().get("data", [])
                if not data:
                    return []
                return data[0].get("embedding", [])  # type: ignore[no-any-return]
        except Exception as e:
            self.logger.error("[KnowledgeAgent] Embedding 실패: %s", e)
            return []

    async def _get_pinecone_host(self) -> str:
        """Pinecone 인덱스 호스트를 조회하고 캐싱한다.

        EpisodeMemoryAgent._get_host()와 동일한 패턴.
        """
        if self.kt_pinecone_host:
            return self.kt_pinecone_host

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://api.pinecone.io/indexes/{self.kt_pinecone_index}",
                    headers={"Api-Key": self.kt_pinecone_api_key},
                    timeout=10.0,
                )
                r.raise_for_status()
                self.kt_pinecone_host = r.json()["host"]
                return self.kt_pinecone_host
        except Exception as e:
            self.logger.error("[KnowledgeAgent] Pinecone host 조회 실패: %s", e)
            return ""

    async def _query_pinecone(
        self, vector: list[float], domain: str, top_k: int = 5
    ) -> list[dict]:
        """Pinecone에서 벡터 유사도 검색을 수행한다.

        EpisodeMemoryAgent._query()와 동일한 패턴.
        domain 필터를 metadata filter로 적용한다.
        """
        host = await self._get_pinecone_host()
        if not host:
            return []

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://{host}/query",
                    headers={"Api-Key": self.kt_pinecone_api_key},
                    json={
                        "vector": vector,
                        "topK": top_k,
                        "includeMetadata": True,
                        "filter": {"domain": {"$eq": domain}},
                    },
                    timeout=10.0,
                )
                r.raise_for_status()
                matches = r.json().get("matches", [])
                
                # 유사도 0.7 이상의 결과만 필터링하여 반환
                return [m for m in matches if m.get("score", 0.0) >= 0.7]
        except Exception as e:
            self.logger.error("[KnowledgeAgent] Pinecone query 실패: %s", e)
            return []

    async def _generate_synthesis(self, query: str, articles: list[dict]) -> str:
        """TextGen API로 검색 결과를 요약/합성한다.

        EpisodeMemoryAgent._generate_summary()와 동일한 패턴.
        TextGen이 미설정이면 빈 문자열을 반환한다 (스킵).
        """
        if not self.kt_textgen_endpoint or not self.kt_textgen_token:
            return ""
        if not articles:
            return ""

        context = "\n".join(
            f"- [{a.get('title', '제목 없음')}] {a.get('content', '')[:200]}"
            for a in articles
        )
        prompt = (
            f"다음은 '{query}'에 관련된 전문 심리 지식 검색 결과입니다.\n\n"
            f"{context}\n\n"
            f"위 내용을 종합하여 핵심 요약을 작성하세요."
        )

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    self.kt_textgen_endpoint,
                    headers={"Authorization": f"Bearer {self.kt_textgen_token}"},
                    json={
                        "model": "Qwen/Qwen3-32B",
                        "chat_template_kwargs": {"enable_thinking": False},
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
                return str(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            self.logger.warning("[KnowledgeAgent] TextGen 요약 실패: %s", e)
            return ""

    async def _fetch_documents_from_backend(self, chunk_ids: list[str]) -> list[dict]:
        """Backend RDB에서 Pinecone top_k 청크 원문을 조회한다.

        GET /api/internal/knowledge?ids=id1,id2,...
        실패 시 빈 리스트 반환 (graceful degradation).
        """
        if not chunk_ids:
            return []

        backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8080/api")
        url = f"{backend_url}/internal/knowledge"

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    url,
                    params={"ids": ",".join(chunk_ids)},
                    timeout=10.0,
                )
                r.raise_for_status()
                data = r.json()
                documents = data.get("data", [])
                self.logger.info(
                    "[KnowledgeAgent] RDB 원문 조회 완료 — %d건",
                    len(documents),
                )
                return documents
        except Exception as e:
            self.logger.error("[KnowledgeAgent] RDB 원문 조회 실패: %s", e)
            return []


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
) -> Callable[[AgentState], Coroutine[Any, Any, dict[str, Any]]]:
    """LangGraph 노드 생성 팩토리"""
    agent = KnowledgeAgent(
        db_client=db_client, pinecone_client=pinecone_client, embedding_client=embedding_client
    )

    async def _node(state: AgentState) -> dict:
        return await agent.process(state)

    return _node

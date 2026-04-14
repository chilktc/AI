"""
Podcast Reasoning — 팟캐스트 에피소드 추론 에이전트.

TIER 1에서 Safety, Emotion, Content Analyzer와 병렬 실행된다.
복잡도 기반 3단계 추론 파이프라인(GoT → ToT → CoT)으로
에피소드 구조를 설계하고 내러티브 흐름을 추론한다.

Episode Memory(개발자2)와 Knowledge Agent(개발자1)를
의존성 주입으로 조건부 호출한다.
통합 전까지는 stub 인터페이스를 사용한다.

담당: 개발자3
출력 필드: reasoning_result (+조건부: memory_results, knowledge_results)
모델: Sonnet 4

추론 깊이 라우팅:
    complexity ≥ 0.8  → "full"     → GoT → ToT → CoT (LLM 3회)
    0.5 ≤ complexity  → "standard" → ToT → CoT (LLM 2회)
    complexity < 0.5  → "minimal"  → CoT만 (LLM 1회)
"""

from __future__ import annotations

from typing import Any, Literal, cast

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.stubs import KnowledgeAgentStub
from src.models.agent_state import AgentState

# DI fallback — 실제 에이전트 (lazy import로 순환 참조 방지)
_EpisodeMemoryAgent: type | None = None


def _get_episode_memory_agent_class() -> type:
    """EpisodeMemoryAgent를 lazy import한다."""
    global _EpisodeMemoryAgent  # noqa: PLW0603
    if _EpisodeMemoryAgent is None:
        from src.agents.podcast.episode_memory import EpisodeMemoryAgent

        _EpisodeMemoryAgent = EpisodeMemoryAgent
    return _EpisodeMemoryAgent


# 추론 깊이 타입 — complexity_score에 따라 결정
ReasoningDepth = Literal["full", "standard", "minimal"]

# GoT/ToT/CoT 시스템 프롬프트는 prompts/podcast/podcast_reasoning.yaml에서 로드한다.
# BaseAgent의 get_prompt("got"), get_prompt("tot"), get_prompt("cot")로 접근.


class PodcastReasoningAgent(BaseAgent):
    """
    팟캐스트 에피소드 추론 에이전트.

    복잡도 기반 3단계 추론 파이프라인(GoT → ToT → CoT)으로
    에피소드 구조를 설계하고 내러티브 흐름을 추론한다.
    Episode Memory와 Knowledge Agent를 조건부로 호출하여
    개인화된 에피소드 경험과 전문 지식을 통합한다.

    Args:
        episode_memory: Episode Memory 에이전트 (DI — 없으면 EpisodeMemoryAgent 사용)
        knowledge_agent: Knowledge Agent (DI — 없으면 stub 사용)
    """

    def __init__(
        self,
        episode_memory: Any | None = None,
        knowledge_agent: Any | None = None,
    ) -> None:
        super().__init__(name="podcast_reasoning", tier=1)
        # 의존성 주입 — DI 미전달 시 실제 에이전트로 fallback
        self.episode_memory = episode_memory or _get_episode_memory_agent_class()()
        self.knowledge_agent = knowledge_agent or KnowledgeAgentStub()
        self._load_config()

    async def process(self, state: AgentState) -> dict[str, Any]:
        """
        에피소드 구조를 설계하고 내러티브 흐름을 추론한다.

        입력 (TIER 0 결과만 참조 — 같은 TIER 1 에이전트 결과는 참조 불가):
            - user_input: 사용자 원본 입력
            - intent: Intent Classifier 결과 (TIER 0 — 선택적)
            - execution_plan: Intent Classifier가 결정한 실행 계획 (TIER 0 — 선택적)

        출력:
            - reasoning_result: 에피소드 구조, 내러티브 흐름, 추론 결과
            - memory_results: 에피소드 기억 검색 결과 (조건부)
            - knowledge_results: 전문 지식 검색 결과 (조건부)

        참고:
            content_analysis(Content Analyzer)와 emotion_vectors(Emotion Agent)는
            같은 TIER 1에서 병렬 실행되므로 이 에이전트에서 참조하지 않는다.
            Podcast Reasoning은 user_input과 intent만으로 독립적으로 추론한다.
        """
        user_input = state.get("user_input", "")
        if not user_input:
            self.logger.error("[PodcastReasoning] user_input 없음")
            return {
                "reasoning_result": {
                    "episode_structure": [],
                    "key_themes": [],
                    "emotional_arc": {},
                    "confidence": 0.0,
                    "reasoning_depth": "minimal",
                    "error": "user_input_missing",
                }
            }
        user_id = state.get("user_id", "")
        intent = state.get("intent", {})
        execution_plan = state.get("execution_plan", {})

        # 복잡도 점수 — Intent Classifier(TIER 0)가 설정한 값 또는 기본값
        complexity = intent.get("complexity_score", 0.5)

        # 1단계: 추론 깊이 결정 (복잡도 기반)
        depth = self._determine_reasoning_depth(complexity)
        self.logger.info("추론 깊이 결정: %s (complexity=%.2f)", depth, complexity)

        # 2단계: 조건부 독립 에이전트 호출 (DI — TIER와 무관한 독립 호출)
        memory_result = await self._fetch_memory_if_needed(
            user_input, user_id, execution_plan, complexity
        )
        knowledge_result = await self._fetch_knowledge_if_needed(
            user_input, execution_plan, complexity
        )

        # 3단계: 추론 파이프라인 실행 (depth에 따라 GoT/ToT/CoT 조합)
        reasoning = await self._execute_reasoning_pipeline(
            depth=depth,
            user_input=user_input,
            intent=intent,
            memory_result=memory_result,
            knowledge_result=knowledge_result,
        )

        # 4단계: GoT 결과 저장 (Neo4j + Backend 전송)
        got_result = reasoning.get("got_result")
        if got_result:
            session_id = state.get("session_id", "")
            episode_id = f"ep_{session_id}" if session_id else ""
            await self._save_graph_data(got_result, session_id, episode_id, state)

        # 5단계: 결과 조립
        result: dict[str, Any] = {
            "reasoning_result": reasoning,
        }

        # 조건부 결과 포함 (독립 에이전트 호출 성공 시에만 AgentState에 기록)
        # - memory_results: Episode Memory 호출 결과 (complexity >= 0.6 또는 execution_plan 요청 시)
        # - knowledge_results: Knowledge Agent 호출 결과
        #   (complexity >= 0.5 또는 execution_plan 요청 시)
        if memory_result:
            result["memory_results"] = memory_result
        if knowledge_result:
            result["knowledge_results"] = knowledge_result

        return result

    # === 설정 로드 ===

    def _load_config(self) -> None:
        """settings.yaml에서 추론 깊이 임계값을 로드한다. 실패 시 기본값 사용."""
        cfg = self._load_agent_config(
            {
                "full_threshold": 0.8,
                "standard_threshold": 0.5,
            }
        )
        self.full_threshold: float = cfg["full_threshold"]
        self.standard_threshold: float = cfg["standard_threshold"]

    # === 추론 깊이 결정 ===

    def _determine_reasoning_depth(self, complexity: float) -> ReasoningDepth:
        """
        복잡도 점수로 추론 깊이를 결정한다.

        Args:
            complexity: Intent Classifier가 설정한 복잡도 (0.0-1.0)

        Returns:
            "full" (GoT+ToT+CoT), "standard" (ToT+CoT), "minimal" (CoT만)
        """
        if complexity >= self.full_threshold:
            return "full"
        elif complexity >= self.standard_threshold:
            return "standard"
        else:
            return "minimal"

    # === 추론 파이프라인 오케스트레이션 ===

    async def _execute_reasoning_pipeline(
        self,
        depth: ReasoningDepth,
        user_input: str,
        intent: dict[str, Any],
        memory_result: dict[str, Any] | None,
        knowledge_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        추론 깊이에 따라 GoT/ToT/CoT를 순차 실행하고 최종 결과를 조립한다.

        full:     GoT → ToT → CoT (LLM 3회)
        standard: ToT → CoT (LLM 2회)
        minimal:  CoT만 (LLM 1회)
        """
        got_result: dict[str, Any] | None = None
        tot_result: dict[str, Any] | None = None

        # GoT: depth="full"일 때만 실행
        if depth == "full":
            got_result = await self._graph_of_thoughts(
                user_input, intent, memory_result, knowledge_result
            )
            self.logger.info(
                "GoT 완료 — 노드 %d개, 엣지 %d개",
                len(got_result.get("nodes", [])),
                len(got_result.get("edges", [])),
            )

        # ToT: depth="full" 또는 "standard"일 때 실행
        if depth in ("full", "standard"):
            tot_result = await self._tree_of_thoughts(
                user_input, intent, got_result, memory_result, knowledge_result
            )
            selected_id = tot_result.get("selected", "?")
            self.logger.info(
                "ToT 완료 — 대안 %d개, 선택 #%s",
                len(tot_result.get("alternatives", [])),
                selected_id,
            )

        # CoT: 항상 실행
        cot_result = await self._chain_of_thoughts(
            user_input, intent, got_result, tot_result, memory_result, knowledge_result
        )
        self.logger.info("CoT 완료 — confidence=%.2f", cot_result.get("confidence", 0))

        # 최종 결과 조립 — 기존 필드(하위 호환) + 신규 메타데이터/phase 결과
        reasoning: dict[str, Any] = {
            # 추론 메타데이터 (신규)
            "reasoning_depth": depth,
            "reasoning_strategy": self._depth_to_strategy_label(depth),
        }

        # GoT 결과 포함 (depth=full일 때)
        if got_result is not None:
            reasoning["got_result"] = got_result

        # ToT 결과 포함 (depth≥standard일 때)
        if tot_result is not None:
            reasoning["tot_result"] = tot_result

        # CoT 결과 — 기존 최상위 필드로 유지 (하위 호환)
        reasoning["episode_structure"] = cot_result.get("episode_structure", [])
        reasoning["narrative_flow"] = cot_result.get("narrative_flow", "")
        reasoning["key_points"] = cot_result.get("key_points", [])
        reasoning["emotional_journey"] = cot_result.get("emotional_journey", [])
        reasoning["confidence"] = cot_result.get("confidence", 0.0)

        return reasoning

    @staticmethod
    def _depth_to_strategy_label(depth: ReasoningDepth) -> str:
        """추론 깊이를 전략 라벨 문자열로 변환한다."""
        labels: dict[str, str] = {
            "full": "GoT+ToT+CoT",
            "standard": "ToT+CoT",
            "minimal": "CoT",
        }
        return labels[depth]

    # === GoT (Graph of Thoughts) ===

    async def _graph_of_thoughts(
        self,
        user_input: str,
        intent: dict[str, Any],
        memory_result: dict[str, Any] | None,
        knowledge_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        사용자 입력에서 주제/개념/감정/경험 간 관계를 그래프로 구축한다.

        Neo4j 호환 JSON 구조로 노드와 엣지를 생성한다.
        현재는 JSON dict로만 저장하며, 향후 Neo4j 통합 시 그대로 사용 가능.
        """
        context = self._build_phase_context(
            phase="GoT",
            user_input=user_input,
            intent=intent,
            memory_result=memory_result,
            knowledge_result=knowledge_result,
        )
        try:
            return await self.call_llm_json(
                system_prompt=self.get_prompt("got"),
                user_message=context,
            )
        except Exception as e:
            self.logger.warning("[PodcastReasoning] GoT LLM 실패: %s", e)
            return {}

    # === ToT (Tree of Thoughts) ===

    async def _tree_of_thoughts(
        self,
        user_input: str,
        intent: dict[str, Any],
        got_result: dict[str, Any] | None,
        memory_result: dict[str, Any] | None,
        knowledge_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        에피소드 구조 대안을 3-5개 생성하고 최적안을 선택한다.

        GoT 그래프가 있으면 이를 참조하여 구조를 설계한다.
        """
        context = self._build_phase_context(
            phase="ToT",
            user_input=user_input,
            intent=intent,
            got_result=got_result,
            memory_result=memory_result,
            knowledge_result=knowledge_result,
        )
        try:
            return await self.call_llm_json(
                system_prompt=self.get_prompt("tot"),
                user_message=context,
            )
        except Exception as e:
            self.logger.warning("[PodcastReasoning] ToT LLM 실패: %s", e)
            return {}

    # === CoT (Chain of Thoughts) ===

    async def _chain_of_thoughts(
        self,
        user_input: str,
        intent: dict[str, Any],
        got_result: dict[str, Any] | None,
        tot_result: dict[str, Any] | None,
        memory_result: dict[str, Any] | None,
        knowledge_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        선택된 구조를 단계적으로 상세화하여 최종 에피소드 구조를 생성한다.

        GoT 그래프와 ToT 선택 결과가 있으면 이를 기반으로 상세화한다.
        """
        context = self._build_phase_context(
            phase="CoT",
            user_input=user_input,
            intent=intent,
            got_result=got_result,
            tot_result=tot_result,
            memory_result=memory_result,
            knowledge_result=knowledge_result,
        )
        try:
            return await self.call_llm_json(
                system_prompt=self.get_prompt("cot"),
                user_message=context,
            )
        except Exception as e:
            self.logger.warning("[PodcastReasoning] CoT LLM 실패: %s", e)
            return {}

    # === 컨텍스트 조합 헬퍼 ===

    def _build_phase_context(
        self,
        phase: str,
        user_input: str,
        intent: dict[str, Any],
        got_result: dict[str, Any] | None = None,
        tot_result: dict[str, Any] | None = None,
        memory_result: dict[str, Any] | None = None,
        knowledge_result: dict[str, Any] | None = None,
    ) -> str:
        """
        각 추론 phase(GoT/ToT/CoT)에 전달할 user_message를 조합한다.

        이전 phase 결과를 누적하여 다음 phase에 전달하는 구조.

        토큰 최적화:
            - GoT(첫 단계): user_input 전체 전달 (원문 분석 필요)
            - ToT/CoT(후속 단계): GoT가 core_pattern을 추출한 경우
              user_input 대신 core_pattern을 참조하여 토큰 절감
        """
        parts: list[str] = []

        # 기본 입력 — GoT는 원문 전체, ToT/CoT는 이전 phase 결과가 있으면 요약 참조
        if phase == "GoT" or got_result is None:
            # GoT(첫 단계) 또는 이전 결과가 없는 경우: user_input 전체 전달
            parts.append(f"[사용자 입력]\n{user_input}")
        else:
            # ToT/CoT: GoT가 이미 핵심을 추출했으므로 user_input 요약만 전달
            core_pattern = got_result.get("core_pattern", "")
            if core_pattern:
                # user_input 앞 100자만 참조 + GoT core_pattern 활용
                input_preview = user_input[:100] + ("..." if len(user_input) > 100 else "")
                parts.append(f"[사용자 입력 요약]\n{input_preview}")
            else:
                # core_pattern이 없으면 원문 전달 (fallback)
                parts.append(f"[사용자 입력]\n{user_input}")

        # Intent Classifier(TIER 0) 정보
        if intent:
            intent_info = intent.get("primary_intent", "미확인")
            complexity = intent.get("complexity_score", 0.5)
            parts.append(f"[의도 분류]\n- 의도: {intent_info}\n- 복잡도: {complexity}")

        # 독립 에이전트 결과 — DI 호출 결과 포함
        if memory_result and memory_result.get("episodes"):
            episode_count = len(memory_result["episodes"])
            parts.append(f"[과거 에피소드 기억]\n- {episode_count}건 발견")
        if knowledge_result and knowledge_result.get("articles"):
            article_count = len(knowledge_result["articles"])
            parts.append(f"[관련 전문 지식]\n- {article_count}건 발견")

        # 이전 phase 결과 — 누적 전달
        if got_result is not None:
            core = got_result.get("core_pattern", "")
            node_count = len(got_result.get("nodes", []))
            edge_count = len(got_result.get("edges", []))
            insights = got_result.get("insights", [])
            parts.append(
                f"[GoT 그래프 분석 결과]\n"
                f"- 핵심 패턴: {core}\n"
                f"- 노드 {node_count}개, 엣지 {edge_count}개\n"
                f"- 인사이트: {insights}"
            )

        if tot_result is not None:
            selected = tot_result.get("selected", "?")
            rationale = tot_result.get("selection_rationale", "")
            alt_count = len(tot_result.get("alternatives", []))
            parts.append(
                f"[ToT 구조 탐색 결과]\n"
                f"- {alt_count}개 대안 중 #{selected} 선택\n"
                f"- 선택 이유: {rationale}"
            )

        return "\n\n".join(parts)

    # === 조건부 독립 에이전트 호출 (기존 유지) ===

    async def _fetch_memory_if_needed(
        self,
        user_input: str,
        user_id: str,
        execution_plan: dict[str, Any],
        complexity: float,
    ) -> dict[str, Any] | None:
        """
        에피소드 기억이 필요한 경우에만 Episode Memory를 호출한다.

        호출 조건:
            1. execution_plan에서 needs_memory가 True이거나
            2. 복잡도가 0.6 이상인 경우

        어댑터 패턴:
            EpisodeMemoryAgent.process(state) → Stub 호환 형식 변환.
            process() 반환: {"memory_results": {"items": [...], "summary": "..."}}
            변환 결과:     {"episodes": [...], "relevance_scores": [...], "summary": "..."}
        """
        needs_memory = execution_plan.get("needs_memory", False)

        if needs_memory or complexity >= 0.6:
            self.logger.info("Episode Memory 조건부 호출 (complexity=%.2f)", complexity)

            memory_state: AgentState = {
                "user_input": user_input,
                "user_id": user_id,
            }
            result = await self.episode_memory.process(memory_state)
            memory_data = result.get("memory_results")

            if not memory_data:
                return None

            # process() → Stub 호환 형식으로 변환
            items = memory_data.get("items", [])
            return {
                "episodes": items,
                "relevance_scores": [item.get("score", 0.0) for item in items],
                "summary": memory_data.get("summary", ""),
            }

        return None

    async def _fetch_knowledge_if_needed(
        self,
        user_input: str,
        execution_plan: dict[str, Any],
        complexity: float,
    ) -> dict[str, Any] | None:
        """
        전문 지식이 필요한 경우에만 Knowledge Agent를 호출한다.

        호출 조건:
            1. execution_plan에서 needs_knowledge가 True이거나
            2. 복잡도가 0.5 이상인 경우
        """
        needs_knowledge = execution_plan.get("needs_knowledge", False)

        if needs_knowledge or complexity >= 0.5:
            self.logger.info("Knowledge Agent 조건부 호출 (complexity=%.2f)", complexity)
            return await self.knowledge_agent.search(
                query=user_input,
                domain="mental_health",
            )

        return None

    # === GoT 그래프 데이터 저장 ===

    async def _save_graph_data(
        self,
        got_result: dict[str, Any],
        session_id: str,
        episode_id: str,
        state: AgentState,
    ) -> None:
        """GoT 결과를 Neo4j에 저장하고 Backend에 전송 + RDB 누적 그래프 갱신한다.

        세 작업 모두 실패해도 파이프라인은 계속 진행한다.
        """
        user_id = state.get("user_id", "")
        await self._save_got_to_neo4j(got_result, session_id, episode_id, user_id)

        # RDB 누적 그래프 — label+group 기준 통합 UPSERT
        from src.api.graph_cumulative import publish_graph_to_rdb

        await publish_graph_to_rdb(got_result, cast(dict[str, Any], state), episode_id)

    async def _save_got_to_neo4j(
        self,
        got_result: dict[str, Any],
        session_id: str,
        episode_id: str,
        user_id: str = "",
    ) -> None:
        """GoT 노드/엣지를 Neo4j에 저장한다.

        실패해도 파이프라인은 계속 진행한다 (graceful degradation).

        [이관 주석] Neo4j를 Backend로 이관 시:
        - 이 메서드 전체를 삭제한다.
        - _save_graph_data()에서 이 호출도 제거한다.
        - Backend 전송(_publish_graph_to_backend)만 유지한다.
        """
        if not episode_id:
            return
        try:
            from src.db.factory import create_graph_client

            async with create_graph_client() as client:
                for node in got_result.get("nodes", []):
                    await client.execute_query(
                        "MERGE (g:GoTNode {got_node_id: $id}) "
                        "SET g.node_type = $type, g.label = $label, "
                        "g.weight = $intensity, g.episode_id = $episode_id, "
                        "g.group = $group",
                        params={
                            "id": f"{episode_id}_{node.get('id', '')}",
                            "type": node.get("type", "concept"),
                            "label": node.get("label", ""),
                            "intensity": node.get("intensity", 0.5),
                            "episode_id": episode_id,
                            "group": node.get("group", "emotional_exhaustion"),
                        },
                    )
                for edge in got_result.get("edges", []):
                    await client.execute_query(
                        "MATCH (a:GoTNode {got_node_id: $from_id}), "
                        "(b:GoTNode {got_node_id: $to_id}) "
                        "MERGE (a)-[:LEADS_TO {relationship: $rel}]->(b)",
                        params={
                            "from_id": f"{episode_id}_{edge.get('from', '')}",
                            "to_id": f"{episode_id}_{edge.get('to', '')}",
                            "rel": edge.get("relationship", "related"),
                        },
                    )
                # User → Session → GoTNode 관계
                if session_id:
                    # User, Session 노드 생성 및 HAS_SESSION 관계
                    if user_id:
                        await client.execute_query(
                            "MERGE (u:User {user_id: $uid}) "
                            "MERGE (s:Session {session_id: $sid}) "
                            "MERGE (u)-[:HAS_SESSION]->(s)",
                            params={"uid": user_id, "sid": session_id},
                        )
                    else:
                        await client.execute_query(
                            "MERGE (s:Session {session_id: $sid})",
                            params={"sid": session_id},
                        )
                    # Session → GoTNode 관계
                    await client.execute_query(
                        "MATCH (s:Session {session_id: $sid}), (g:GoTNode) "
                        "WHERE g.episode_id = $eid "
                        "MERGE (s)-[:REASONED_BY]->(g)",
                        params={"sid": session_id, "eid": episode_id},
                    )
        except Exception as e:
            self.logger.warning("Neo4j 저장 실패 (파이프라인 계속): %s", e)


async def podcast_reasoning_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Podcast Reasoning.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    from src.agents.podcast.knowledge import KnowledgeAgent

    agent = PodcastReasoningAgent(knowledge_agent=KnowledgeAgent())
    return await agent(state)

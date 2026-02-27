"""
Podcast Reasoning 에이전트 테스트.

에피소드 구조 설계, DI 기반 조건부 호출(Episode Memory / Knowledge),
복잡도 기반 추론 깊이 라우팅, GoT/ToT/CoT 파이프라인,
하위 호환성 등을 검증한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.podcast.podcast_reasoning import (
    PodcastReasoningAgent,
    podcast_reasoning_agent,
    podcast_reasoning_node,
)
from src.agents.shared.stubs import EpisodeMemoryStub, KnowledgeAgentStub
from src.models.agent_state import AgentState

# === 공용 픽스처 ===


@pytest.fixture
def mock_memory() -> AsyncMock:
    """모의 Episode Memory 에이전트."""
    mock = AsyncMock(spec=EpisodeMemoryStub)
    mock.search.return_value = {
        "episodes": [{"id": "ep_001", "title": "이전 에피소드"}],
        "relevance_scores": [0.85],
    }
    return mock


@pytest.fixture
def mock_knowledge() -> AsyncMock:
    """모의 Knowledge Agent."""
    mock = AsyncMock(spec=KnowledgeAgentStub)
    mock.search.return_value = {
        "articles": [{"id": "art_001", "title": "스트레스 관리 가이드"}],
        "guidelines": ["충분한 수면", "규칙적인 운동"],
    }
    return mock


@pytest.fixture
def agent(mock_memory: AsyncMock, mock_knowledge: AsyncMock) -> PodcastReasoningAgent:
    """DI로 모의 에이전트가 주입된 Podcast Reasoning 인스턴스."""
    return PodcastReasoningAgent(
        episode_memory=mock_memory,
        knowledge_agent=mock_knowledge,
    )


@pytest.fixture
def agent_with_stubs() -> PodcastReasoningAgent:
    """Stub을 사용하는 기본 Podcast Reasoning 인스턴스."""
    return PodcastReasoningAgent()


@pytest.fixture
def base_state() -> AgentState:
    """기본 AgentState — 복잡도 낮음 (minimal depth, DI 호출 안 함)."""
    return AgentState(
        user_input="오늘 하루 어떻게 보냈는지 이야기해볼게요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "daily_reflection", "complexity_score": 0.3},
    )


@pytest.fixture
def complex_state() -> AgentState:
    """복잡한 AgentState — 복잡도 높음 (full depth, DI 호출 트리거).

    TIER 1 병렬 실행 구조에 맞게 같은 TIER 1 에이전트 결과
    (content_analysis, emotion_vectors)는 포함하지 않는다.
    Podcast Reasoning은 TIER 0 결과(intent)만 참조한다.
    """
    return AgentState(
        user_input="직장에서의 대인관계 스트레스와 번아웃을 어떻게 극복할 수 있을까요?",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "coping_strategy", "complexity_score": 0.8},
    )


@pytest.fixture
def full_depth_state() -> AgentState:
    """complexity=0.9 → "full" depth 트리거용 AgentState."""
    return AgentState(
        user_input="트라우마 이후의 회복과 성장 과정을 깊이 있게 탐구하고 싶어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "deep_exploration", "complexity_score": 0.9},
    )


@pytest.fixture
def standard_depth_state() -> AgentState:
    """complexity=0.6 → "standard" depth 트리거용 AgentState."""
    return AgentState(
        user_input="최근에 잠을 잘 못 자고 있어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "sleep_issue", "complexity_score": 0.6},
    )


# === 모의 LLM 결과 픽스처 ===


@pytest.fixture
def mock_got_result() -> dict[str, Any]:
    """GoT 그래프 분석 모의 결과."""
    return {
        "core_pattern": "직장 스트레스와 번아웃의 복합적 연결",
        "nodes": [
            {"id": "node_1", "type": "topic", "label": "직장 스트레스", "intensity": 0.9},
            {"id": "node_2", "type": "emotion", "label": "번아웃", "intensity": 0.8},
            {"id": "node_3", "type": "concept", "label": "대인관계", "intensity": 0.7},
            {"id": "node_4", "type": "experience", "label": "업무 과부하", "intensity": 0.6},
            {"id": "node_5", "type": "concept", "label": "자기돌봄", "intensity": 0.5},
        ],
        "edges": [
            {"from": "node_1", "to": "node_2", "relationship": "causes", "weight": 0.9},
            {"from": "node_3", "to": "node_1", "relationship": "influences", "weight": 0.7},
            {"from": "node_4", "to": "node_2", "relationship": "causes", "weight": 0.8},
            {"from": "node_5", "to": "node_2", "relationship": "contrasts", "weight": 0.6},
        ],
        "insights": ["스트레스-번아웃 경로가 지배적", "자기돌봄이 대안 경로로 존재"],
    }


@pytest.fixture
def mock_tot_result() -> dict[str, Any]:
    """ToT 대안 평가 모의 결과."""
    return {
        "alternatives": [
            {
                "id": 1,
                "structure_summary": "원인 탐색 → 극복 사례 → 실천법",
                "segments": [
                    {
                        "segment": "intro",
                        "title": "오프닝",
                        "duration_seconds": 20,
                        "focus": "공감",
                    },
                    {
                        "segment": "body_1",
                        "title": "원인 탐색",
                        "duration_seconds": 80,
                        "focus": "분석",
                    },
                    {
                        "segment": "body_2",
                        "title": "극복 사례",
                        "duration_seconds": 80,
                        "focus": "사례",
                    },
                    {
                        "segment": "outro",
                        "title": "마무리",
                        "duration_seconds": 20,
                        "focus": "격려",
                    },
                ],
                "strengths": ["체계적 구조", "실용적"],
                "weaknesses": ["감정 탐색 부족"],
                "score": 0.85,
            },
            {
                "id": 2,
                "structure_summary": "감정 인정 → 공감 대화 → 작은 실천",
                "segments": [
                    {
                        "segment": "intro",
                        "title": "감정 인정",
                        "duration_seconds": 30,
                        "focus": "공감",
                    },
                    {
                        "segment": "body_1",
                        "title": "공감 대화",
                        "duration_seconds": 120,
                        "focus": "대화",
                    },
                    {
                        "segment": "outro",
                        "title": "작은 실천",
                        "duration_seconds": 30,
                        "focus": "실천",
                    },
                ],
                "strengths": ["높은 공감력", "따뜻한 톤"],
                "weaknesses": ["구조 단순"],
                "score": 0.75,
            },
        ],
        "selected": 1,
        "selection_rationale": "체계적이면서 실용적인 구조가 3-5분 에피소드에 적합",
    }


@pytest.fixture
def mock_cot_result() -> dict[str, Any]:
    """CoT 상세화 모의 결과 (3-5분 범위, 210초)."""
    return {
        "episode_structure": [
            {
                "segment": "intro",
                "title": "오늘의 이야기",
                "duration_seconds": 30,
                "content_summary": "에피소드 소개",
                "tone": "warm",
            },
            {
                "segment": "body_1",
                "title": "스트레스의 본질",
                "duration_seconds": 150,
                "content_summary": "스트레스 원인 탐색",
                "tone": "informative",
            },
            {
                "segment": "outro",
                "title": "마무리",
                "duration_seconds": 30,
                "content_summary": "격려와 마무리",
                "tone": "encouraging",
            },
        ],
        "narrative_flow": "공감 → 탐색 → 실천 → 격려",
        "key_points": ["스트레스 인식", "대처 전략", "자기돌봄"],
        "emotional_journey": [
            {"phase": "opening", "target_emotion": "공감", "approach": "경험 공유"},
            {"phase": "resolution", "target_emotion": "안도", "approach": "실천 방법"},
        ],
        "confidence": 0.85,
    }


@pytest.fixture
def mock_reasoning_result() -> dict[str, Any]:
    """기존 테스트 호환 — LLM이 반환할 모의 추론 결과 (CoT 단독용)."""
    return {
        "episode_structure": [
            {
                "segment": "intro",
                "title": "오늘의 이야기",
                "duration_seconds": 30,
                "content_summary": "에피소드 소개",
                "tone": "warm",
            },
            {
                "segment": "body_1",
                "title": "스트레스의 본질",
                "duration_seconds": 150,
                "content_summary": "스트레스 원인 탐색",
                "tone": "informative",
            },
            {
                "segment": "outro",
                "title": "마무리",
                "duration_seconds": 30,
                "content_summary": "격려와 마무리",
                "tone": "encouraging",
            },
        ],
        "narrative_flow": "공감 → 탐색 → 실천 → 격려",
        "key_points": ["스트레스 인식", "대처 전략", "자기돌봄"],
        "emotional_journey": [
            {"phase": "opening", "target_emotion": "공감", "approach": "경험 공유"},
            {"phase": "resolution", "target_emotion": "안도", "approach": "실천 방법"},
        ],
        "confidence": 0.85,
    }


# === 기존 테스트 (minimal depth — CoT 1회 호출) ===


class TestPodcastReasoningAgent:
    """Podcast Reasoning 에이전트 핵심 로직 테스트."""

    @pytest.mark.asyncio
    async def test_process_returns_reasoning_result(
        self,
        agent: PodcastReasoningAgent,
        base_state: AgentState,
        mock_reasoning_result: dict[str, Any],
    ) -> None:
        """process()가 reasoning_result를 올바르게 반환하는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_reasoning_result
        ):
            result = await agent.process(base_state)

        assert "reasoning_result" in result
        # 하위 호환 — 기존 필드 존재 확인
        assert result["reasoning_result"]["confidence"] == 0.85
        # 신규 메타데이터 확인
        assert result["reasoning_result"]["reasoning_depth"] == "minimal"
        assert result["reasoning_result"]["reasoning_strategy"] == "CoT"

    @pytest.mark.asyncio
    async def test_low_complexity_skips_di_calls(
        self,
        agent: PodcastReasoningAgent,
        base_state: AgentState,
        mock_reasoning_result: dict[str, Any],
        mock_memory: AsyncMock,
        mock_knowledge: AsyncMock,
    ) -> None:
        """복잡도 낮으면 (0.3) Episode Memory / Knowledge 호출을 건너뛰는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_reasoning_result
        ):
            result = await agent.process(base_state)

        # 복잡도 0.3 → memory(>=0.6)도, knowledge(>=0.5)도 호출 안 됨
        mock_memory.search.assert_not_called()
        mock_knowledge.search.assert_not_called()
        assert "memory_results" not in result
        assert "knowledge_results" not in result

    @pytest.mark.asyncio
    async def test_high_complexity_calls_both_di_agents(
        self,
        agent: PodcastReasoningAgent,
        complex_state: AgentState,
        mock_memory: AsyncMock,
        mock_knowledge: AsyncMock,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """복잡도 높으면 (0.8) Episode Memory, Knowledge 둘 다 호출하는지 확인."""
        with patch.object(
            agent,
            "call_llm_json",
            new_callable=AsyncMock,
            side_effect=[mock_got_result, mock_tot_result, mock_cot_result],
        ):
            result = await agent.process(complex_state)

        # 복잡도 0.8 → memory(>=0.6), knowledge(>=0.5) 모두 호출
        mock_memory.search.assert_called_once()
        mock_knowledge.search.assert_called_once()
        assert "memory_results" in result
        assert "knowledge_results" in result

    @pytest.mark.asyncio
    async def test_execution_plan_forces_memory_call(
        self,
        agent: PodcastReasoningAgent,
        mock_reasoning_result: dict[str, Any],
        mock_memory: AsyncMock,
    ) -> None:
        """execution_plan의 needs_memory=True가 복잡도 무관하게 호출을 트리거하는지 확인."""
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user",
            session_id="sess_test",
            mode="podcast",
            intent={"complexity_score": 0.1},  # 매우 낮은 복잡도
            execution_plan={"needs_memory": True},
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_reasoning_result
        ):
            await agent.process(state)

        mock_memory.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_execution_plan_forces_knowledge_call(
        self,
        agent: PodcastReasoningAgent,
        mock_reasoning_result: dict[str, Any],
        mock_knowledge: AsyncMock,
    ) -> None:
        """execution_plan의 needs_knowledge=True가 복잡도 무관하게 호출을 트리거하는지 확인."""
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user",
            session_id="sess_test",
            mode="podcast",
            intent={"complexity_score": 0.1},  # 매우 낮은 복잡도
            execution_plan={"needs_knowledge": True},
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_reasoning_result
        ):
            await agent.process(state)

        mock_knowledge.search.assert_called_once()


class TestPodcastReasoningDI:
    """의존성 주입 (DI) 패턴 테스트."""

    def test_default_stubs_injected(self, agent_with_stubs: PodcastReasoningAgent) -> None:
        """DI 인자 없이 생성하면 stub이 주입되는지 확인."""
        assert isinstance(agent_with_stubs.episode_memory, EpisodeMemoryStub)
        assert isinstance(agent_with_stubs.knowledge_agent, KnowledgeAgentStub)

    def test_custom_agents_injected(
        self, mock_memory: AsyncMock, mock_knowledge: AsyncMock
    ) -> None:
        """커스텀 에이전트가 올바르게 주입되는지 확인."""
        agent = PodcastReasoningAgent(
            episode_memory=mock_memory,
            knowledge_agent=mock_knowledge,
        )
        assert agent.episode_memory is mock_memory
        assert agent.knowledge_agent is mock_knowledge

    def test_agent_attributes(self, agent_with_stubs: PodcastReasoningAgent) -> None:
        """에이전트 기본 속성이 올바르게 설정되는지 확인."""
        assert agent_with_stubs.name == "podcast_reasoning"
        assert agent_with_stubs.tier == 1


class TestPodcastReasoningStubs:
    """Stub 에이전트 동작 테스트."""

    @pytest.mark.asyncio
    async def test_episode_memory_stub_returns_empty(self) -> None:
        """EpisodeMemoryStub이 빈 결과를 반환하는지 확인."""
        stub = EpisodeMemoryStub()
        result = await stub.search(query="test", user_id="user")
        assert result == {"episodes": [], "relevance_scores": []}

    @pytest.mark.asyncio
    async def test_knowledge_agent_stub_returns_empty(self) -> None:
        """KnowledgeAgentStub이 빈 결과를 반환하는지 확인."""
        stub = KnowledgeAgentStub()
        result = await stub.search(query="test")
        assert result == {"articles": [], "guidelines": []}


class TestPodcastReasoningNode:
    """LangGraph 노드 함수 테스트."""

    @pytest.mark.asyncio
    async def test_node_function_calls_agent(
        self,
        base_state: AgentState,
        mock_reasoning_result: dict[str, Any],
    ) -> None:
        """podcast_reasoning_node가 에이전트를 올바르게 호출하는지 확인."""
        with patch.object(
            podcast_reasoning_agent,
            "process",
            new_callable=AsyncMock,
            return_value={"reasoning_result": mock_reasoning_result},
        ):
            result = await podcast_reasoning_node(base_state)

        assert "reasoning_result" in result


# === 추론 깊이 결정 테스트 (v6 신규) ===


class TestReasoningDepth:
    """_determine_reasoning_depth() 단위 테스트."""

    def test_full_depth_at_high_complexity(self, agent_with_stubs: PodcastReasoningAgent) -> None:
        """complexity ≥ 0.8 → 'full' 반환 확인."""
        assert agent_with_stubs._determine_reasoning_depth(0.8) == "full"
        assert agent_with_stubs._determine_reasoning_depth(0.9) == "full"
        assert agent_with_stubs._determine_reasoning_depth(1.0) == "full"

    def test_standard_depth_at_medium_complexity(
        self, agent_with_stubs: PodcastReasoningAgent
    ) -> None:
        """0.5 ≤ complexity < 0.8 → 'standard' 반환 확인."""
        assert agent_with_stubs._determine_reasoning_depth(0.5) == "standard"
        assert agent_with_stubs._determine_reasoning_depth(0.6) == "standard"
        assert agent_with_stubs._determine_reasoning_depth(0.79) == "standard"

    def test_minimal_depth_at_low_complexity(self, agent_with_stubs: PodcastReasoningAgent) -> None:
        """complexity < 0.5 → 'minimal' 반환 확인."""
        assert agent_with_stubs._determine_reasoning_depth(0.0) == "minimal"
        assert agent_with_stubs._determine_reasoning_depth(0.3) == "minimal"
        assert agent_with_stubs._determine_reasoning_depth(0.49) == "minimal"


# === 추론 파이프라인 통합 테스트 (v6 신규) ===


class TestReasoningPipeline:
    """추론 파이프라인 통합 테스트 — LLM 호출 횟수, depth별 결과 포함 여부."""

    @pytest.mark.asyncio
    async def test_full_pipeline_calls_llm_3_times(
        self,
        agent: PodcastReasoningAgent,
        full_depth_state: AgentState,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """full depth일 때 GoT+ToT+CoT = LLM 3회 호출 확인."""
        mock = AsyncMock(side_effect=[mock_got_result, mock_tot_result, mock_cot_result])
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(full_depth_state)

        assert mock.call_count == 3
        reasoning = result["reasoning_result"]
        assert reasoning["reasoning_depth"] == "full"
        assert reasoning["reasoning_strategy"] == "GoT+ToT+CoT"
        assert "got_result" in reasoning
        assert "tot_result" in reasoning

    @pytest.mark.asyncio
    async def test_standard_pipeline_calls_llm_2_times(
        self,
        agent: PodcastReasoningAgent,
        standard_depth_state: AgentState,
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """standard depth일 때 ToT+CoT = LLM 2회 호출 확인."""
        mock = AsyncMock(side_effect=[mock_tot_result, mock_cot_result])
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(standard_depth_state)

        assert mock.call_count == 2
        reasoning = result["reasoning_result"]
        assert reasoning["reasoning_depth"] == "standard"
        assert reasoning["reasoning_strategy"] == "ToT+CoT"
        assert "got_result" not in reasoning  # GoT 미실행
        assert "tot_result" in reasoning

    @pytest.mark.asyncio
    async def test_minimal_pipeline_calls_llm_1_time(
        self,
        agent: PodcastReasoningAgent,
        base_state: AgentState,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """minimal depth일 때 CoT만 = LLM 1회 호출 확인."""
        mock = AsyncMock(return_value=mock_cot_result)
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(base_state)

        assert mock.call_count == 1
        reasoning = result["reasoning_result"]
        assert reasoning["reasoning_depth"] == "minimal"
        assert reasoning["reasoning_strategy"] == "CoT"
        assert "got_result" not in reasoning
        assert "tot_result" not in reasoning

    @pytest.mark.asyncio
    async def test_full_pipeline_includes_got_data(
        self,
        agent: PodcastReasoningAgent,
        full_depth_state: AgentState,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """full depth에서 got_result가 정확한 데이터를 포함하는지 확인."""
        mock = AsyncMock(side_effect=[mock_got_result, mock_tot_result, mock_cot_result])
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(full_depth_state)

        got = result["reasoning_result"]["got_result"]
        assert got["core_pattern"] == "직장 스트레스와 번아웃의 복합적 연결"
        assert len(got["nodes"]) == 5
        assert len(got["edges"]) == 4

    @pytest.mark.asyncio
    async def test_full_pipeline_includes_tot_data(
        self,
        agent: PodcastReasoningAgent,
        full_depth_state: AgentState,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """full depth에서 tot_result가 정확한 데이터를 포함하는지 확인."""
        mock = AsyncMock(side_effect=[mock_got_result, mock_tot_result, mock_cot_result])
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(full_depth_state)

        tot = result["reasoning_result"]["tot_result"]
        assert tot["selected"] == 1
        assert len(tot["alternatives"]) == 2

    @pytest.mark.asyncio
    async def test_strategy_label_mapping(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """_depth_to_strategy_label이 올바른 라벨을 반환하는지 확인."""
        assert PodcastReasoningAgent._depth_to_strategy_label("full") == "GoT+ToT+CoT"
        assert PodcastReasoningAgent._depth_to_strategy_label("standard") == "ToT+CoT"
        assert PodcastReasoningAgent._depth_to_strategy_label("minimal") == "CoT"


# === GoT Phase 단위 테스트 (v6 신규) ===


class TestGoTPhase:
    """_graph_of_thoughts() 단위 테스트."""

    @pytest.mark.asyncio
    async def test_got_returns_graph_structure(
        self,
        agent: PodcastReasoningAgent,
        mock_got_result: dict[str, Any],
    ) -> None:
        """GoT 결과에 nodes, edges, core_pattern, insights가 포함되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_got_result
        ):
            result = await agent._graph_of_thoughts(
                user_input="스트레스 테스트",
                intent={"primary_intent": "test", "complexity_score": 0.9},
                memory_result=None,
                knowledge_result=None,
            )

        assert "core_pattern" in result
        assert "nodes" in result
        assert "edges" in result
        assert "insights" in result

    @pytest.mark.asyncio
    async def test_got_passes_context_to_llm(
        self,
        agent: PodcastReasoningAgent,
        mock_got_result: dict[str, Any],
    ) -> None:
        """GoT가 user_input과 intent를 LLM 컨텍스트에 포함하는지 확인."""
        mock = AsyncMock(return_value=mock_got_result)
        with patch.object(agent, "call_llm_json", mock):
            await agent._graph_of_thoughts(
                user_input="스트레스 관리",
                intent={"primary_intent": "coping", "complexity_score": 0.9},
                memory_result=None,
                knowledge_result=None,
            )

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        assert "스트레스 관리" in user_message
        assert "coping" in user_message


# === ToT Phase 단위 테스트 (v6 신규) ===


class TestToTPhase:
    """_tree_of_thoughts() 단위 테스트."""

    @pytest.mark.asyncio
    async def test_tot_returns_alternatives(
        self,
        agent: PodcastReasoningAgent,
        mock_tot_result: dict[str, Any],
    ) -> None:
        """ToT 결과에 alternatives, selected, selection_rationale가 포함되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_tot_result
        ):
            result = await agent._tree_of_thoughts(
                user_input="스트레스 테스트",
                intent={"primary_intent": "test"},
                got_result=None,
                memory_result=None,
                knowledge_result=None,
            )

        assert "alternatives" in result
        assert "selected" in result
        assert "selection_rationale" in result

    @pytest.mark.asyncio
    async def test_tot_receives_got_result_in_context(
        self,
        agent: PodcastReasoningAgent,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
    ) -> None:
        """ToT가 GoT 결과를 LLM 컨텍스트에 포함하는지 확인."""
        mock = AsyncMock(return_value=mock_tot_result)
        with patch.object(agent, "call_llm_json", mock):
            await agent._tree_of_thoughts(
                user_input="스트레스 관리",
                intent={"primary_intent": "coping"},
                got_result=mock_got_result,
                memory_result=None,
                knowledge_result=None,
            )

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        # GoT 결과가 컨텍스트에 포함되어야 한다
        assert "GoT 그래프 분석 결과" in user_message
        assert "직장 스트레스와 번아웃의 복합적 연결" in user_message


# === CoT Phase 단위 테스트 (v6 신규) ===


class TestCoTPhase:
    """_chain_of_thoughts() 단위 테스트."""

    @pytest.mark.asyncio
    async def test_cot_returns_episode_structure(
        self,
        agent: PodcastReasoningAgent,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """CoT 결과에 episode_structure, narrative_flow 등이 포함되는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            result = await agent._chain_of_thoughts(
                user_input="스트레스 테스트",
                intent={"primary_intent": "test"},
                got_result=None,
                tot_result=None,
                memory_result=None,
                knowledge_result=None,
            )

        assert "episode_structure" in result
        assert "narrative_flow" in result
        assert "key_points" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_cot_receives_tot_result_in_context(
        self,
        agent: PodcastReasoningAgent,
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """CoT가 ToT 결과를 LLM 컨텍스트에 포함하는지 확인."""
        mock = AsyncMock(return_value=mock_cot_result)
        with patch.object(agent, "call_llm_json", mock):
            await agent._chain_of_thoughts(
                user_input="스트레스 관리",
                intent={"primary_intent": "coping"},
                got_result=None,
                tot_result=mock_tot_result,
                memory_result=None,
                knowledge_result=None,
            )

        call_args = mock.call_args
        user_message = call_args.kwargs.get(
            "user_message", call_args.args[1] if len(call_args.args) > 1 else ""
        )
        # ToT 결과가 컨텍스트에 포함되어야 한다
        assert "ToT 구조 탐색 결과" in user_message
        assert "#1 선택" in user_message


# === 하위 호환성 테스트 (v6 신규) ===


class TestBackwardCompatibility:
    """모든 depth에서 기존 필드(narrative_flow, key_points 등)가 존재하는지 확인."""

    @pytest.mark.asyncio
    async def test_minimal_depth_has_legacy_fields(
        self,
        agent: PodcastReasoningAgent,
        base_state: AgentState,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """minimal depth에서도 기존 필드가 reasoning_result에 존재하는지 확인."""
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            result = await agent.process(base_state)

        reasoning = result["reasoning_result"]
        # 기존 필드 존재 — Script Generator, Batch Validator가 이 필드에 접근
        assert "episode_structure" in reasoning
        assert "narrative_flow" in reasoning
        assert "key_points" in reasoning
        assert "emotional_journey" in reasoning
        assert "confidence" in reasoning

    @pytest.mark.asyncio
    async def test_full_depth_has_legacy_fields(
        self,
        agent: PodcastReasoningAgent,
        full_depth_state: AgentState,
        mock_got_result: dict[str, Any],
        mock_tot_result: dict[str, Any],
        mock_cot_result: dict[str, Any],
    ) -> None:
        """full depth에서도 기존 필드가 reasoning_result에 존재하는지 확인."""
        mock = AsyncMock(side_effect=[mock_got_result, mock_tot_result, mock_cot_result])
        with patch.object(agent, "call_llm_json", mock):
            result = await agent.process(full_depth_state)

        reasoning = result["reasoning_result"]
        # 기존 필드 존재
        assert "episode_structure" in reasoning
        assert "narrative_flow" in reasoning
        assert "key_points" in reasoning
        assert "emotional_journey" in reasoning
        assert "confidence" in reasoning
        # 신규 필드도 공존
        assert "got_result" in reasoning
        assert "tot_result" in reasoning
        assert "reasoning_depth" in reasoning
        assert "reasoning_strategy" in reasoning


# === 엣지 케이스 테스트 ===


class TestPodcastReasoningEdgeCases:
    """Podcast Reasoning 에이전트 엣지 케이스 테스트.

    경계값, 빈 입력, 누락된 필드, stub 예외 전파 등을 검증한다.
    """

    @pytest.mark.asyncio
    async def test_empty_user_input(
        self,
        agent: PodcastReasoningAgent,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """빈 문자열 user_input으로도 process()가 정상 동작하는지 확인 (LLM이 처리)."""
        state = AgentState(
            user_input="",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
            intent={"primary_intent": "unknown", "complexity_score": 0.3},
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            result = await agent.process(state)

        # 빈 입력이어도 reasoning_result 구조는 정상 반환
        assert "reasoning_result" in result
        assert result["reasoning_result"]["reasoning_depth"] == "minimal"
        assert result["reasoning_result"]["reasoning_strategy"] == "CoT"

    @pytest.mark.asyncio
    async def test_missing_intent_field(
        self,
        agent: PodcastReasoningAgent,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """state에 intent 키가 아예 없을 때 기본값으로 처리되는지 확인."""
        # AgentState는 total=False이므로 intent 키 생략 가능
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
        )
        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            result = await agent.process(state)

        # intent 없으면 complexity 기본값 0.5 → "standard" depth
        assert "reasoning_result" in result
        assert result["reasoning_result"]["reasoning_depth"] == "standard"
        assert result["reasoning_result"]["reasoning_strategy"] == "ToT+CoT"

    @pytest.mark.asyncio
    async def test_llm_returns_empty_dict(
        self,
        agent: PodcastReasoningAgent,
        base_state: AgentState,
    ) -> None:
        """call_llm_json이 빈 dict를 반환해도 필수 메타데이터 필드가 존재하는지 확인."""
        # CoT만 실행 (minimal depth) — LLM이 {} 반환
        with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value={}):
            result = await agent.process(base_state)

        reasoning = result["reasoning_result"]
        # 메타데이터 필드는 파이프라인이 직접 설정하므로 반드시 존재
        assert reasoning["reasoning_depth"] == "minimal"
        assert reasoning["reasoning_strategy"] == "CoT"
        # 콘텐츠 필드는 .get() 기본값으로 빈 리스트/빈 문자열/0.0
        assert reasoning["episode_structure"] == []
        assert reasoning["narrative_flow"] == ""
        assert reasoning["key_points"] == []
        assert reasoning["emotional_journey"] == []
        assert reasoning["confidence"] == 0.0

    def test_boundary_complexity_exactly_0_5(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """complexity=0.5 경계값이 'standard' depth를 반환하는지 확인."""
        depth = agent_with_stubs._determine_reasoning_depth(0.5)
        assert depth == "standard"

    def test_boundary_complexity_exactly_0_8(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """complexity=0.8 경계값이 'full' depth를 반환하는지 확인."""
        depth = agent_with_stubs._determine_reasoning_depth(0.8)
        assert depth == "full"

    def test_boundary_complexity_zero(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """complexity=0.0 최솟값이 'minimal' depth를 반환하는지 확인."""
        depth = agent_with_stubs._determine_reasoning_depth(0.0)
        assert depth == "minimal"

    def test_boundary_complexity_one(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """complexity=1.0 최댓값이 'full' depth를 반환하는지 확인."""
        depth = agent_with_stubs._determine_reasoning_depth(1.0)
        assert depth == "full"

    @pytest.mark.asyncio
    async def test_memory_stub_exception_handling(
        self,
        mock_knowledge: AsyncMock,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """EpisodeMemoryStub.search()에서 예외 발생 시 예외가 전파되는지 확인.

        _fetch_memory_if_needed에 try/except가 없으므로 예외가 그대로 전파된다.
        """
        # 예외를 발생시키는 모의 Episode Memory 생성
        failing_memory = AsyncMock()
        failing_memory.search.side_effect = Exception("메모리 검색 실패")

        agent = PodcastReasoningAgent(
            episode_memory=failing_memory,
            knowledge_agent=mock_knowledge,
        )

        # complexity=0.7 → memory 호출 트리거 (>= 0.6)
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
            intent={"primary_intent": "test", "complexity_score": 0.7},
        )

        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            with pytest.raises(Exception, match="메모리 검색 실패"):
                await agent.process(state)

    @pytest.mark.asyncio
    async def test_knowledge_stub_exception_handling(
        self,
        mock_memory: AsyncMock,
        mock_cot_result: dict[str, Any],
    ) -> None:
        """KnowledgeAgentStub.search()에서 예외 발생 시 예외가 전파되는지 확인.

        _fetch_knowledge_if_needed에 try/except가 없으므로 예외가 그대로 전파된다.
        """
        # 예외를 발생시키는 모의 Knowledge Agent 생성
        failing_knowledge = AsyncMock()
        failing_knowledge.search.side_effect = Exception("지식 검색 실패")

        agent = PodcastReasoningAgent(
            episode_memory=mock_memory,
            knowledge_agent=failing_knowledge,
        )

        # complexity=0.6 → knowledge 호출 트리거 (>= 0.5)
        state = AgentState(
            user_input="테스트 입력",
            user_id="test_user_001",
            session_id="sess_test_001",
            mode="podcast",
            intent={"primary_intent": "test", "complexity_score": 0.6},
        )

        with patch.object(
            agent, "call_llm_json", new_callable=AsyncMock, return_value=mock_cot_result
        ):
            with pytest.raises(Exception, match="지식 검색 실패"):
                await agent.process(state)

    def test_build_phase_context_all_none(
        self,
        agent_with_stubs: PodcastReasoningAgent,
    ) -> None:
        """_build_phase_context에 user_input만 전달하고 나머지 모두 None일 때 정상 동작 확인."""
        context = agent_with_stubs._build_phase_context(
            phase="CoT",
            user_input="테스트 입력",
            intent={},
            got_result=None,
            tot_result=None,
            memory_result=None,
            knowledge_result=None,
        )

        # user_input은 항상 포함
        assert "[사용자 입력]" in context
        assert "테스트 입력" in context
        # intent가 빈 dict이므로 의도 분류 섹션은 미포함
        assert "[의도 분류]" not in context
        # 나머지 선택 섹션도 미포함
        assert "[과거 에피소드 기억]" not in context
        assert "[관련 전문 지식]" not in context
        assert "[GoT 그래프 분석 결과]" not in context
        assert "[ToT 구조 탐색 결과]" not in context

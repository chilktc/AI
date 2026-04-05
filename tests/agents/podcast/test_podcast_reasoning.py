"""
Podcast Reasoning 에이전트 테스트.

에피소드 구조 설계, DI 기반 조건부 호출(Episode Memory / Knowledge),
복잡도 기반 추론 깊이 라우팅, GoT/ToT/CoT 파이프라인,
하위 호환성 등을 검증한다.

v7 리팩터: 38 → 14 테스트 (parametrize + 중복 삭제)

NOTE: tests/agents/podcast/conftest.py의 got_default_thresholds autouse fixture가
      기본 full_threshold=0.0, standard_threshold=0.0으로 설정한다.
      depth 경계 테스트에서는 명시적으로 원래 threshold를 복원한다.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.podcast.podcast_reasoning import PodcastReasoningAgent
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
    """기본 AgentState — GoT 기본 설정에서 full depth로 동작 (complexity 0.9)."""
    return AgentState(
        user_input="트라우마 이후의 회복과 성장 과정을 깊이 있게 탐구하고 싶어요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "deep_exploration", "complexity_score": 0.9},
    )


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


# === 1. 추론 깊이 라우팅 ===


@pytest.mark.parametrize(
    "complexity, expected_depth",
    [
        pytest.param(0.0, "minimal", id="zero"),
        pytest.param(0.3, "minimal", id="low"),
        pytest.param(0.49, "minimal", id="below_standard"),
        pytest.param(0.5, "standard", id="boundary_standard"),
        pytest.param(0.6, "standard", id="medium"),
        pytest.param(0.79, "standard", id="below_full"),
        pytest.param(0.8, "full", id="boundary_full"),
        pytest.param(0.9, "full", id="high"),
        pytest.param(1.0, "full", id="max"),
    ],
)
def test_reasoning_depth_routing(
    agent_with_stubs: PodcastReasoningAgent,
    complexity: float,
    expected_depth: str,
) -> None:
    """complexity_score 기반 추론 깊이 결정 (원래 threshold 사용)."""
    # autouse GoT fixture 오버라이드: 원래 threshold로 복원
    agent_with_stubs.full_threshold = 0.8
    agent_with_stubs.standard_threshold = 0.5
    assert agent_with_stubs._determine_reasoning_depth(complexity) == expected_depth


# === 2. full/minimal 파이프라인 LLM 호출 수 ===


@pytest.mark.asyncio
async def test_pipeline_llm_call_count(
    agent: PodcastReasoningAgent,
    base_state: AgentState,
    mock_got_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    mock_cot_result: dict[str, Any],
) -> None:
    """full(3회) + minimal(1회) 파이프라인 LLM 호출 수 확인."""
    # full depth (complexity=0.9, base_state)
    mock_full = AsyncMock(side_effect=[mock_got_result, mock_tot_result, mock_cot_result])
    with patch.object(agent, "call_llm_json", mock_full):
        result_full = await agent.process(base_state)

    assert mock_full.call_count == 3
    assert result_full["reasoning_result"]["reasoning_depth"] == "full"
    assert result_full["reasoning_result"]["reasoning_strategy"] == "GoT+ToT+CoT"
    assert "got_result" in result_full["reasoning_result"]
    assert "tot_result" in result_full["reasoning_result"]

    # minimal depth (complexity=0.3)
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5
    state_min = AgentState(
        user_input="오늘 하루 어떻게 보냈는지 이야기해볼게요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "daily_reflection", "complexity_score": 0.3},
    )
    mock_min = AsyncMock(return_value=mock_cot_result)
    with patch.object(agent, "call_llm_json", mock_min):
        result_min = await agent.process(state_min)

    assert mock_min.call_count == 1
    assert result_min["reasoning_result"]["reasoning_depth"] == "minimal"
    assert result_min["reasoning_result"]["reasoning_strategy"] == "CoT"
    assert "got_result" not in result_min["reasoning_result"]
    assert "tot_result" not in result_min["reasoning_result"]


# === 4. DI 호출 라우팅 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "complexity, expect_memory, expect_knowledge",
    [
        pytest.param(0.3, False, False, id="low_skips_both"),
        pytest.param(0.55, False, True, id="mid_calls_knowledge_only"),
        pytest.param(0.65, True, True, id="high_calls_both"),
    ],
)
async def test_di_call_routing(
    mock_memory: AsyncMock,
    mock_knowledge: AsyncMock,
    mock_cot_result: dict[str, Any],
    mock_got_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    complexity: float,
    expect_memory: bool,
    expect_knowledge: bool,
) -> None:
    """complexity에 따라 DI 에이전트(Memory/Knowledge) 호출 여부가 결정된다."""
    agent = PodcastReasoningAgent(
        episode_memory=mock_memory,
        knowledge_agent=mock_knowledge,
    )
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5

    state = AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "test", "complexity_score": complexity},
    )
    side_effect = (
        [mock_got_result, mock_tot_result, mock_cot_result]
        if complexity >= 0.8
        else [mock_tot_result, mock_cot_result] if complexity >= 0.5 else [mock_cot_result]
    )
    with patch.object(agent, "call_llm_json", AsyncMock(side_effect=side_effect)):
        await agent.process(state)

    if expect_memory:
        mock_memory.search.assert_called_once()
    else:
        mock_memory.search.assert_not_called()
    if expect_knowledge:
        mock_knowledge.search.assert_called_once()
    else:
        mock_knowledge.search.assert_not_called()


# === 5. execution_plan 강제 호출 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "plan_key, check_mock",
    [
        pytest.param("needs_memory", "mock_memory", id="force_memory"),
        pytest.param("needs_knowledge", "mock_knowledge", id="force_knowledge"),
    ],
)
async def test_execution_plan_forces_di_call(
    mock_memory: AsyncMock,
    mock_knowledge: AsyncMock,
    mock_cot_result: dict[str, Any],
    plan_key: str,
    check_mock: str,
) -> None:
    """execution_plan의 needs_memory/needs_knowledge가 복잡도 무관하게 호출을 트리거."""
    agent = PodcastReasoningAgent(
        episode_memory=mock_memory,
        knowledge_agent=mock_knowledge,
    )
    state = AgentState(
        user_input="테스트 입력",
        user_id="test_user",
        session_id="sess_test",
        mode="podcast",
        intent={"complexity_score": 0.1},
        execution_plan={plan_key: True},
    )
    with patch.object(agent, "call_llm_json", AsyncMock(return_value=mock_cot_result)):
        await agent.process(state)

    target = mock_memory if check_mock == "mock_memory" else mock_knowledge
    target.search.assert_called_once()


# === 6. DI 주입 패턴 ===


@pytest.mark.parametrize(
    "use_stubs",
    [
        pytest.param(True, id="default_stubs"),
        pytest.param(False, id="custom_agents"),
    ],
)
def test_di_injection(
    mock_memory: AsyncMock,
    mock_knowledge: AsyncMock,
    use_stubs: bool,
) -> None:
    """DI 인자 없이 생성하면 stub, 있으면 커스텀 에이전트가 주입된다."""
    if use_stubs:
        agent = PodcastReasoningAgent()
        assert isinstance(agent.episode_memory, EpisodeMemoryStub)
        assert isinstance(agent.knowledge_agent, KnowledgeAgentStub)
    else:
        agent = PodcastReasoningAgent(
            episode_memory=mock_memory,
            knowledge_agent=mock_knowledge,
        )
        assert agent.episode_memory is mock_memory
        assert agent.knowledge_agent is mock_knowledge


# === 7. GoT/ToT/CoT 단위 테스트 ===


@pytest.mark.asyncio
async def test_got_tot_cot_structure_and_context(
    agent: PodcastReasoningAgent,
    mock_got_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    mock_cot_result: dict[str, Any],
) -> None:
    """GoT/ToT/CoT 각각의 필수 필드 + 프롬프트 컨텍스트 포함을 검증한다."""

    def _get_user_message(m: AsyncMock) -> str:
        return m.call_args.kwargs.get(
            "user_message", m.call_args.args[1] if len(m.call_args.args) > 1 else ""
        )

    # GoT
    mock_g = AsyncMock(return_value=mock_got_result)
    with patch.object(agent, "call_llm_json", mock_g):
        got = await agent._graph_of_thoughts(
            user_input="스트레스 관리",
            intent={"primary_intent": "coping", "complexity_score": 0.9},
            memory_result=None,
            knowledge_result=None,
        )
    assert "core_pattern" in got and "nodes" in got and "edges" in got
    assert "스트레스 관리" in _get_user_message(mock_g)
    assert "coping" in _get_user_message(mock_g)

    # ToT
    mock_t = AsyncMock(return_value=mock_tot_result)
    with patch.object(agent, "call_llm_json", mock_t):
        tot = await agent._tree_of_thoughts(
            user_input="스트레스 관리",
            intent={"primary_intent": "coping"},
            got_result=mock_got_result,
            memory_result=None,
            knowledge_result=None,
        )
    assert "alternatives" in tot and "selected" in tot
    assert "GoT 그래프 분석 결과" in _get_user_message(mock_t)

    # CoT
    mock_c = AsyncMock(return_value=mock_cot_result)
    with patch.object(agent, "call_llm_json", mock_c):
        cot = await agent._chain_of_thoughts(
            user_input="스트레스 관리",
            intent={"primary_intent": "coping"},
            got_result=None,
            tot_result=mock_tot_result,
            memory_result=None,
            knowledge_result=None,
        )
    assert "episode_structure" in cot and "narrative_flow" in cot and "confidence" in cot
    assert "ToT 구조 탐색 결과" in _get_user_message(mock_c)


# === 10. 하위 호환성 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "depth_label, complexity, llm_calls, has_got, has_tot",
    [
        pytest.param("minimal", 0.3, 1, False, False, id="minimal"),
        pytest.param("full", 0.9, 3, True, True, id="full"),
    ],
)
async def test_legacy_fields_present(
    agent: PodcastReasoningAgent,
    mock_got_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    mock_cot_result: dict[str, Any],
    depth_label: str,
    complexity: float,
    llm_calls: int,
    has_got: bool,
    has_tot: bool,
) -> None:
    """모든 depth에서 기존 필드(episode_structure, narrative_flow 등)가 존재한다."""
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5
    state = AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "test", "complexity_score": complexity},
    )
    effects = [mock_got_result, mock_tot_result, mock_cot_result][:llm_calls]
    with patch.object(agent, "call_llm_json", AsyncMock(side_effect=effects)):
        result = await agent.process(state)

    reasoning = result["reasoning_result"]
    for field in (
        "episode_structure",
        "narrative_flow",
        "key_points",
        "emotional_journey",
        "confidence",
    ):
        assert field in reasoning, f"Missing legacy field: {field}"
    assert reasoning["reasoning_depth"] == depth_label
    assert ("got_result" in reasoning) == has_got
    assert ("tot_result" in reasoning) == has_tot


# === 11. 엣지 케이스: 빈 입력 / 누락 intent ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input, has_intent, expected_depth",
    [
        pytest.param("", True, "minimal", id="empty_input"),
        pytest.param("테스트 입력", False, "standard", id="missing_intent"),
    ],
)
async def test_edge_case_inputs(
    agent: PodcastReasoningAgent,
    mock_cot_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    user_input: str,
    has_intent: bool,
    expected_depth: str,
) -> None:
    """빈 입력 또는 intent 누락 시 기본값으로 처리된다."""
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5
    state_data: dict[str, Any] = {
        "user_input": user_input,
        "user_id": "test_user_001",
        "session_id": "sess_test_001",
        "mode": "podcast",
    }
    if has_intent:
        state_data["intent"] = {"primary_intent": "unknown", "complexity_score": 0.3}
    state = AgentState(**state_data)

    effects = (
        [mock_tot_result, mock_cot_result] if expected_depth == "standard" else [mock_cot_result]
    )
    with patch.object(agent, "call_llm_json", AsyncMock(side_effect=effects)):
        result = await agent.process(state)

    assert "reasoning_result" in result
    assert result["reasoning_result"]["reasoning_depth"] == expected_depth


# === 12. LLM이 빈 dict 반환 ===


@pytest.mark.asyncio
async def test_llm_returns_empty_dict(
    agent: PodcastReasoningAgent,
) -> None:
    """call_llm_json이 {}를 반환해도 필수 메타데이터 필드가 존재한다."""
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5
    state = AgentState(
        user_input="테스트",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "test", "complexity_score": 0.3},
    )
    with patch.object(agent, "call_llm_json", AsyncMock(return_value={})):
        result = await agent.process(state)

    reasoning = result["reasoning_result"]
    assert reasoning["reasoning_depth"] == "minimal"
    assert reasoning["reasoning_strategy"] == "CoT"
    assert reasoning["episode_structure"] == []
    assert reasoning["confidence"] == 0.0


# === 13. DI 예외 전파 ===


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failing_agent, error_msg",
    [
        pytest.param("memory", "메모리 검색 실패", id="memory_exception"),
        pytest.param("knowledge", "지식 검색 실패", id="knowledge_exception"),
    ],
)
async def test_di_exception_propagation(
    mock_memory: AsyncMock,
    mock_knowledge: AsyncMock,
    mock_cot_result: dict[str, Any],
    mock_tot_result: dict[str, Any],
    failing_agent: str,
    error_msg: str,
) -> None:
    """DI 에이전트에서 예외 발생 시 그대로 전파된다."""
    if failing_agent == "memory":
        mock_memory.search.side_effect = Exception(error_msg)
    else:
        mock_knowledge.search.side_effect = Exception(error_msg)

    agent = PodcastReasoningAgent(
        episode_memory=mock_memory,
        knowledge_agent=mock_knowledge,
    )
    agent.full_threshold = 0.8
    agent.standard_threshold = 0.5

    state = AgentState(
        user_input="테스트 입력",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="podcast",
        intent={"primary_intent": "test", "complexity_score": 0.7},
    )
    with patch.object(
        agent, "call_llm_json", AsyncMock(side_effect=[mock_tot_result, mock_cot_result])
    ):
        with pytest.raises(Exception, match=error_msg):
            await agent.process(state)


# === 14. _build_phase_context all None ===


def test_build_phase_context_all_none(agent_with_stubs: PodcastReasoningAgent) -> None:
    """_build_phase_context에 user_input만 전달하고 나머지 모두 None일 때 정상 동작."""
    context = agent_with_stubs._build_phase_context(
        phase="CoT",
        user_input="테스트 입력",
        intent={},
        got_result=None,
        tot_result=None,
        memory_result=None,
        knowledge_result=None,
    )
    assert "[사용자 입력]" in context
    assert "테스트 입력" in context
    assert "[의도 분류]" not in context
    assert "[과거 에피소드 기억]" not in context
    assert "[GoT 그래프 분석 결과]" not in context


# ===================================================================
# Neo4j 저장 + Backend 전송 테스트
# ===================================================================


_SAMPLE_GOT_RESULT: dict[str, Any] = {
    "nodes": [
        {
            "id": 1,
            "label": "업무 과부하",
            "type": "concept",
            "group": "work_structure",
            "intensity": 0.8,
        },
        {
            "id": 2,
            "label": "상사 갈등",
            "type": "concept",
            "group": "leadership",
            "intensity": 0.6,
        },
    ],
    "edges": [
        {"from": 1, "to": 2, "relationship": "causes"},
    ],
}


def _patch_create_graph_client(**kwargs):
    """지연 임포트(src.db.factory)를 안전하게 patch하는 헬퍼.

    test_graph_routes.py가 sys.modules에 src.db를 mock으로 등록하면
    patch("src.db.factory.create_graph_client")가 실패한다.
    builtins.__import__를 가로채서 지연 임포트 시점에 mock을 주입한다.
    """
    import builtins

    real_import = builtins.__import__
    mock_fn = MagicMock(**kwargs)

    def _fake_import(name, *args, **kw):
        if name == "src.db.factory":
            mod = MagicMock()
            mod.create_graph_client = mock_fn
            return mod
        return real_import(name, *args, **kw)

    return patch.object(builtins, "__import__", side_effect=_fake_import), mock_fn


class TestSaveGotToNeo4j:
    @pytest.mark.asyncio
    async def test_normal_save(self, agent: PodcastReasoningAgent) -> None:
        mock_client = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        import_patch, mock_fn = _patch_create_graph_client(return_value=mock_cm)
        with import_patch:
            await agent._save_got_to_neo4j(_SAMPLE_GOT_RESULT, "sess_001", "ep_001")

        # 2 노드 MERGE + 1 엣지 MERGE + 1 Session 관계 = 4 호출
        assert mock_client.execute_query.call_count == 4

    @pytest.mark.asyncio
    async def test_empty_episode_id_skips(self, agent: PodcastReasoningAgent) -> None:
        import_patch, mock_factory = _patch_create_graph_client()
        with import_patch:
            await agent._save_got_to_neo4j(_SAMPLE_GOT_RESULT, "sess_001", "")
            mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_neo4j_failure_graceful(self, agent: PodcastReasoningAgent) -> None:
        import_patch, _ = _patch_create_graph_client(
            side_effect=Exception("Neo4j down"),
        )
        with import_patch:
            # 예외가 전파되지 않음 (graceful degradation)
            await agent._save_got_to_neo4j(_SAMPLE_GOT_RESULT, "sess_001", "ep_001")


class TestPublishGraphToBackend:
    @pytest.mark.asyncio
    async def test_normal_publish(self, agent: PodcastReasoningAgent) -> None:
        mock_publisher = AsyncMock()
        state: AgentState = {"user_id": "user_001", "session_id": "sess_001"}

        with patch(
            "src.api.publisher.AgentDataPublisher",
            return_value=mock_publisher,
        ):
            await agent._publish_graph_to_backend(_SAMPLE_GOT_RESULT, state)

        mock_publisher.publish.assert_called_once()
        call_kwargs = mock_publisher.publish.call_args
        assert call_kwargs.kwargs.get("user_id") == "user_001"

    @pytest.mark.asyncio
    async def test_publish_failure_graceful(self, agent: PodcastReasoningAgent) -> None:
        state: AgentState = {"user_id": "user_001", "session_id": "sess_001"}

        with patch(
            "src.api.publisher.AgentDataPublisher",
            side_effect=Exception("Backend unreachable"),
        ):
            await agent._publish_graph_to_backend(_SAMPLE_GOT_RESULT, state)


class TestSaveGraphData:
    @pytest.mark.asyncio
    async def test_calls_both_methods(self, agent: PodcastReasoningAgent) -> None:
        state: AgentState = {"user_id": "user_001", "session_id": "sess_001"}

        with (
            patch.object(agent, "_save_got_to_neo4j", new_callable=AsyncMock) as mock_neo4j,
            patch.object(
                agent,
                "_publish_graph_to_backend",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await agent._save_graph_data(_SAMPLE_GOT_RESULT, "sess_001", "ep_001", state)

        mock_neo4j.assert_called_once_with(_SAMPLE_GOT_RESULT, "sess_001", "ep_001")
        mock_publish.assert_called_once_with(_SAMPLE_GOT_RESULT, state)

# 에이전트 개발 가이드

Mind-Log 에이전트를 구현할 때 참고하는 실무 가이드입니다.
기본 개념은 `../getting-started/QUICK_START.md`, 아키텍처 전체는 `CLAUDE.md`를 참조하세요.

---

## 1. 구현 체크리스트

새 에이전트를 구현할 때 아래 순서를 따릅니다:

- [ ] **BaseAgent 상속** + `__init__(name, tier)` 설정
- [ ] **`process(state: AgentState) -> dict[str, Any]`** 구현 — 자기 담당 필드만 반환
- [ ] **모듈 하단** 노드 함수 작성 (요청별 인스턴스 생성 패턴)
- [ ] **프롬프트 YAML** 작성: `prompts/{mode}/{name}.yaml`
- [ ] **테스트** 작성: `tests/agents/{mode}/test_{name}.py`
- [ ] **workflow.py stub 교체** (→ 섹션 6 참조)

---

## 2. 에이전트 기본 템플릿

### 단일 프롬프트 에이전트

대부분의 에이전트는 이 패턴을 따릅니다.

```python
"""
Context Agent — 대화 맥락 분석.

TIER 1 (병렬) | 모델: Haiku
담당: 개발자3
"""
from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.models.agent_state import AgentState


class ContextAgent(BaseAgent):
    """대화 맥락을 분석하여 주제, 흐름, 참여도를 판단한다."""

    def __init__(self) -> None:
        super().__init__(name="context", tier=1)
        # BaseAgent.__init__이 자동으로 수행:
        #   - LLMClient 초기화 (settings.yaml 기반 모델/프로바이더 자동 결정)
        #   - PromptLoader로 prompts/{mode}/{name}.yaml 프롬프트 자동 로딩
        #   - A/B 테스트 설정 로딩 (settings.yaml prompts.ab_tests 참조)

    async def process(self, state: AgentState) -> dict[str, Any]:
        user_input = state["user_input"]

        # call_llm_json: JSON 응답 + LLM 호출 횟수 자동 추적
        # call_llm: 텍스트 응답 + LLM 호출 횟수 자동 추적
        # get_prompt("키"): 자동 로딩된 프롬프트에서 키로 조회
        result = await self.call_llm_json(
            system_message=self.get_prompt("system_prompt"),
            user_message=user_input,
        )

        return {"context": result}


# --- 노드 함수 (요청별 인스턴스 생성) ---
async def context_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Context Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = ContextAgent()
    return await agent(state)
```

### 다중 프롬프트(GoT/ToT/CoT) 에이전트

Reasoning 계열은 여러 프롬프트를 순차적으로 호출합니다.

```python
"""
Reasoning Agent — 다단계 추론 (GoT → ToT → CoT).

TIER 1 (병렬) | 모델: Opus 4.6
담당: 개발자3
"""
from __future__ import annotations

from typing import Any

from src.agents.shared.base_agent import BaseAgent
from src.agents.shared.stubs import KnowledgeAgentStub, MemoryAgentStub
from src.models.agent_state import AgentState


class ReasoningAgent(BaseAgent):
    """GoT/ToT/CoT 기반 다단계 추론을 수행한다."""

    def __init__(
        self,
        memory_agent: MemoryAgentStub | None = None,
        knowledge_agent: KnowledgeAgentStub | None = None,
    ) -> None:
        super().__init__(name="reasoning", tier=1)
        self._memory = memory_agent or MemoryAgentStub()
        self._knowledge = knowledge_agent or KnowledgeAgentStub()

    async def process(self, state: AgentState) -> dict[str, Any]:
        user_input = state["user_input"]
        complexity = state.get("intent", {}).get("complexity_score", 0.5)

        # 추론 깊이 결정 (룰 기반)
        if complexity > 0.8:
            depth = "full"      # GoT → ToT → CoT
        elif complexity > 0.6:
            depth = "standard"  # ToT → CoT
        else:
            depth = "minimal"   # CoT only

        result: dict[str, Any] = {}

        # GoT (full 전용)
        if depth == "full":
            got = await self.call_llm_json(
                system_message=self.get_prompt("got"),  # 다중 프롬프트 키
                user_message=user_input,
            )
            result["got_result"] = got

        # ToT (standard 이상)
        if depth in ("full", "standard"):
            tot = await self.call_llm_json(
                system_message=self.get_prompt("tot"),
                user_message=user_input,
            )
            result["tot_result"] = tot

        # CoT (항상 실행)
        cot = await self.call_llm_json(
            system_message=self.get_prompt("cot"),
            user_message=user_input,
        )
        result["cot_result"] = cot

        return {"reasoning_result": result}


# --- 노드 함수 (요청별 인스턴스 생성) ---
async def reasoning_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Reasoning Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = ReasoningAgent()
    return await agent(state)
```

### 독립 에이전트 (DI — 의존성 주입)

Memory/Knowledge/EpisodeMemory는 Reasoning 계열에서 조건부 호출됩니다.
StateGraph 노드가 아닌 **독립 에이전트**로 DI 패턴을 따릅니다.

```python
# Reasoning Agent 생성 시 독립 에이전트 주입
from src.agents.conversation.memory import MemoryAgent
from src.agents.conversation.knowledge import KnowledgeAgent

reasoning = ReasoningAgent(
    memory_agent=MemoryAgent(),       # 실제 구현
    knowledge_agent=KnowledgeAgent(), # 실제 구현
)

# 또는 stub으로 테스트
from src.agents.shared.stubs import MemoryAgentStub, KnowledgeAgentStub

reasoning = ReasoningAgent(
    memory_agent=MemoryAgentStub(),
    knowledge_agent=KnowledgeAgentStub(),
)
```

---

## 3. 프롬프트 YAML 작성법

### 디렉토리 구조

```
prompts/
├── podcast/         # 팟캐스트모드 전용
├── conversation/    # 대화모드 전용
└── shared/          # 공용 에이전트 (양쪽 모드)
```

`BaseAgent._resolve_mode()`가 모듈 경로에서 모드를 자동 추론합니다:
- `src/agents/podcast/*.py` → `prompts/podcast/`
- `src/agents/conversation/*.py` → `prompts/conversation/`
- `src/agents/shared/*.py` → `prompts/shared/`

### 단일 프롬프트 형식

```yaml
version: "1.0.0"
system_prompt: |
  당신은 ...

  ## 분석 항목
  1. ...

  ## 응답 형식 (JSON)
  {...}
```

### 멀티버전 프롬프트 형식

`default_version` + `versions` 딕셔너리로 여러 버전을 관리합니다.
`settings.yaml`에서 에이전트별 버전을 핀닝합니다.

```yaml
# prompts/podcast/content_analyzer.yaml
default_version: "2.1.0"
versions:
  "2.1.0":
    system_prompt: |
      (시스템 프롬프트)
```

### 다중 프롬프트 형식 (GoT/ToT/CoT)

```yaml
default_version: "3.0.0"
versions:
  "3.0.0":
    prompts:
      got:
        system_prompt: |
          (GoT 프롬프트)
      tot:
        system_prompt: |
          (ToT 프롬프트)
      cot:
        system_prompt: |
          (CoT 프롬프트)
```

> 이전 버전은 `prompts/{mode}/_archive/` 폴더에 보존되어 있습니다.
> 버전 관리 상세는 `PROMPT_VERSIONING.md`를 참조하세요.

### 코드에서 프롬프트 호출

```python
# 단일 프롬프트
prompt = self.get_prompt("system_prompt")

# 다중 프롬프트 — 키 이름으로 접근
got_prompt = self.get_prompt("got")
tot_prompt = self.get_prompt("tot")
cot_prompt = self.get_prompt("cot")
```

### A/B 테스트 설정

`config/settings.yaml`에서 에이전트별 A/B 설정:

```yaml
agents:
  content_analyzer:
    model: sonnet
    prompt_version: "1.0.0"
    ab_test:
      enabled: true
      variants: ["v1", "v2"]
      weights: [0.5, 0.5]
```

YAML 파일에 멀티버전 추가:

```yaml
version: "1.0.0"
versions:
  v1:
    system_prompt: |
      (버전 1 프롬프트)
  v2:
    system_prompt: |
      (버전 2 프롬프트)
```

### 보안 참고

`prompts/` 디렉토리는 `.gitignore`에 포함되어 있습니다.
프롬프트 내용은 Notion을 통해 팀 간 공유합니다.

---

## 4. 테스트 작성 패턴

### LLM 호출 Mock

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_process_returns_expected_field(
    agent: ContextAgent,
    base_state: AgentState,
) -> None:
    """process()가 context 필드를 반환하는지 확인."""
    mock_response = {"current_topic": "직장 스트레스", "user_engagement": "high"}

    with patch.object(
        agent, "call_llm_json",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await agent.process(base_state)

    assert "context" in result
    assert result["context"]["current_topic"] == "직장 스트레스"
```

### AgentState Fixture

```python
@pytest.fixture
def base_state() -> AgentState:
    """기본 AgentState — 최소 필수 필드."""
    return AgentState(
        user_input="요즘 스트레스를 많이 받아요.",
        user_id="test_user_001",
        session_id="sess_test_001",
        mode="conversation",
    )
```

### 필드 격리 검증

에이전트는 자기 담당 필드만 반환해야 합니다:

```python
async def test_only_returns_own_field(agent, base_state):
    """다른 에이전트 필드를 반환하지 않는지 확인."""
    with patch.object(agent, "call_llm_json", new_callable=AsyncMock, return_value={}):
        result = await agent.process(base_state)

    assert list(result.keys()) == ["context"]  # 자기 필드만
```

### 엣지케이스 체크리스트

- [ ] 빈 `user_input`에서 에러 없이 동작
- [ ] 매우 긴 입력(2000자+)에서 정상 동작
- [ ] `mode` 필드가 없을 때 기본값 처리
- [ ] LLM이 빈 응답 반환 시 처리
- [ ] LLM 호출 실패 시 예외 전파 여부

---

## 5. 공용 에이전트 모드 분기 패턴

Safety, Emotion 등은 대화모드와 팟캐스트모드 모두에서 사용됩니다.

### `state["mode"]` 기반 분기

```python
class SafetyAgent(BaseAgent):
    async def process(self, state: AgentState) -> dict[str, Any]:
        mode = state.get("mode", "conversation")

        if mode == "podcast":
            # 팟캐스트 특화 안전 검사
            ...
        else:
            # 대화모드 안전 검사
            ...
```

### 프롬프트 디렉토리

공용 에이전트는 `prompts/shared/`에 YAML을 배치합니다:

```
prompts/shared/safety.yaml     ← 공용 Safety Agent
prompts/shared/emotion.yaml    ← 공용 Emotion Agent
```

`BaseAgent._resolve_mode()`가 `src/agents/shared/` 경로를 감지하면
자동으로 `prompts/shared/`에서 프롬프트를 로드합니다.

---

## 6. workflow.py 노드 등록 방법

> 워크플로우 노드 등록 규칙과 인터페이스는 [CLAUDE.md](../CLAUDE.md#langgraph-워크플로우)를 참조하세요.
> `workflow.py`는 Protected File이므로 수정 시 3인 합의가 필요합니다.

---

## 7. 참고 구현 예시

이미 구현된 에이전트를 참고하세요:

| 파일 | 패턴 | 특징 |
|------|------|------|
| `src/agents/podcast/content_analyzer.py` | 단일 프롬프트 + 전후처리 | 기본 패턴의 완전한 예시 |
| `src/agents/podcast/podcast_reasoning.py` | 다중 프롬프트 + DI + 추론 깊이 라우팅 | GoT/ToT/CoT 다단계 추론 |
| `src/agents/podcast/batch_validator.py` | TIER 3 검증 + `next_step` 라우팅 | 재시도 루프 연동 |
| `src/agents/shared/learning.py` | 공용(shared) + 백엔드 API 연동 | 비동기 + API client |

### 테스트 참고

| 파일 | 패턴 |
|------|------|
| `tests/agents/podcast/test_content_analyzer.py` | 단일 에이전트 전체 테스트 |
| `tests/agents/podcast/test_podcast_reasoning.py` | DI mock + 다중 프롬프트 |
| `tests/agents/podcast/test_batch_validator.py` | 통과/실패/재시도 시나리오 |
| `tests/integration/test_crisis_preemption.py` | CRISIS 선점 통합 테스트 |
| `tests/integration/test_retry_loop.py` | 재시도 루프 + 라우터 |

---

## 8. 공용 유틸리티 (context_utils)

에이전트 구현 시 반복되는 패턴을 통합한 유틸리티 모듈.
위치: `src/agents/shared/context_utils.py`

### build_section(label, data, keys)

dict에서 지정된 키를 추출하여 LLM 컨텍스트 섹션으로 포맷한다.

```python
from src.agents.shared.context_utils import build_section

# 감정 분석 결과를 컨텍스트로 변환
section = build_section("감정 분석", emotion_vectors, keys=["primary_emotion", "intensity"])
# 결과: "[감정 분석]\n- primary_emotion: 불안\n- intensity: 0.8"
```

### build_context(*sections)

비어있지 않은 섹션들을 `\n\n`으로 결합한다.

```python
from src.agents.shared.context_utils import build_context, build_section

context = build_context(
    build_section("감정 분석", emotion_vectors),
    build_section("콘텐츠 분석", content_analysis, keys=["main_theme", "depth_level"]),
)
```

### clamp(value, lo, hi, default)

숫자 값을 범위 내로 제한한다. 타입 변환 실패 시 default를 반환.

```python
from src.agents.shared.context_utils import clamp

intensity = clamp(raw_intensity, 0.0, 1.0, default=0.5)
duration = clamp(target_duration, min_duration, max_duration)
```

### BaseAgent._load_agent_config(defaults)

`settings.yaml`에서 에이전트별 설정을 로드하고 기본값과 병합한다.
각 에이전트의 `_load_config()`에서 호출.

```python
def _load_config(self) -> None:
    cfg = self._load_agent_config({
        "full_threshold": 0.8,
        "standard_threshold": 0.5,
    })
    self.full_threshold = cfg["full_threshold"]
    self.standard_threshold = cfg["standard_threshold"]
```

---

*마지막 업데이트: 2026-03-24*

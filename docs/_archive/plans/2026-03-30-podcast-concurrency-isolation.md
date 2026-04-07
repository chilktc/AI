# 팟캐스트모드 동시 요청 격리 구현 계획

> **상태: 구현 완료 (2026-03-30)**. 전체 6개 Task 완료, 298 테스트 통과 확인.
> 추가로 `test_retry_then_pass` fixture (계획에 미포함)도 노드 함수 패치로 수정됨.

**Goal:** 팟캐스트 파이프라인의 10개 에이전트 싱글톤을 요청별 인스턴스로 전환하여, 100명 동시 요청에서도 개인정보가 절대 섞이지 않도록 한다.

**Architecture:** 모듈 레벨 싱글톤을 제거하고 노드 함수 내부에서 에이전트를 생성한다. base_agent.py에서 중복 인스턴스 변수(`_current_ab_variant`)를 ContextVar로 일원화하고, llm_client.py에서 `last_usage` 프로퍼티를 방어적 복사로 변경한다.

**Tech Stack:** Python 3.11+, LangGraph, pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-03-30-podcast-concurrency-isolation-design.md`

---

### Task 1: 개별 에이전트 파일 싱글톤 제거 (7개 파일)

**Files:**
- Modify: `src/agents/podcast/safety.py:70-76`
- Modify: `src/agents/podcast/emotion.py:89-93`
- Modify: `src/agents/podcast/content_analyzer.py:235-241`
- Modify: `src/agents/podcast/podcast_reasoning.py:453-459`
- Modify: `src/agents/podcast/batch_validator.py:241-247`
- Modify: `src/agents/podcast/visualization.py:121-124`
- Modify: `src/agents/shared/learning.py:131-137`

- [ ] **Step 1: safety.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/safety.py`에서 lines 70-76을 다음으로 교체:

```python
async def safety_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Safety Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = SafetyAgent()
    return await agent(state)
```

제거되는 코드:
- `safety_agent = SafetyAgent()` (line 72)
- `# --- 싱글톤 + 노드 래퍼 ---` 주석 (line 70)
- `# 인스턴스 생성 시점에 settings.yaml을 참조하여 llm_client가 초기화됩니다.` 주석 (line 71)

- [ ] **Step 2: emotion.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/emotion.py`에서 lines 89-93을 다음으로 교체:

```python
async def emotion_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Emotion Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = EmotionAgent()
    return await agent(state)
```

제거되는 코드: `emotion_agent = EmotionAgent()` (line 89)

- [ ] **Step 3: content_analyzer.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/content_analyzer.py`에서 lines 235-241을 다음으로 교체:

```python
async def content_analyzer_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Content Analyzer.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = ContentAnalyzerAgent()
    return await agent(state)
```

제거되는 코드:
- `# LangGraph 노드 함수로 사용할 에이전트 인스턴스` 주석 (line 235)
- `content_analyzer_agent = ContentAnalyzerAgent()` (line 236)

- [ ] **Step 4: podcast_reasoning.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/podcast_reasoning.py`에서 lines 453-459을 다음으로 교체:

```python
async def podcast_reasoning_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Podcast Reasoning.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = PodcastReasoningAgent()
    return await agent(state)
```

제거되는 코드:
- `# LangGraph 노드 함수로 사용할 에이전트 인스턴스` 주석 (line 453)
- `podcast_reasoning_agent = PodcastReasoningAgent()` (line 454)

- [ ] **Step 5: batch_validator.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/batch_validator.py`에서 lines 241-247을 다음으로 교체:

```python
async def batch_validator_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Batch Validator.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = BatchValidatorAgent()
    return await agent(state)
```

제거되는 코드:
- `# LangGraph 노드 함수로 사용할 에이전트 인스턴스` 주석 (line 241)
- `batch_validator_agent = BatchValidatorAgent()` (line 242)

- [ ] **Step 6: visualization.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/podcast/visualization.py`에서 lines 121-124를 다음으로 교체:

```python
async def visualization_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Visualization Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = VisualizationAgent()
    return await agent(state)
```

제거되는 코드:
- `# --- 노드 래퍼 ---` 주석 (line 121)
- `visualization_agent = VisualizationAgent()` (line 122)

- [ ] **Step 7: learning.py — 싱글톤 제거, 노드 함수 내부 생성**

`src/agents/shared/learning.py`에서 lines 131-137을 다음으로 교체:

```python
async def learning_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Learning Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = LearningAgent()
    return await agent(state)
```

제거되는 코드:
- `# LangGraph 노드 함수로 사용할 에이전트 인스턴스` 주석 (line 131)
- `learning_agent = LearningAgent()` (line 132)

- [ ] **Step 8: 테스트 실행**

Run: `pytest tests/agents/ -v --timeout=30`
Expected: PASS (단위 테스트는 에이전트를 직접 생성하므로 영향 없음)

- [ ] **Step 9: 커밋**

```bash
git add src/agents/podcast/safety.py src/agents/podcast/emotion.py src/agents/podcast/content_analyzer.py src/agents/podcast/podcast_reasoning.py src/agents/podcast/batch_validator.py src/agents/podcast/visualization.py src/agents/shared/learning.py
git commit -m "refactor: 7개 에이전트 싱글톤 제거, 노드 함수 내부 인스턴스 생성으로 전환"
```

---

### Task 2: workflow.py 싱글톤 제거 + reset_agents 삭제

**Files:**
- Modify: `src/graph/workflow.py:89-177`

- [ ] **Step 1: 3개 싱글톤 변수 제거 + 노드 함수 변경**

`src/graph/workflow.py`에서 lines 89-95를 다음으로 교체:

```python
# --- TIER 0 (개발자1) ---


async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """Intent Classifier 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = IntentClassifierAgent()
    return await agent.process(state)
```

제거되는 코드: `_intent_classifier = IntentClassifierAgent()` (line 90)

- [ ] **Step 2: script_generator 싱글톤 제거**

`src/graph/workflow.py`에서 lines 98-104를 다음으로 교체:

```python
# --- TIER 2 팟캐스트모드 (개발자1) ---


async def script_generator_node(state: AgentState) -> dict[str, Any]:
    """Script Generator 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = ScriptGeneratorAgent()
    return await agent.process(state)
```

제거되는 코드: `_script_generator = ScriptGeneratorAgent()` (line 99)

- [ ] **Step 3: script_personalizer 싱글톤 제거 + reset_agents 삭제**

`src/graph/workflow.py`에서 lines 155-177을 다음으로 교체:

```python
# --- TIER 4 팟캐스트모드 (개발자1) ---


async def script_personalizer_node(state: AgentState) -> dict[str, Any]:
    """Script Personalizer 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = ScriptPersonalizerAgent()
    return await agent.process(state)
```

제거되는 코드:
- `_script_personalizer = ScriptPersonalizerAgent()` (line 156)
- `reset_agents()` 함수 전체 (lines 159-172)

- [ ] **Step 4: 테스트 실행**

Run: `pytest tests/graph/ tests/integration/ -v --timeout=60`
Expected: `test_e2e_mock_pipeline.py`의 3개 fixture에서 FAIL (싱글톤 참조 제거됨). 나머지 통합 테스트는 PASS.

- [ ] **Step 5: 커밋**

```bash
git add src/graph/workflow.py
git commit -m "refactor: workflow.py 3개 싱글톤 제거 + reset_agents() 삭제"
```

---

### Task 3: 테스트 코드 수정 (싱글톤 패치 → 노드 함수 패치)

**Files:**
- Modify: `tests/graph/test_e2e_mock_pipeline.py:140-231`

- [ ] **Step 1: mock_podcast_nodes fixture 수정**

`tests/graph/test_e2e_mock_pipeline.py`의 `mock_podcast_nodes` fixture (lines 141-169)를 다음으로 교체:

```python
@pytest.fixture
def mock_podcast_nodes(monkeypatch):
    """팟캐스트 모드 전체 파이프라인 노드를 mock 데이터로 패치."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf, "intent_classifier_node",
        AsyncMock(return_value=MOCK_INTENT_PODCAST),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf, "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf, "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )
    monkeypatch.setattr(
        wf, "script_generator_node",
        AsyncMock(return_value=MOCK_SCRIPT_DRAFT),
    )
    monkeypatch.setattr(wf, "batch_validator_node", AsyncMock(return_value=MOCK_BV_PASS))
    monkeypatch.setattr(
        wf, "script_personalizer_node",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_PODCAST),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))
```

변경점: `wf._intent_classifier.process` → `wf.intent_classifier_node`, `wf._script_generator.process` → `wf.script_generator_node`, `wf._script_personalizer.process` → `wf.script_personalizer_node`

- [ ] **Step 2: mock_conversation_nodes fixture 수정**

`tests/graph/test_e2e_mock_pipeline.py`의 `mock_conversation_nodes` fixture (lines 173-196)를 다음으로 교체:

```python
@pytest.fixture
def mock_conversation_nodes(monkeypatch):
    """대화 모드 전체 파이프라인 노드를 mock 데이터로 패치."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf, "intent_classifier_node",
        AsyncMock(return_value=MOCK_INTENT_CONVERSATION),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_SAFE))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(wf, "context_node", AsyncMock(return_value=MOCK_CONTEXT))
    monkeypatch.setattr(
        wf, "reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_CONVERSATION),
    )
    monkeypatch.setattr(wf, "synthesis_node", AsyncMock(return_value=MOCK_SYNTHESIS))
    monkeypatch.setattr(wf, "validator_node", AsyncMock(return_value=MOCK_VALIDATOR_PASS))
    monkeypatch.setattr(
        wf, "personalization_node",
        AsyncMock(return_value=MOCK_FINAL_OUTPUT_CONVERSATION),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))
```

변경점: `wf._intent_classifier.process` → `wf.intent_classifier_node`

- [ ] **Step 3: mock_crisis_nodes fixture 수정**

`tests/graph/test_e2e_mock_pipeline.py`의 `mock_crisis_nodes` fixture (lines 199-231)를 다음으로 교체:

```python
@pytest.fixture
def mock_crisis_nodes(monkeypatch):
    """CRISIS 시나리오 노드 mock."""
    import src.graph.workflow as wf

    monkeypatch.setattr(
        wf, "intent_classifier_node",
        AsyncMock(return_value=MOCK_INTENT_CRISIS),
    )
    monkeypatch.setattr(wf, "safety_node", AsyncMock(return_value=MOCK_SAFETY_CRISIS))
    monkeypatch.setattr(wf, "emotion_node", AsyncMock(return_value=MOCK_EMOTION))
    monkeypatch.setattr(
        wf, "content_analyzer_node",
        AsyncMock(return_value=MOCK_CONTENT_ANALYSIS),
    )
    monkeypatch.setattr(
        wf, "podcast_reasoning_node",
        AsyncMock(return_value=MOCK_REASONING_PODCAST),
    )
    monkeypatch.setattr(
        wf, "script_generator_node",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 2는 실행되면 안 됨")),
    )
    monkeypatch.setattr(
        wf, "batch_validator_node",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 3는 실행되면 안 됨")),
    )
    monkeypatch.setattr(
        wf, "script_personalizer_node",
        AsyncMock(side_effect=AssertionError("CRISIS 시 TIER 4는 실행되면 안 됨")),
    )
    monkeypatch.setattr(wf, "visualization_node", AsyncMock(return_value=MOCK_VISUALIZATION))
    monkeypatch.setattr(wf, "learning_node", AsyncMock(return_value={}))
```

변경점: `wf._intent_classifier.process` → `wf.intent_classifier_node`, `wf._script_generator.process` → `wf.script_generator_node`, `wf._script_personalizer.process` → `wf.script_personalizer_node`

- [ ] **Step 4: 테스트 실행**

Run: `pytest tests/graph/test_e2e_mock_pipeline.py -v --timeout=60`
Expected: PASS (모든 fixture가 노드 함수명으로 패치)

- [ ] **Step 5: 전체 테스트 실행 (Task 1~3 통합 검증)**

Run: `pytest tests/ -v --timeout=120`
Expected: PASS. 실패 시 구현 의도를 확인하고, 테스트가 제거된 싱글톤에 의존하면 테스트를 수정한다.

- [ ] **Step 6: 커밋**

```bash
git add tests/graph/test_e2e_mock_pipeline.py
git commit -m "test: E2E mock 테스트를 노드 함수 패치 방식으로 전환"
```

---

### Task 4: base_agent.py — `_current_ab_variant` 제거 + 동시성 주석

**Files:**
- Modify: `src/agents/shared/base_agent.py:78-116, 299-308, 373-426, 454, 770`

- [ ] **Step 1: `__init__`에서 `_current_ab_variant` 제거 + 동시성 주석 추가**

`src/agents/shared/base_agent.py`의 class docstring에 동시성 주석을 추가한다. 기존 클래스 docstring 끝에 다음을 추가:

```python
    # [동시성 안전] 이 클래스의 인스턴스는 요청마다 새로 생성되어야 한다.
    # _llm_call_count, _last_input_snapshot, _last_output_snapshot 등의
    # mutable 상태가 요청별로 격리되려면 인스턴스가 공유되지 않아야 한다.
    # 모듈 레벨 싱글톤으로 사용하지 마시오.
```

`__init__`의 mutable 변수에 주석을 추가한다:

line 92 변경:
```python
        # [동시성] 요청별 인스턴스 전제 — 싱글톤 시 요청 간 카운터 섞임
        self._llm_call_count = 0
```

lines 111-116을 다음으로 교체:
```python
        # A/B variant는 ContextVar(_active_ab_variant)로만 관리한다.
        # 인스턴스 변수로 중복 저장하지 않는다 — 동시 요청 시 경합 방지.

        # [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 스냅샷으로 덮어쓰기됨
        self._last_input_snapshot: dict[str, Any] | None = None
        # [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 결과로 덮어쓰기됨
        self._last_output_snapshot: dict[str, Any] | None = None
```

제거되는 코드:
- `self._current_ab_variant: str | None = None` (line 112)
- `# 현재 실행에서 선택된 A/B variant (Telemetry 추적용)` 주석 (line 111)

- [ ] **Step 2: `ab_variant` 프로퍼티를 ContextVar에서 읽도록 변경**

lines 300-308을 다음으로 교체:

```python
    @property
    def ab_variant(self) -> str | None:
        """현재 실행에서 선택된 A/B variant를 반환한다.

        ContextVar에서 읽으므로 동시 요청 간 안전하다.
        A/B 테스트가 비활성이면 None.
        """
        return _active_ab_variant.get()
```

- [ ] **Step 3: `__call__`에서 `_current_ab_variant` 참조 제거**

line 379를 제거:
```python
            # 제거: self._current_ab_variant = variant
```

line 426을 제거:
```python
            # 제거: self._current_ab_variant = None
```

변경 후 `__call__`의 A/B 테스트 부분 (lines 373-381):
```python
        # A/B 테스트 variant 결정
        ab_label = ""
        token: contextvars.Token[str | None] | None = None
        if self._ab_config is not None and self._ab_prompts:
            session_id = state.get("session_id", "unknown")
            variant = self._resolve_ab_variant(str(session_id))
            token = _active_ab_variant.set(variant)
            ab_label = f" [A/B: {variant}]"
```

변경 후 finally 블록 (lines 422-426):
```python
        finally:
            # contextvars 정리 — 이전 값으로 복원
            if token is not None:
                _active_ab_variant.reset(token)
```

- [ ] **Step 4: LangSmith metadata와 get_execution_metrics에서 ContextVar로 변경**

line 454 변경:
```python
            "ab_variant": _active_ab_variant.get(),
```

line 770 변경:
```python
            "ab_variant": _active_ab_variant.get(),
```

- [ ] **Step 5: 테스트 실행**

Run: `pytest tests/agents/shared/ -v --timeout=30`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add src/agents/shared/base_agent.py
git commit -m "refactor: _current_ab_variant 제거, ContextVar 일원화 + 동시성 주석 추가"
```

---

### Task 5: llm_client.py — `last_usage` 방어적 복사 + 동시성 주석

**Files:**
- Modify: `src/agents/shared/llm_client.py:61, 136, 138, 204-210`

- [ ] **Step 1: 클래스 변수와 인스턴스 변수에 동시성 주석 추가**

line 61 변경:
```python
    # [동시성] 클래스 변수 — 앱 부트스트랩 시에만 등록, 런타임 요청 중 변경 금지
    _custom_providers: dict[str, type] = {}
```

lines 135-137 변경:
```python
        # [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 토큰 수로 덮어쓰기됨
        self._last_usage: dict[str, int] | None = None
        # [동시성] 요청별 인스턴스 전제 — 싱글톤 시 += 연산이 비원자적이라 값 유실
        self._total_usage: dict[str, int] = {
```

- [ ] **Step 2: `last_usage` 프로퍼티를 방어적 복사로 변경**

lines 204-210을 다음으로 교체:

```python
    @property
    def last_usage(self) -> dict[str, int] | None:
        """직전 LLM 호출의 토큰 사용량을 반환한다.

        내부 상태 보호를 위해 복사본을 반환한다.

        Returns:
            {"input_tokens": N, "output_tokens": N, "total_tokens": N} 또는 None
        """
        return self._last_usage.copy() if self._last_usage is not None else None
```

- [ ] **Step 3: 테스트 실행**

Run: `pytest tests/agents/shared/test_llm_client.py -v --timeout=30`
Expected: PASS (테스트는 반환된 dict 값만 읽으므로 copy()로 인한 영향 없음)

- [ ] **Step 4: 커밋**

```bash
git add src/agents/shared/llm_client.py
git commit -m "refactor: last_usage 방어적 복사 + 동시성 주석 추가"
```

---

### Task 6: 전체 테스트 통합 검증

**Files:** (수정 없음 — 검증만)

- [ ] **Step 1: 전체 테스트 실행**

Run: `pytest tests/ -v --timeout=120`
Expected: ALL PASS

- [ ] **Step 2: 실패 시 대응**

실패 발생 시:
1. 실패 원인이 **제거된 싱글톤 참조** 또는 **변경된 내부 구조 의존**인지 확인
2. 해당하면 테스트 코드를 새 구조에 맞게 수정
3. 실패 원인이 **프로덕션 로직 결함**이면 프로덕션 코드를 수정
4. 재실행하여 전체 통과 확인

- [ ] **Step 3: 통합 테스트 실행**

Run: `pytest tests/integration/ -v --timeout=60`
Expected: PASS

- [ ] **Step 4: 최종 커밋 (필요 시)**

추가 수정이 있었다면:
```bash
git add -A
git commit -m "fix: 동시성 격리 리팩토링 후 테스트 수정"
```

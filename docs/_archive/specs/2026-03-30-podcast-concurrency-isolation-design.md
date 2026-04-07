# 팟캐스트모드 동시 요청 격리 설계

**작성일**: 2026-03-30
**범위**: 팟캐스트모드 파이프라인의 동시 요청 안전성 확보
**접근 방식**: 요청마다 에이전트 인스턴스 새로 생성 + 보호 파일 정리

---

## 1. 문제 정의

> **참고**: 이 섹션은 리팩토링 **전** 상태를 기술한다. 라인 번호는 리팩토링 전 기준이며, 현재 코드와 다를 수 있다.
> 리팩토링은 2026-03-30에 완료되었다.

### 리팩토링 전 구조

팟캐스트 파이프라인의 **모든 10개 에이전트**가 모듈 레벨 싱글톤으로 생성되어, 동시에 들어오는 여러 요청이 동일한 에이전트 인스턴스를 공유했다.

| 위치 | 싱글톤 에이전트 | 라인 |
|------|----------------|------|
| `src/graph/workflow.py` | `_intent_classifier` (IntentClassifierAgent) | 90 |
| `src/graph/workflow.py` | `_script_generator` (ScriptGeneratorAgent) | 99 |
| `src/graph/workflow.py` | `_script_personalizer` (ScriptPersonalizerAgent) | 156 |
| `src/agents/podcast/safety.py` | `safety_agent` (SafetyAgent) | 72 |
| `src/agents/podcast/emotion.py` | `emotion_agent` (EmotionAgent) | 90 |
| `src/agents/podcast/content_analyzer.py` | `content_analyzer_agent` (ContentAnalyzerAgent) | 236 |
| `src/agents/podcast/podcast_reasoning.py` | `podcast_reasoning_agent` (PodcastReasoningAgent) | 454 |
| `src/agents/podcast/batch_validator.py` | `batch_validator_agent` (BatchValidatorAgent) | 242 |
| `src/agents/podcast/visualization.py` | `visualization_agent` (VisualizationAgent) | 121 |
| `src/agents/shared/learning.py` | `learning_agent` (LearningAgent) | 131 |

추가로, 독립 에이전트 `EpisodeMemoryAgent`도 `episode_memory.py:138`에서 싱글톤으로 생성된다.

### 동시 요청 시 발생하는 문제

`BaseAgent` (`src/agents/shared/base_agent.py`)의 mutable 인스턴스 변수가 요청 간 덮어쓰기된다:

| 변수 | 라인 | 영향 받는 에이전트 | 위험 |
|------|------|-------------------|------|
| `_llm_call_count` | 92, 545, 564 | **전체 10개** (`call_llm()`에서 증가, `process()`/`__call__()` 모두 경유) | 요청 A/B의 LLM 호출 카운터가 섞임 |
| `_current_ab_variant` | 112, 379 | 7개 (`__call__()` 경유 에이전트만) | ContextVar `_active_ab_variant`와 중복 저장. 인스턴스 변수가 다른 요청 것으로 덮어쓰기 |
| `_last_input_snapshot` | 115, 391 | 7개 (`__call__()` 경유 에이전트만) | 요청 A가 요청 B의 입력 스냅샷을 읽음 |
| `_last_output_snapshot` | 116, 398 | 7개 (`__call__()` 경유 에이전트만) | 요청 A가 요청 B의 출력 스냅샷을 읽음 |

> **참고**: workflow.py의 3개 에이전트(IntentClassifier, ScriptGenerator, ScriptPersonalizer)는
> `__call__()`이 아닌 `.process()`를 직접 호출하므로 `_current_ab_variant`, `_last_*_snapshot`
> 변수는 변경되지 않는다. 그러나 `_llm_call_count`는 `call_llm()`/`call_llm_json()` 내부에서
> 증가하므로 `.process()` 경로에서도 공유 문제가 있다.

`LLMClient` (`src/agents/shared/llm_client.py`)의 토큰 사용량 추적도 안전하지 않다:

| 변수 | 라인 | 위험 |
|------|------|------|
| `_last_usage` | 136, 229-233 | 마지막 호출의 토큰 수가 다른 요청 것으로 덮어쓰기. 프로퍼티가 mutable dict 참조를 직접 반환 |
| `_total_usage` | 138, 234-236 | `+=` 연산이 atomic하지 않아 값 유실 가능 |

추가로, `_current_ab_variant` 인스턴스 변수(base_agent.py:112)는 이미 존재하는 ContextVar `_active_ab_variant`(base_agent.py:54)와 **동일한 값을 중복 저장**하고 있다. 실제 prompt 선택 로직(`get_prompt()`, line 327)은 ContextVar에서 값을 읽으므로, 인스턴스 변수는 모니터링/로깅 용도로만 사용되는 불필요한 경합 포인트이다.

### 완화 요소 (변경 불필요한 부분)

- `compiled_graph`: LangGraph의 컴파일된 그래프는 공유해도 안전. `ainvoke`마다 독립된 상태를 주입한다.
- `initial_state`: `src/api/routes/podcasts.py:270-275`에서 요청마다 새로 생성한다.
- `backend_client`: `httpx.AsyncClient`는 동시 요청에 안전하다.
- `_active_ab_variant` (contextvars): asyncio 태스크별로 격리된다.
- `get_settings()`: 읽기 전용 싱글톤, 초기화 후 변경 없음.
- `_custom_providers` (llm_client.py:61): 클래스 변수. 앱 부트스트랩 시에만 등록(`dev/ollama_bootstrap.py`), 런타임 요청 중 변경 없음.

---

## 2. 요구사항

1. 여러 사용자가 동시에 팟캐스트 에피소드를 요청하면, 각 요청마다 파이프라인이 **개별로** 실행된다.
2. 한 사용자의 데이터(감정, 입력 내용, 위기 상태 등)가 다른 사용자의 실행 결과에 **절대 섞이지 않는다**. 개인정보에 민감한 프로젝트로, 100명 동시 요청에서도 데이터 격리가 보장되어야 한다.
3. 각 요청의 결과가 해당 요청의 백엔드에 **정확하게** 반환된다.
4. 보호 파일(`base_agent.py`, `llm_client.py`)은 필요 시 수정하되 **신중하게** 접근한다.
5. 불필요한 코드를 정리하고, 동시성 및 데이터 격리 관련 주석을 명확하게 남긴다.

---

## 3. 설계

### 개요

변경은 3가지 레이어로 구분한다:

| 레이어 | 대상 | 목적 |
|--------|------|------|
| A. 싱글톤 제거 | workflow.py + 7개 에이전트 파일 | 요청별 인스턴스 격리 (핵심 변경) |
| B. base_agent.py 정리 | `_current_ab_variant` 중복 제거 + 주석 | 불필요한 경합 포인트 제거 |
| C. llm_client.py 정리 | `last_usage` 프로퍼티 방어적 복사 + 주석 | 내부 상태 보호 강화 |

---

### 3.A 싱글톤 제거 — 노드 함수 내부에서 에이전트 생성

#### workflow.py (3개 에이전트 + reset_agents 제거)

**변경 전:**
```python
_intent_classifier = IntentClassifierAgent()

async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """Intent Classifier 노드"""
    return await _intent_classifier.process(state)
```

**변경 후:**
```python
async def intent_classifier_node(state: AgentState) -> dict[str, Any]:
    """Intent Classifier 노드 — 요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다."""
    agent = IntentClassifierAgent()
    return await agent.process(state)
```

동일 패턴을 `_script_generator`, `_script_personalizer`에도 적용한다.

**`reset_agents()` 함수 제거**: 싱글톤이 없어지므로 함수 자체를 제거한다. 현재 프로덕션 코드에서 호출하는 곳이 없으며, 테스트(`dev/live_tests/test_e2e_multi_provider.py`)에서는 `importlib.reload(workflow)`를 사용하므로 영향 없음.

#### 개별 에이전트 파일 (7개)

각 파일의 모듈 레벨 싱글톤을 제거하고 노드 함수 내부에서 생성한다.

| 파일 | 제거할 싱글톤 | 변경할 노드 함수 |
|------|-------------|----------------|
| `src/agents/podcast/safety.py:72` | `safety_agent` | `safety_node()` |
| `src/agents/podcast/emotion.py:90` | `emotion_agent` | `emotion_node()` |
| `src/agents/podcast/content_analyzer.py:236` | `content_analyzer_agent` | `content_analyzer_node()` |
| `src/agents/podcast/podcast_reasoning.py:454` | `podcast_reasoning_agent` | `podcast_reasoning_node()` |
| `src/agents/podcast/batch_validator.py:242` | `batch_validator_agent` | `batch_validator_node()` |
| `src/agents/podcast/visualization.py:121` | `visualization_agent` | `visualization_node()` |
| `src/agents/shared/learning.py:131` | `learning_agent` | `learning_node()` |

**변경 전 (공통 패턴):**
```python
safety_agent = SafetyAgent()

async def safety_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Safety Agent. 3인 합의된 workflow.py에서 호출됨."""
    return await safety_agent(state)
```

**변경 후 (공통 패턴):**
```python
async def safety_node(state: AgentState) -> dict[str, Any]:
    """LangGraph 노드 — Safety Agent.
    요청마다 새 인스턴스를 생성하여 동시 요청 간 상태를 격리한다.
    """
    agent = SafetyAgent()
    return await agent(state)
```

#### EpisodeMemoryAgent (수정 대상 아님)

`src/agents/podcast/episode_memory.py:138`의 `episode_memory_agent` 싱글톤과 `episode_memory_node`는 **현재 workflow.py에 등록되어 있지 않다**. `dev/manual_tests/`에서만 사용되며, 프로덕션 파이프라인에서 `PodcastReasoningAgent`는 기본값으로 `EpisodeMemoryStub()`을 사용한다. 따라서 이번 변경에서 `episode_memory.py`는 수정 대상이 아니다.

---

### 3.B base_agent.py 정리 (보호 파일 — 신중하게)

요청별 인스턴스 생성으로 대부분의 mutable 상태 문제는 자동 해결된다. 추가로 다음 2가지를 정리한다.

#### B-1. `_current_ab_variant` 인스턴스 변수 제거

**이유**: ContextVar `_active_ab_variant`(line 54)가 이미 동일한 값을 asyncio 태스크별로 격리하여 관리한다. 인스턴스 변수 `_current_ab_variant`(line 112)는 중복 저장이며, 싱글톤 환경에서 요청 간 경합을 유발하는 불필요한 코드이다.

**현재 `_current_ab_variant` 사용처 (6곳):**

| 위치 | 용도 | 변경 방법 |
|------|------|----------|
| line 112 | 선언 (`__init__`) | **제거** |
| line 307 | `ab_variant` 프로퍼티 반환값 | ContextVar에서 읽기: `_active_ab_variant.get()` |
| line 379 | 설정 (`__call__`) | **제거** |
| line 426 | 정리 (`finally`) | **제거** (ContextVar reset만 유지) |
| line 454 | LangSmith metadata | ContextVar에서 읽기: `_active_ab_variant.get()` |
| line 770 | `get_execution_metrics()` | ContextVar에서 읽기: `_active_ab_variant.get()` |

> **참고**: line 381(`ab_label`)과 line 406(로그 메시지)은 `__call__` 내 로컬 변수 `variant`/`ab_label`을 사용하며,
> `_current_ab_variant`를 직접 참조하지 않는다. 테스트 코드에서도 `_current_ab_variant`에 직접 접근하는 곳은 없다.

**`ab_variant` 프로퍼티 (line 299-307):**
```python
# 변경 전
@property
def ab_variant(self) -> str | None:
    return self._current_ab_variant

# 변경 후
@property
def ab_variant(self) -> str | None:
    """현재 실행에서 선택된 A/B variant를 반환한다.
    ContextVar에서 읽으므로 동시 요청 간 안전하다.
    """
    return _active_ab_variant.get()
```

#### B-2. 동시성 안전 주석 추가

요청별 인스턴스 생성 패턴이 전제되어야 안전한 변수들에 주석을 추가한다. 향후 싱글톤으로 회귀하는 것을 방지하기 위함이다.

```python
class BaseAgent(ABC):
    """에이전트 공통 부모 클래스.

    [동시성 안전] 이 클래스의 인스턴스는 요청마다 새로 생성된다.
    _llm_call_count, _last_input_snapshot, _last_output_snapshot 등의
    mutable 상태가 요청별로 격리되려면 인스턴스가 공유되지 않아야 한다.
    모듈 레벨 싱글톤으로 사용하지 마시오.
    """
```

추가할 주석 위치:

| 위치 | 주석 내용 |
|------|----------|
| `__init__` 내 `_llm_call_count` (line 92) | `# [동시성] 요청별 인스턴스 전제 — 싱글톤 시 요청 간 카운터 섞임` |
| `__init__` 내 `_last_input_snapshot` (line 115) | `# [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 스냅샷으로 덮어쓰기됨` |
| `__init__` 내 `_last_output_snapshot` (line 116) | `# [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 결과로 덮어쓰기됨` |

---

### 3.C llm_client.py 정리 (보호 파일 — 신중하게)

요청별 인스턴스 생성으로 토큰 추적의 경합 문제는 자동 해결된다. 추가로 다음 2가지를 정리한다.

#### C-1. `last_usage` 프로퍼티 방어적 복사

**현재 (line 204-211):**
```python
@property
def last_usage(self) -> dict[str, int] | None:
    """직전 LLM 호출의 토큰 사용량을 반환한다."""
    return self._last_usage  # mutable dict 참조 직접 반환
```

**변경 후:**
```python
@property
def last_usage(self) -> dict[str, int] | None:
    """직전 LLM 호출의 토큰 사용량을 반환한다.
    내부 상태 보호를 위해 복사본을 반환한다.
    """
    return self._last_usage.copy() if self._last_usage is not None else None
```

> **참고**: `total_usage` 프로퍼티(line 213-216)는 이미 `.copy()`를 사용하고 있어 일관성을 맞춤.

#### C-2. 동시성 안전 주석 추가

```python
class LLMClient:
    """LLM 멀티 프로바이더 클라이언트.

    [동시성 안전] 이 클래스의 인스턴스는 BaseAgent와 함께 요청마다 새로 생성된다.
    _last_usage, _total_usage 등의 mutable 상태가 요청별로 격리되려면
    인스턴스가 공유되지 않아야 한다.
    """
```

추가할 주석 위치:

| 위치 | 주석 내용 |
|------|----------|
| `_last_usage` (line 136) | `# [동시성] 요청별 인스턴스 전제 — 싱글톤 시 다른 요청 토큰 수로 덮어쓰기됨` |
| `_total_usage` (line 138) | `# [동시성] 요청별 인스턴스 전제 — 싱글톤 시 += 연산이 비원자적이라 값 유실` |
| `_custom_providers` (line 61) | `# [동시성] 클래스 변수 — 앱 부트스트랩 시에만 등록, 런타임 요청 중 변경 금지` |

---

### 3.D 변경하지 않는 것

| 항목 | 이유 |
|------|------|
| `src/graph/workflow.py` 그래프 구조 | 노드 등록, 엣지, 조건부 라우팅은 변경 없음 |
| `src/api/routes/podcasts.py` | 이미 요청별 `initial_state` 생성 + `compiled_graph.ainvoke()` 패턴 |
| `src/api/main.py` | `compiled_graph`, `backend_client` 공유는 안전 |
| `config/loader.py` | `get_settings()` 읽기 전용 싱글톤은 안전 |
| `episode_memory.py` | workflow.py에 미등록, 프로덕션 미사용 |
| 기존 팩토리 패턴 | `create_script_generator_node()`, `create_script_personalizer_node()` — 사용하지 않고 제거하지도 않음. 차후 DI 필요 시 활용 |

---

## 4. 동시 요청 실행 흐름 (변경 후)

```
요청 A (alice, sess_001)              요청 B (bob, sess_002)
    |                                      |
    v                                      v
compiled_graph.ainvoke(                compiled_graph.ainvoke(
  state_A, thread_id=sess_001)          state_B, thread_id=sess_002)
    |                                      |
    v                                      v
IntentClassifierAgent() 새 생성        IntentClassifierAgent() 새 생성
  _llm_call_count = 0 (A 전용)          _llm_call_count = 0 (B 전용)
  LLMClient() (A 전용)                  LLMClient() (B 전용)
    |                                      |
    v                                      v
TIER 1 병렬 (각각 새 인스턴스)          TIER 1 병렬 (각각 새 인스턴스)
  SafetyAgent()  - A 전용                SafetyAgent()  - B 전용
  EmotionAgent() - A 전용                EmotionAgent() - B 전용
  ContentAnalyzerAgent() - A 전용        ContentAnalyzerAgent() - B 전용
  PodcastReasoningAgent() - A 전용       PodcastReasoningAgent() - B 전용
    |                                      |
    v                                      v
ScriptGeneratorAgent() - A 전용        ScriptGeneratorAgent() - B 전용
    |                                      |
    v                                      v
BatchValidatorAgent() - A 전용         BatchValidatorAgent() - B 전용
    |                                      |
    v                                      v
ScriptPersonalizerAgent() - A 전용     ScriptPersonalizerAgent() - B 전용
    |                                      |
    v                                      v
alice 결과 반환                         bob 결과 반환
    |                                      |
    v                                      v
LearningAgent() - A 전용 (비동기)      LearningAgent() - B 전용 (비동기)
```

모든 mutable 상태가 요청별 인스턴스에 격리된다:
- `_llm_call_count`: 요청별 BaseAgent 인스턴스에 속함
- `_last_input_snapshot`, `_last_output_snapshot`: 요청별 인스턴스에 속함
- `_last_usage`, `_total_usage`: 요청별 LLMClient 인스턴스에 속함
- A/B variant: ContextVar로 asyncio 태스크별 격리 (인스턴스 변수 제거)

---

## 5. 변경 요약

### 수정 파일 목록

| # | 파일 | 변경 내용 | 레이어 |
|---|------|----------|--------|
| 1 | `src/graph/workflow.py` | 3개 싱글톤 제거, 노드 함수 내부 생성, `reset_agents()` 제거 | A |
| 2 | `src/agents/podcast/safety.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 3 | `src/agents/podcast/emotion.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 4 | `src/agents/podcast/content_analyzer.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 5 | `src/agents/podcast/podcast_reasoning.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 6 | `src/agents/podcast/batch_validator.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 7 | `src/agents/podcast/visualization.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 8 | `src/agents/shared/learning.py` | 싱글톤 제거, 노드 함수 내부 생성 | A |
| 9 | `src/agents/shared/base_agent.py` | `_current_ab_variant` 제거, ContextVar 일원화, 주석 추가 | B |
| 10 | `src/agents/shared/llm_client.py` | `last_usage` 방어적 복사, 주석 추가 | C |
| 11 | `tests/graph/test_e2e_mock_pipeline.py` | 싱글톤 패치를 노드 함수 패치로 변경 | 테스트 |

---

## 6. 성능 영향

### 에이전트 인스턴스 생성 비용

에이전트 `__init__`에서 수행하는 작업:
1. `LLMClient` 생성 — boto3/httpx 클라이언트 초기화
2. `PromptLoader` — YAML 파일 읽기 + 파싱
3. 프롬프트 버전 해석 + A/B 설정 로딩

### 예상 오버헤드

| 작업 | 소요 시간 (추정) |
|------|-----------------|
| 에이전트 인스턴스 생성 (10개) | ~5-15ms |
| 실제 LLM 호출 (파이프라인 전체) | ~3,000-15,000ms |

인스턴스 생성 비용은 LLM 호출 대비 **0.1% 미만**이므로 무시할 수 있다.

---

## 7. 테스트 전략

### 원칙

코드 변경 후 테스트가 실패하면, 먼저 **구현 의도를 확인**한다.
실패 원인이 프로덕션 로직의 결함이면 프로덕션 코드를 수정하고,
실패 원인이 테스트 코드가 **제거된 싱글톤이나 변경된 내부 구조에 의존**하는 경우라면
테스트 코드를 구현 의도에 맞게 수정하여 재실행한다.

### 영향 분석

#### 수정이 필요한 테스트 (1개 파일)

**`tests/graph/test_e2e_mock_pipeline.py`** — 싱글톤 변수를 직접 패치하여 실패 확정

현재 이 테스트는 workflow 모듈의 싱글톤에 monkeypatch를 적용한다:
```python
import src.graph.workflow as wf
monkeypatch.setattr(wf._intent_classifier, "process", AsyncMock(...))
monkeypatch.setattr(wf._script_generator, "process", AsyncMock(...))
monkeypatch.setattr(wf._script_personalizer, "process", AsyncMock(...))
```

싱글톤 제거 후 `wf._intent_classifier` 등의 모듈 속성이 존재하지 않으므로 `AttributeError`가 발생한다.
이는 프로덕션 로직의 결함이 아니라 테스트가 **구현 세부사항(싱글톤 변수)**에 의존하고 있기 때문이다.

**수정 방향**: 노드 함수 자체를 패치하는 방식으로 변경한다.
```python
monkeypatch.setattr(wf, "intent_classifier_node", AsyncMock(return_value=MOCK_INTENT))
monkeypatch.setattr(wf, "script_generator_node", AsyncMock(return_value=MOCK_SCRIPT))
monkeypatch.setattr(wf, "script_personalizer_node", AsyncMock(return_value=MOCK_FINAL))
```

나머지 노드 패치(`safety_node`, `emotion_node` 등)는 이미 함수명으로 패치하고 있어 변경 불필요.

#### 확인이 필요한 테스트 (1개 파일)

**`tests/agents/shared/test_llm_client.py`** — `last_usage` 방어적 복사 적용 후 동작 확인

`last_usage` 프로퍼티가 `.copy()`를 반환하도록 변경된다. 현재 테스트(line 553-577)는
반환된 dict의 값을 읽기만 하므로 영향 없을 것으로 판단되나, 변경 후 실행하여 확인한다.

#### 영향 없는 테스트

| 테스트 영역 | 이유 |
|------------|------|
| 에이전트 단위 테스트 (5개+) | 에이전트를 직접 생성하여 테스트. 싱글톤 미참조 |
| 통합 테스트 (`tests/integration/`) | 노드 함수명으로 패치. 싱글톤 변수 미참조 |
| A/B 테스트 (`test_prompt_versioning.py`) | 해시 로직 독립 테스트. 인스턴스 변수 미참조 |
| 모니터링 테스트 (`test_io_tracker.py`) | IOSnapshot API 테스트. 싱글톤 미참조 |
| 멀티 프로바이더 테스트 (`dev/live_tests/`) | `importlib.reload(workflow)` 사용. `reset_agents()` 미호출 |

### 검증 절차

변경 완료 후 전체 테스트를 실행한다:
```bash
pytest tests/ -v
```

실패 발생 시:
1. 실패 원인이 **제거된 싱글톤 참조** 또는 **변경된 내부 구조 의존**인지 확인
2. 해당하면 테스트 코드를 새 구조에 맞게 수정
3. 실패 원인이 **프로덕션 로직 결함**이면 프로덕션 코드를 수정
4. 재실행하여 전체 통과 확인

---

## 8. 개인정보 격리 검증 (100명 동시 요청 시나리오)

이 프로젝트는 사용자의 감정과 멘탈 상태를 다루는 민감한 서비스이다.
다른 사용자의 정보 및 데이터가 혼동되어 들어오거나 표출되어 나가는 일이 절대 발생해서는 안 된다.
100명의 사용자가 동시에 요청을 보내는 시나리오를 전제로, 전체 데이터 경로를 검증한 결과이다.

### 이 설계로 해결되는 데이터 격리 위험

| 위험 | 원인 | 해결 방법 |
|------|------|----------|
| 사용자 A의 입력 스냅샷이 사용자 B에게 노출 | 싱글톤의 `_last_input_snapshot`이 덮어쓰기됨 | 요청별 인스턴스 생성 (레이어 A) |
| 사용자 A의 출력 결과가 사용자 B에게 노출 | 싱글톤의 `_last_output_snapshot`이 덮어쓰기됨 | 요청별 인스턴스 생성 (레이어 A) |
| LLM 호출 토큰 수가 다른 사용자 것과 섞임 | 싱글톤의 `_llm_call_count`, `_total_usage` 공유 | 요청별 인스턴스 생성 (레이어 A) |
| A/B 테스트 변형이 다른 사용자 것으로 기록 | `_current_ab_variant` 인스턴스 변수 경합 | ContextVar 일원화 (레이어 B) |
| `last_usage` 프로퍼티로 내부 dict 변경 가능 | mutable dict 참조 직접 반환 | 방어적 복사 (레이어 C) |

### 기존 코드에서 이미 안전한 영역 (변경 불필요)

| 영역 | 격리 메커니즘 | 검증 결과 |
|------|-------------|----------|
| CRISIS 선점 | `cancel_event`가 함수 진입 시 요청별 생성 (workflow.py:320, 408) | 사용자 A의 위기 신호가 사용자 B의 TIER 1을 취소하지 않음 |
| `next_step` 라우팅 | AgentState 필드 — LangGraph가 요청별 상태 복사본 관리 | 사용자 A의 라우팅 결정이 사용자 B에 영향 없음 |
| 라우팅 함수 | `route_after_tier1()` 등은 state만 읽는 순수 함수 | 모듈 레벨 상태 미변경 |
| `initial_state` 생성 | podcasts.py:270-275에서 요청마다 새 dict 생성 | 공유 참조 없음 |
| `MindLogTelemetryCallback` | 요청마다 새 인스턴스 생성 (podcasts.py:282) | 텔레메트리 데이터 격리 |
| `BackendClient` (httpx) | `httpx.AsyncClient`는 동시 비동기 요청에 안전 | 요청 간 데이터 혼선 없음 |
| 비동기 후처리 | `asyncio.create_task()`로 생성, state 인자는 요청별 AgentState | 백그라운드 태스크도 요청별 격리 |
| 모듈 레벨 상수 | `_MAX_RETRIES`, `_TIER1_TIMEOUT` 등 immutable int | 런타임 변경 불가 |
| ContextVar (`_active_ab_variant`) | asyncio 태스크별 자동 격리 | A/B variant 선택이 요청 간 간섭 없음 |
| 프롬프트 캐시 (`PromptLoader._cache`) | 시스템 프롬프트만 캐시, 사용자 데이터 미포함 | 개인정보 미저장 |
| 입력 스냅샷 (`_sanitize_state_snapshot`) | `user_input`은 길이만 기록, 원문 미저장 | 민감정보 보호 |

### 동시 요청 시나리오: 사용자 A (위기 상황) + 사용자 B (일반 요청)

```
T0: 사용자 A "자해 충동이 있어요" → compiled_graph.ainvoke(state_A)
T1: 사용자 B "명상에 대해 알려줘" → compiled_graph.ainvoke(state_B)

T2: TIER 1 병렬 실행
    ┌─ state_A → SafetyAgent() [A 전용] → CRISIS 감지
    │   └─ cancel_event_A.set()  ← A의 이벤트만 발동
    │   └─ A의 Emotion/Content/Reasoning 취소
    │   └─ Safety 심화 → 위기 응답 생성
    │
    └─ state_B → SafetyAgent() [B 전용] → safe 판정
        └─ cancel_event_B는 미발동
        └─ B의 Emotion/Content/Reasoning 정상 완료

T3: 사용자 A → 위기 응답 (핫라인 안내 등) 즉시 반환
    사용자 B → TIER 2~4 정상 진행 → 명상 팟캐스트 반환

결과:
  ✓ 사용자 A의 위기 데이터가 사용자 B에게 노출되지 않음
  ✓ 사용자 B의 파이프라인이 A의 CRISIS로 중단되지 않음
  ✓ 각 사용자의 응답이 올바른 요청에 반환됨
```

---

## 9. 차후 확장 고려

### Learning Agent 기반 개인화

학습 데이터가 파이프라인에 반영될 때 (Script Personalizer가 학습 데이터를 조회하는 구조):
- 요청별 인스턴스 생성 패턴이면, 매 요청마다 최신 학습 데이터를 DB에서 조회
- 싱글톤이었다면 캐시 무효화/동기화 문제가 추가로 발생했을 것
- **이 설계가 개인화 확장에도 자연스럽게 호환**된다

### 대화모드 확장

대화모드의 스텁 에이전트(Context, Reasoning, Synthesis, Validator, Personalization)가 구현될 때도 동일한 패턴(노드 함수 내부 인스턴스 생성)을 적용하면 된다. `base_agent.py`와 `llm_client.py`에 추가된 동시성 주석이 가이드 역할을 한다.

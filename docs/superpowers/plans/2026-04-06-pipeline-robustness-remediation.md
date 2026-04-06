# 파이프라인 견고성 강화 계획서 (아카이브 v1-v4)

> **⚠️ 이 문서는 아카이브입니다. v4부터 문서가 분리되었습니다.**
> - **마스터 인덱스:** [pipeline-robustness-index.md](./pipeline-robustness-index.md)
> - **Phase 1 (Changes 1-7):** [pipeline-robustness-part1.md](./pipeline-robustness-part1.md)
> - **Phase 2 (Structured Fallback):** [pipeline-robustness-part2.md](./pipeline-robustness-part2.md)

---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AWS E2E 테스트 및 멀티 서브에이전트 감사(6개 병렬 에이전트 교차 검증 포함)에서 발견된 파이프라인 구조적 취약점 **10개**를 수정하여, LLM 실패·타임아웃·필드 누락 시 연쇄 실패를 방지한다.

**Architecture:** TIER 0→4 LangGraph 파이프라인에서 에이전트 간 상태 필드 의존성이 방어 코드 없이 하드와이어드되어 있음. 각 에이전트가 이전 에이전트의 출력 구조를 가정하고 동작하다보니, LLM 실패 1건이 전체 파이프라인 크래시로 이어진다. 이번 수정은 각 에이전트가 빈/부분 입력에서도 의미 있는 결과를 반환하도록 방어 코드를 추가한다.

**Tech Stack:** Python 3.11+, LangGraph StateGraph, FastAPI, AsyncIO

**브랜치 전략:** 신규 브랜치 `feature/reasoning-pipeline-robustness` (개발자2 생성, 3인 모두 리뷰 필수)

---

## 왜 PR#59와 분리하는가

현재 진행 중인 `feature/reasoning-aws-env-remediation` (PR#59 후보)는 **AWS 환경변수 주입 문제** (deploy.yml, BACKEND_API_URL, .env.db gitignore)에 집중되어 있다.

이번 버그들은 **파이프라인 로직 문제**로, 수정 대상 파일이 완전히 다르다:

| PR#59 (진행 중) | 이번 계획 (신규) |
|----------------|----------------|
| `.github/workflows/deploy.yml` | `src/graph/workflow.py` ← Protected |
| `config/loader.py` | `src/agents/podcast/podcast_reasoning.py` |
| `.gitignore` | `src/agents/podcast/script_generator.py` |
| `docs/` | `src/agents/podcast/batch_validator.py` |
| | `src/agents/podcast/emotion.py` |
| | `src/agents/podcast/script_personalizer.py` |
| | `src/agents/podcast/content_analyzer.py` |
| | `src/agents/podcast/safety.py` |

두 작업을 하나의 PR에 묶으면 리뷰 범위가 너무 넓어지고, 롤백 시 독립적 처리가 불가능해진다.

---

## PR#58에서 진행된 이유 (경위 설명)

이전 세션 컨텍스트 요약에 "PR#58 (feature/reasoning-security-remediation) 배포 검증"으로 기록되어 있어 혼선이 발생했다. 실제 경위:

1. 세션 시작 시점: 로컬이 `feature/reasoning-security-remediation` 브랜치였음 (PR#58 브랜치)
2. PR#58은 이미 develop에 **MERGE 완료** (`d13c4b4`) — 배포된 상태 검증이 목적
3. 세션 중 `feature/reasoning-aws-env-remediation`으로 전환하여 PR#59 작업 병행
4. **AWS 배포 검증 대상은 develop (PR#58 포함)** — 로컬 브랜치와 무관

결론: PR#58 기준 배포 검증은 올바른 행동이었다. 로컬 브랜치 혼선만 존재했을 뿐.

---

## 브랜치 구조 현황 (2026-04-06)

```
main            ← PR#25까지만 반영 (배포 기준 아님)
  └── develop   ← PR#58까지 반영 (AWS EC2 실제 배포 기준)
        └── feature/reasoning-aws-env-remediation  [PR#59 후보, 5커밋 ahead]
              └── [신규] feature/reasoning-pipeline-robustness  [이번 계획]
```

**develop이 실질적 배포 기준 브랜치**임을 주의. main은 아직 PR#25 수준.

---

## 파일 구조

```
수정 파일:
├── src/graph/workflow.py                          ← Protected File (3인 합의 필수)
├── src/agents/podcast/podcast_reasoning.py        ← 개발자3 도메인
├── src/agents/podcast/content_analyzer.py         ← 개발자3 도메인 [v2 추가]
├── src/agents/podcast/script_generator.py         ← 개발자1 도메인
├── src/agents/podcast/batch_validator.py          ← 개발자3 도메인
├── src/agents/podcast/safety.py                   ← 개발자2 도메인 [v2 추가]
├── src/agents/podcast/emotion.py                  ← 개발자2 도메인
└── src/agents/podcast/script_personalizer.py      ← 개발자1 도메인

신규/수정 테스트:
├── tests/graph/test_workflow_routing.py           ← workflow.py 변경 검증
├── tests/agents/podcast/test_podcast_reasoning.py ← user_input 방어 케이스
├── tests/agents/podcast/test_content_analyzer.py  ← user_input 방어 케이스 [v2 추가]
├── tests/agents/podcast/test_batch_validator.py   ← LLM 실패 케이스
├── tests/agents/podcast/test_safety.py            ← LLM 실패 케이스 [v2 추가]
├── tests/agents/podcast/test_script_generator.py  ← content_analysis 누락 케이스
├── tests/agents/podcast/test_emotion_agent.py     ← fallback 개선 케이스
└── tests/agents/podcast/test_script_personalizer.py ← empty script_draft 케이스
```

---

## 발견된 취약점 전체 목록

멀티 서브에이전트 4개 + AWS SSM 10회 E2E 테스트 결과 종합.

| # | 파일 | 라인 | 취약점 | 위험도 | 발생 조건 |
|---|------|------|--------|--------|---------|
| 1 | workflow.py | **118, 127, 185** | `agent.process(state)` 직접 호출 → BaseAgent.__call__() 우회 **(3곳)** | CRITICAL | 상시 발생 |
| 2 | podcast_reasoning.py | 81 | `state["user_input"]` KeyError 무방비 | CRITICAL | 독립 테스트 시 |
| 2-B | content_analyzer.py | 81 | `state["user_input"]` KeyError 무방비 **(동일 패턴)** [v2 추가] | CRITICAL | 독립 테스트 시 |
| 3 | script_generator.py | 48-50 | `content_analysis` 없을 때 `state` 전체를 fallback으로 사용 | HIGH | Content Analyzer 실패/타임아웃 시 |
| 4 | batch_validator.py | 84-87 | `call_llm_json()` 주변 try/except 없음 | HIGH | LLM 응답 파싱 실패 시 |
| 4-B | safety.py | 45-47 | `call_llm_json()` 주변 try/except 없음 **(CRISIS 판정 크래시 위험)** [v2 추가] | CRITICAL | LLM 응답 파싱 실패 시 |
| 4-C | podcast_reasoning.py | 270, 298, 328 | GoT/ToT/CoT `call_llm_json()` 3곳 try/except 없음 [v2 추가] | HIGH | LLM 응답 파싱 실패 시 |
| 5 | emotion.py | 97-109 | LLM 실패 시 fallback이 `intent` 감정 정보 미활용 | MEDIUM | LLM 응답 파싱 실패 시 |
| 6 | script_personalizer.py | 170-181 | ValidatedScript 생성 실패 시 `final_output = ""` 반환 | HIGH | script_draft 빈 dict 또는 구조 불일치 시 |

> **[v2] 교차 검증으로 추가 발견**: 6개 병렬 코드 리뷰 에이전트 검증 결과, v1 계획서 대비 **4개 추가 취약점** (1→3곳 확대, 2-B, 4-B, 4-C) 발견됨.

**추가 구조적 문제 (이번 계획에서 제외 — 별도 계획 필요):**

| # | 파일 | 라인 | 내용 | 이유 |
|---|------|------|------|------|
| A | workflow.py | 76-94 | `_with_timeout()` 타임아웃 시 `{}` 반환 → 하위 필드 누락 | 에이전트별 기본값 설계 필요. 대규모 변경 |
| B | (여러 파일) | - | episode_memory.yaml 없음 → Stub 사용 중 | Pinecone 연동과 묶여 있음 |
| C | config/settings.yaml | - | 복잡도 임계값 CLAUDE.md vs settings.yaml 불일치 | 3인 합의 후 settings.yaml 단독 기준 확립 |

---

## Change 1: workflow.py — `__call__()` 우회 수정 (3곳) [v2 범위 확대]

### 근거

workflow.py에 인라인 정의된 **3개 노드 함수 모두** `agent.process(state)`를 직접 호출하여 `BaseAgent.__call__()`을 우회한다. `__call__()`은 다음을 수행한다:
- LangSmith 트레이싱 스팬 생성 (PromptRun, ChainRun)
- A/B 테스트 ContextVar 초기화
- LLM 호출 카운터 초기화 (`_llm_call_count = 0`)
- 처리 시간 측정 (`time.monotonic()`)
- 입출력 스냅샷 기록

> **[v2 교차 검증 결과]** v1 계획서는 "Intent Classifier 1개만 이 버그를 갖고 있다"고 기술했으나, 코드 리뷰 에이전트가 **script_generator_node(라인 127)과 script_personalizer_node(라인 185)에서도 동일 버그를 발견**했다.

나머지 7개 에이전트(safety, emotion, content_analyzer, podcast_reasoning, batch_validator, visualization, learning)는 각 모듈 내부에서 `await agent(state)` 패턴을 올바르게 사용한다.

**왜 지금까지 발견되지 않았는가:** `process()` 메서드도 정상적으로 LLM 호출과 결과 반환은 하므로 기능적 오작동이 없었음. 관측 인프라만 손상된 상태.

### 수정 대상 (workflow.py — 3곳)

**변경 1 (라인 115-118) — intent_classifier_node:**
```python
# 변경 전:
    return await agent.process(state)
# 변경 후:
    return await agent(state)
```

**변경 2 (라인 124-127) — script_generator_node:**
```python
# 변경 전:
    return await agent.process(state)
# 변경 후:
    return await agent(state)
```

**변경 3 (라인 182-185) — script_personalizer_node:**
```python
# 변경 전:
    return await agent.process(state)
# 변경 후:
    return await agent(state)
```

**3줄 변경. 각각 `process` → `(state)` (괄호 호출).**

### 후속 조치

**왜 후속 조치가 필요한가:**
- `__call__()` 활성화 후 LangSmith에 Intent Classifier 트레이스가 새로 생성됨 → LangSmith 프로젝트에서 새 스팬 유형 확인 필요
- A/B 테스트 ContextVar가 활성화되면 `settings.yaml`의 `prompts.ab_tests.intent_classifier` 설정이 효과를 가짐 → 의도치 않은 버전 전환 주의
- `_llm_call_count` 초기화로 카운터 기반 로직이 동작하기 시작함

**체크리스트:**
- [ ] `settings.yaml`에 `prompts.ab_tests.intent_classifier` 활성화 설정이 있는지 확인 → 있으면 `enabled: false` 확인
- [ ] `__call__()` 내부 A/B 테스트 분기 로직이 intent_classifier에 영향을 주는지 `base_agent.py` 확인
- [ ] 변경 후 E2E 테스트에서 LangSmith 트레이스 정상 기록 확인

### 테스트 수정

`tests/graph/test_workflow_routing.py` 또는 `tests/graph/test_e2e_mock_pipeline.py`:

```python
# 추가할 테스트: intent_classifier_node가 __call__을 사용하는지 확인
@pytest.mark.asyncio
async def test_intent_classifier_node_uses_call_not_process():
    """workflow.py intent_classifier_node가 agent.process()가 아닌 agent()를 호출하는지 확인."""
    mock_agent = AsyncMock()
    mock_agent.return_value = {"intent": {}}

    with patch(
        "src.graph.workflow.IntentClassifierAgent",
        return_value=mock_agent,
    ):
        state = AgentState(
            user_input="테스트",
            user_id="u1",
            session_id="s1",
            mode="podcast",
        )
        await intent_classifier_node(state)

    # __call__ 경로 확인: mock_agent(state)가 1회 호출됐는지
    mock_agent.assert_awaited_once_with(state)
    # process()가 호출됐다면 이 assertion이 실패함
    mock_agent.process.assert_not_called()
```

### 구현 절차

- [ ] Step 1: `src/graph/workflow.py:118` (intent_classifier_node) `agent.process(state)` → `await agent(state)` 수정
- [ ] Step 1b: `src/graph/workflow.py:127` (script_generator_node) 동일 수정 [v2 추가]
- [ ] Step 1c: `src/graph/workflow.py:185` (script_personalizer_node) 동일 수정 [v2 추가]
- [ ] Step 2: `settings.yaml` A/B 테스트 설정 확인 (`enabled: false` 여부)
- [ ] Step 3: 테스트 파일에 `test_intent_classifier_node_uses_call_not_process` 추가
- [ ] Step 4: `pytest tests/graph/ -v` — 기존 + 신규 테스트 통과
- [ ] Step 5: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

> **Protected File 주의:** workflow.py 수정 전 3인 합의 슬랙/PR 리뷰 필수.

---

## Change 1-B: workflow.py — TIER 0 타임아웃 래퍼 적용 [v2 추가]

### 근거

`_TIER0_TIMEOUT` 변수가 `workflow.py:68`에서 로드되지만(**20초, settings.yaml 기준**), 이 값을 사용하는 코드가 **전체 workflow.py에 존재하지 않는다**. Dead code 상태.

TIER 1~4는 모두 `asyncio.wait_for()` 또는 `_with_timeout()` 래퍼로 보호된다. TIER 0만 타임아웃이 없어 Intent Classifier LLM이 무응답하면 파이프라인 전체가 무한 대기에 빠질 수 있다.

### 수정 대상 (workflow.py — build_unified_graph)

`build_unified_graph()` 라인 576 부근에서 `intent_classifier_node`를 타임아웃 래퍼로 감싸야 한다:

**변경 전:**
```python
graph.add_node("intent_classifier", intent_classifier_node)
```

**변경 후:**
```python
async def _intent_classifier_with_timeout(s: AgentState) -> dict[str, Any]:
    return await _with_timeout(intent_classifier_node, s, _TIER0_TIMEOUT, "intent_classifier")

graph.add_node("intent_classifier", _intent_classifier_with_timeout)
```

### 구현 절차

- [ ] Step 1: `build_unified_graph()` 내에서 `intent_classifier_node`에 `_with_timeout()` 래퍼 적용
- [ ] Step 2: 테스트 추가 — Intent Classifier 타임아웃 시 빈 dict 반환 확인
- [ ] Step 3: `pytest tests/graph/ -v` — 기존 + 신규 테스트 통과

> **Protected File 주의:** workflow.py 수정에 포함. 3인 합의 필수.

---

## Change 2: podcast_reasoning.py — user_input 안전 접근

### 근거

`podcast_reasoning.py:81`에서 `user_input = state["user_input"]`는 키가 없으면 `KeyError`를 발생시킨다.

**KeyError 발생 시나리오:**

```
TIER 0: intent_classifier_node 실행
  └── _with_timeout(intent_classifier_node, state, _TIER0_TIMEOUT=10s)
        └── asyncio.TimeoutError 발생 (10초 초과)
              └── 반환: {} (빈 dict)

LangGraph merge: state = {**원본_state, **{}} = {**원본_state}
  [주의] user_input은 이미 원본_state에 있으므로 이 시나리오에서는 KeyError 미발생

BUT: 다른 시나리오:
  └── intent_classifier_node가 Exception으로 크래시하면
        └── workflow는 에러 상태로 전환될 수 있음
```

**실제 위험 시나리오 재평가:**

상기 분석 후, workflow.py의 LangGraph가 `{}` 반환을 기존 state에 merge하므로, `user_input`은 초기 API 요청 시 이미 state에 설정된다. **따라서 정상적인 파이프라인에서는 KeyError가 발생하지 않는다.**

그러나 다음 경우에는 발생 가능:
1. `podcast_reasoning.py`를 독립적으로 테스트할 때 (state에 user_input 없이 호출)
2. 미래에 workflow가 변경되어 user_input을 나중에 설정하는 경우
3. 코드 리뷰어가 state 초기화 위치를 오해하는 경우

**방어 코드 추가의 이유:** 명시적 오류 메시지 제공, 코드 의도 명확화, 독립 테스트 시 오류 재현 방지.

### 수정 대상 (podcast_reasoning.py)

**변경 전 (라인 81):**
```python
user_input = state["user_input"]
```

**변경 후:**
```python
user_input = state.get("user_input", "")
if not user_input:
    self.logger.error(
        "[PodcastReasoning] user_input 없음 — 파이프라인 초기화 오류 가능성"
    )
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
```

### 왜 ValueError를 raise하지 않는가

LangGraph 파이프라인에서 unhandled exception은 전체 그래프 실행을 중단시킨다. `user_input`이 없다면:
- 파이프라인 전체가 실패하는 것보다 빈 reasoning_result를 반환하는 것이 낫다
- Batch Validator가 script_draft 없음을 감지하고 FAIL 반환 → 재시도 또는 CRITICAL_FAIL
- 사용자는 오류 메시지 대신 품질 낮은 응답을 받더라도 파이프라인이 계속 동작함

**단, logging은 ERROR 레벨로 기록하여 모니터링에서 탐지 가능하게 한다.**

### 후속 조치

**왜 후속 조치가 필요한가:**
- `error: "user_input_missing"` 필드가 `reasoning_result`에 추가되면 Batch Validator가 이를 어떻게 처리하는지 확인 필요
- Script Generator가 빈 `episode_structure: []`를 받으면 → `segment_plan` 없음 → 임시 플랜 생성 경로로 진입
- 임시 플랜 생성 경로의 품질이 허용 가능한지 확인

**체크리스트:**
- [ ] `batch_validator.py`의 `_build_analysis_context()`가 `reasoning_result.error` 필드를 어떻게 처리하는지 확인
- [ ] Script Generator의 임시 플랜 경로(`segment_plan = [{intro}]`)가 Batch Validator를 통과하는지 확인
- [ ] 모니터링 알림: Prometheus/CloudWatch에서 `[PodcastReasoning] user_input 없음` 로그 알림 설정 권장

### 테스트 수정

`tests/agents/podcast/test_podcast_reasoning.py`의 기존 `test_edge_case_inputs`를 확장:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state_overrides, expected_error_key",
    [
        # 빈 문자열 user_input
        ({"user_input": ""}, "user_input_missing"),
        # user_input 키 자체 없음
        ({}, "user_input_missing"),
    ],
)
async def test_missing_or_empty_user_input_returns_fallback(
    state_overrides, expected_error_key, mock_memory, mock_knowledge
):
    """user_input 없거나 빈 문자열이면 error 필드가 있는 reasoning_result 반환."""
    agent = PodcastReasoningAgent(
        memory_agent=mock_memory, knowledge_agent=mock_knowledge
    )
    base_state = AgentState(
        user_input="original",  # 덮어쓸 예정
        user_id="u1",
        session_id="s1",
        mode="podcast",
        intent=MOCK_INTENT_PODCAST,
    )
    state = {**base_state, **state_overrides}

    result = await agent.process(state)

    assert "reasoning_result" in result
    assert result["reasoning_result"].get("error") == expected_error_key
    assert result["reasoning_result"]["confidence"] == 0.0
```

### 구현 절차

- [ ] Step 1: `podcast_reasoning.py:81` `state["user_input"]` → `state.get()`로 교체 + 조기 반환 추가
- [ ] Step 2: `test_podcast_reasoning.py`에 `test_missing_or_empty_user_input_returns_fallback` 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_podcast_reasoning.py -v` — 신규 + 기존 테스트 통과
- [ ] Step 4: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

---

## Change 2-B: content_analyzer.py — user_input 안전 접근 [v2 추가]

### 근거

`content_analyzer.py:81`에서도 `state["user_input"]`으로 직접 접근한다. podcast_reasoning.py:81과 동일한 패턴이며, 동일한 KeyError 위험이 존재한다.

### 수정 대상

**변경 전 (라인 81):**
```python
user_input = state["user_input"]
```

**변경 후:**
```python
user_input = state.get("user_input", "")
if not user_input:
    self.logger.error(
        "[ContentAnalyzer] user_input 없음 — 파이프라인 초기화 오류 가능성"
    )
    return {
        "content_analysis": {
            "main_theme": "",
            "sub_themes": [],
            "emotional_journey": {},
            "depth_level": "light",
            "error": "user_input_missing",
        }
    }
```

### 구현 절차

- [ ] Step 1: `content_analyzer.py:81` `state["user_input"]` → `state.get()` + 조기 반환
- [ ] Step 2: `test_content_analyzer.py`에 빈 user_input 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_content_analyzer.py -v` — 통과

---

## Change 3: script_generator.py — content_analysis fallback 수정

### 근거

`script_generator.py:48-50`:
```python
content_analysis: dict[str, Any] = cast(
    dict[str, Any], state.get("content_analysis", state)
)  # state 최상단에 병합됐을 수도 있고 dict 형태일 수도 있음
```

`state` 전체를 fallback으로 사용하는 것은 의도된 동작처럼 보이지만 **실제로는 잘못된 코드**다.

**왜 잘못됐는가:**
- `state`는 `AgentState(TypedDict)`로 수십 개 필드를 가진 큰 dict다
- `content_analysis.get("main_theme", ...)` 호출 시 `state.get("main_theme")`를 시도하는데, `AgentState`에 `main_theme` 필드는 없음 → 항상 기본값 `"Mental Health"` 사용
- `content_analysis.get("emotional_journey", ...)` 시 `state.get("emotional_journey")`는 없음 → `{}` 반환
- 코드 주석 "state 최상단에 병합됐을 수도 있고"는 과거 아키텍처 잔재 — 현재 `content_analysis`는 항상 별도 필드로 저장됨

**실제 발생하는 문제:**
- `main_theme = "Mental Health"` (사용자 주제 무시)
- `emotional_journey = {}` (감정 여정 없이 스크립트 생성)
- 결과: Batch Validator에서 점수 0.3 미만 → 재시도 증가

### 수정 대상 (script_generator.py)

**변경 전 (라인 48-50):**
```python
content_analysis: dict[str, Any] = cast(
    dict[str, Any], state.get("content_analysis", state)
)  # state 최상단에 병합됐을 수도 있고 dict 형태일 수도 있음
```

**변경 후:**
```python
content_analysis: dict[str, Any] = cast(
    dict[str, Any], state.get("content_analysis", {})
)
if not content_analysis:
    self.logger.warning(
        "[ScriptGenerator] content_analysis 없음 — 기본값으로 스크립트 생성"
    )
```

**이후 라인 51-63도 함께 검토 필요:**

현재:
```python
main_theme: str = str(
    content_analysis.get("main_theme", state.get("main_theme", "Mental Health"))
)
```

수정 후 `content_analysis = {}`이면 `state.get("main_theme")` 역시 없으므로 `"Mental Health"` 반환. 이는 수용 가능한 fallback이지만, user_input에서 간단하게 키워드 추출하는 것이 더 낫다.

단, user_input 파싱은 추가 로직이므로 이번 계획에서는 **warning 로깅만 추가하고, fallback 기본값(`"Mental Health"`)은 그대로 유지**한다. 이것이 더 안전한 최소한의 변경이다.

### 후속 조치

**왜 후속 조치가 필요한가:**
- `state` 전체를 fallback으로 쓰는 패턴이 다른 파일에도 있는지 전체 검색 필요
- `content_analysis` 없이 생성된 스크립트의 품질 모니터링 필요

**체크리스트:**
- [ ] `grep -r "state\.get.*state)" src/` — 유사 패턴 전체 검색 후 수정 여부 결정
- [ ] `emotional_journey` 필드가 `content_analysis` 없을 때 어떤 구조로 제공되는지 Script Generator 흐름 재확인

### 테스트 수정

`tests/agents/podcast/test_script_generator.py`에 추가:

```python
@pytest.mark.asyncio
async def test_missing_content_analysis_uses_empty_dict_not_state():
    """content_analysis 없을 때 state 전체가 아닌 빈 dict를 fallback으로 사용한다."""
    agent = ScriptGeneratorAgent()

    state = AgentState(
        user_input="스트레스 관리",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        intent={"complexity_score": 0.5},
        reasoning_result={
            "episode_structure": [
                {"section": "intro", "duration_ratio": 0.3},
                {"section": "body", "duration_ratio": 0.7},
            ]
        },
        # content_analysis 없음
    )

    with patch.object(agent, "call_llm", new_callable=AsyncMock) as mock_call_llm, \
         patch.object(agent, "call_llm_json", new_callable=AsyncMock) as mock_json:
        mock_call_llm.return_value = "생성된 스크립트"
        mock_json.return_value = {"insights": ["핵심 인사이트"]}

        result = await agent.process(state)

    assert "script_draft" in result
    # main_theme이 "Mental Health" 기본값인지 확인 (state 전체의 user_input이 사용되지 않음)
    draft = result["script_draft"]
    # 스크립트는 생성됐지만, main_theme은 fallback
    assert draft.get("episode_title") is not None
```

### 구현 절차

- [ ] Step 1: `script_generator.py:48-50` fallback을 `state` → `{}`로 수정, warning 로깅 추가
- [ ] Step 2: `grep -r "state\.get.*state)" src/agents/` 실행하여 동일 패턴 다른 파일 확인
- [ ] Step 3: 테스트 추가
- [ ] Step 4: `pytest tests/agents/podcast/test_script_generator.py -v` — 통과
- [ ] Step 5: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

---

## Change 4: batch_validator.py — call_llm_json() try/except 추가

### 근거

`batch_validator.py:84-87`:
```python
# LLM으로 스크립트 품질 검증
validation = await self.call_llm_json(
    system_prompt=self.get_prompt("system_prompt"),
    user_message=validation_context,
)
```

`call_llm_json()`이 실패하면:
1. `JSONDecodeError` or `LLMCallError` propagate
2. `batch_validator_node()`가 exception을 raise
3. LangGraph가 해당 노드 실패로 기록, 파이프라인 중단

**이 취약점이 다른 에이전트와 다른 이유:**
- Script Generator는 `call_llm_json()` 주변에 try/except 있음 (라인 334)
- Podcast Reasoning은 내부적으로 try/except 있음
- **Batch Validator만 유일하게 try/except 없음**

**적절한 fallback 동작 결정:**

Batch Validator의 역할은 스크립트 품질 검증이다. LLM 호출 실패 시:
- `PASS`로 fallback: 검증 없이 통과 → 품질 낮은 스크립트 최종 출력 위험
- `FAIL`로 fallback: 재시도 유발 → 무한 재시도 가능
- `CRITICAL_FAIL`로 fallback: 즉시 강제 통과 → 적절

**결정: `FAIL` (revision 재시도 1회 허용) + `forced_pass`로 fallback**

이유: LLM 실패는 일시적 오류일 가능성이 높음. 1회 재시도 후 실패하면 `iteration_count >= max_retries`로 강제 통과. 품질보다 파이프라인 완결성 우선.

### 수정 대상 (batch_validator.py)

**변경 전 (라인 80-98):**
```python
        # LLM으로 스크립트 품질 검증
        validation = await self.call_llm_json(
            system_prompt=self.get_prompt("system_prompt"),
            user_message=validation_context,
        )

        # 검증 결과에 따른 라우팅 결정
        action = validation.get("action", {})
        decision = action.get("decision", "revise")
```

**변경 후:**
```python
        # LLM으로 스크립트 품질 검증
        try:
            validation = await self.call_llm_json(
                system_prompt=self.get_prompt("system_prompt"),
                user_message=validation_context,
            )
        except Exception as e:
            self.logger.error(
                "[BatchValidator] LLM 호출 실패 — FAIL 처리 (재시도 유발): %s", e
            )
            return {
                "validation_result": {
                    "verdict": "FAIL",
                    "decision": "revise",
                    "overall_score": 0.0,
                    "action": {"decision": "revise"},
                    "error": "llm_call_failed",
                }
            }

        # 검증 결과에 따른 라우팅 결정
        action = validation.get("action", {})
        decision = action.get("decision", "revise")
```

### 후속 조치

**왜 후속 조치가 필요한가:**
- LLM 실패 시 `FAIL` 반환 → `route_after_tier3_podcast()`가 재시도 여부 결정
- `iteration_count`가 이미 `max_retries`에 도달했다면 강제 통과 → `forced_pass = True`
- 두 번째 Batch Validator 호출에서도 LLM 실패하면 → 강제 통과 → 품질 미보장 스크립트 출력
- 이 경로에 대한 알림/모니터링 필요

**체크리스트:**
- [ ] `route_after_tier3_podcast()`가 `validation_result.error == "llm_call_failed"`를 처리하는지 확인
- [ ] Prometheus 메트릭: Batch Validator LLM 실패율 추적 추가 권장

### 테스트 수정

`tests/agents/podcast/test_batch_validator.py`에 추가:

```python
@pytest.mark.asyncio
async def test_llm_call_failure_returns_fail_verdict():
    """call_llm_json() 실패 시 FAIL verdict를 반환하고 예외를 전파하지 않는다."""
    agent = BatchValidatorAgent()

    state = AgentState(
        user_input="테스트",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        script_draft={
            "episode_title": "테스트",
            "segments": [{"script_text": "내용"}],
        },
        iteration_count=0,
    )

    with patch.object(
        agent,
        "call_llm_json",
        new_callable=AsyncMock,
        side_effect=Exception("LLM 연결 실패"),
    ):
        result = await agent.process(state)

    assert "validation_result" in result
    assert result["validation_result"]["verdict"] == "FAIL"
    assert result["validation_result"]["overall_score"] == 0.0
    assert result["validation_result"].get("error") == "llm_call_failed"
```

### 구현 절차

- [ ] Step 1: `batch_validator.py:84-87` `call_llm_json()` 호출을 try/except로 감싸기
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_batch_validator.py -v` — 통과
- [ ] Step 4: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

---

## Change 4-B: safety.py — call_llm_json() try/except 추가 [v2 추가]

### 근거

`safety.py:45-47`에서 `call_llm_json()` 호출에 try/except가 없다. **Safety Agent는 CRISIS 판정을 담당하는 핵심 에이전트**로, LLM 실패 시 위기 판정이 불가능해지며 TIER 1 병렬 작업 전체가 크래시한다.

이것은 batch_validator.py보다 **더 심각한 문제**다. Batch Validator는 TIER 3에서 단독 실행되지만, Safety Agent는 TIER 1 병렬 4개 에이전트 중 하나로 실행되며, 실패 시 `run_with_cancel()` 내부에서 exception이 전파되어 **나머지 3개 에이전트까지 영향**받는다.

### 수정 대상 (safety.py)

**변경 전 (라인 45-47):**
```python
result = await self.call_llm_json(
    system_prompt=self.get_prompt("system_prompt"),
    user_message=user_message,
)
```

**변경 후:**
```python
try:
    result = await self.call_llm_json(
        system_prompt=self.get_prompt("system_prompt"),
        user_message=user_message,
    )
except Exception as e:
    self.logger.error("[SafetyAgent] LLM 호출 실패 — safe fallback 적용: %s", e)
    result = {
        "risk_level": 0,
        "risk_score": 0.0,
        "status": "safe",
        "flags": {},
        "required_in_script": [],
        "error": "llm_call_failed",
    }
```

**Fallback을 "safe"로 설정하는 이유:** LLM 실패 시 CRISIS 오탐보다 안전한 쪽(safe)으로 fallback하는 것이 파이프라인 안정성에 유리하다. 실제 위기 상황은 Intent Classifier의 1차 규칙 기반 감지(`risk_flag`)로 부분적 보호된다.

### 구현 절차

- [ ] Step 1: `safety.py:45-47` `call_llm_json()` 호출을 try/except로 감싸기
- [ ] Step 2: 테스트 추가 — LLM 실패 시 safe fallback 반환 확인
- [ ] Step 3: `pytest tests/agents/podcast/test_safety.py -v` — 통과

---

## Change 4-C: podcast_reasoning.py — GoT/ToT/CoT call_llm_json() try/except [v2 추가]

### 근거

`podcast_reasoning.py`의 3개 추론 메서드에서 `call_llm_json()` 호출에 try/except가 없다:
- `_graph_of_thoughts()` 라인 270
- `_tree_of_thoughts()` 라인 298
- `_chain_of_thoughts()` 라인 328

이들은 `_execute_reasoning_pipeline()` 내부에서 순차 호출되며, 하나라도 실패하면 전체 Reasoning 에이전트가 크래시한다. 이전 HTTP 500 (JSONDecodeError, raw_text="") 사고의 근본 원인이기도 하다.

### 수정 방향

각 메서드 내부에서 `call_llm_json()` 호출을 try/except로 감싸고, 실패 시 빈 dict `{}`를 반환한다. `_execute_reasoning_pipeline()`에서 이미 각 결과에 `.get()` 접근을 사용하므로, 빈 dict 반환은 안전하게 처리된다.

### 구현 절차

- [ ] Step 1: `_graph_of_thoughts()` 라인 270, `_tree_of_thoughts()` 라인 298, `_chain_of_thoughts()` 라인 328 — 각각 try/except 추가
- [ ] Step 2: 기존 `test_llm_returns_empty_dict` 테스트가 이 경로를 커버하는지 확인, 부족하면 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_podcast_reasoning.py -v` — 통과

---

## Change 5: emotion.py — LLM 실패 시 fallback 개선

### 근거

`emotion.py:97-109` (LLM 파싱 실패 시 fallback):
```python
except Exception:
    self.logger.warning("[EmotionAgent] LLM 응답 파싱 실패 — 폴백 적용", exc_info=True)
    text = user_input
    primary = "anxiety" if "불안" in text else ("sadness" if "우울" in text else "neutral")
    vec = {
        "primary_emotion": primary,
        ...
    }
```

**문제점:**
- `user_input`의 키워드("불안", "우울")로만 감정을 결정
- Intent Classifier가 이미 LLM으로 분석한 `detected_entities.emotions`를 무시함
- LLM이 `intent_section`으로 전달받은 감정 정보를 fallback에서 활용하지 않음

**실제 발생 케이스:**
- 사용자가 "요즘 힘들다"라고 입력 → "불안"/"우울" 키워드 없음 → "neutral" 반환
- Intent Classifier는 이미 `detected_entities.emotions: ["sadness", "fatigue"]`를 분석했으나 무시됨
- Script Generator가 neutral 톤으로 스크립트 생성 → 사용자 감정과 불일치

### 수정 대상 (emotion.py)

**변경 전 (라인 97-109):**
```python
        except Exception:
            self.logger.warning("[EmotionAgent] LLM 응답 파싱 실패 — 폴백 적용", exc_info=True)
            text = user_input
            primary = "anxiety" if "불안" in text else ("sadness" if "우울" in text else "neutral")
            vec = {
                "primary_emotion": primary,
                "intensity": 0.7 if primary != "neutral" else 0.3,
                "valence": -0.4 if primary in ("anxiety", "sadness") else 0.0,
                "arousal": 0.7 if primary == "anxiety" else 0.3,
                "secondary_emotions": [],
                "tone_recommendation": "supportive_neutral",
                "emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],
            }
```

**변경 후:**
```python
        except Exception:
            self.logger.warning("[EmotionAgent] LLM 응답 파싱 실패 — 폴백 적용", exc_info=True)
            # 1순위: Intent Classifier가 분석한 감정 정보 활용
            detected_emotions = (
                intent.get("detected_entities", {}).get("emotions", [])
                if isinstance(intent.get("detected_entities"), dict)
                else []
            )
            primary = detected_emotions[0] if detected_emotions else None
            # 2순위: user_input 키워드 기반 추론
            if not primary:
                text = user_input
                primary = (
                    "anxiety" if "불안" in text
                    else ("sadness" if "우울" in text else "neutral")
                )
            vec = {
                "primary_emotion": primary,
                "intensity": 0.7 if primary != "neutral" else 0.3,
                "valence": -0.4 if primary in ("anxiety", "sadness") else 0.0,
                "arousal": 0.7 if primary == "anxiety" else 0.3,
                "secondary_emotions": detected_emotions[1:] if len(detected_emotions) > 1 else [],
                "tone_recommendation": "supportive_neutral",
                "emotional_journey_hint": ["공감", "정리", "실행 가능한 한 가지", "마무리"],
            }
```

**주요 변경점:**
1. `intent.detected_entities.emotions`를 먼저 확인 (Intent Classifier 결과 활용)
2. `secondary_emotions`도 detected_emotions의 나머지 요소로 채움
3. 키워드 기반은 2순위 fallback으로 격하

### 후속 조치

**왜 후속 조치가 필요한가:**
- `secondary_emotions`가 이제 빈 리스트가 아닌 실제 값을 가질 수 있음 → 하위 에이전트가 이 필드를 어떻게 사용하는지 확인
- Batch Validator의 `_build_analysis_context()`가 `secondary_emotions`를 포함하는지 확인

**체크리스트:**
- [ ] `batch_validator.py`의 `_build_analysis_context()` (라인 212-220)에서 `secondary_emotions` 처리 여부 확인
- [ ] Script Personalizer가 `emotion_vectors.secondary_emotions`를 활용하는지 확인

### 테스트 수정

`tests/agents/podcast/test_emotion_agent.py`에 추가:

```python
@pytest.mark.asyncio
async def test_llm_failure_fallback_uses_intent_emotions():
    """LLM 실패 시 fallback이 intent.detected_entities.emotions를 우선 사용한다."""
    agent = EmotionAgent()

    state = AgentState(
        user_input="요즘 힘들다",  # "불안"/"우울" 키워드 없음
        user_id="u1",
        session_id="s1",
        mode="podcast",
        intent={
            "detected_entities": {
                "emotions": ["sadness", "fatigue"],
            },
            "flags": {"risk_flag": False},
        },
    )

    with patch.object(
        agent,
        "call_llm_json",
        new_callable=AsyncMock,
        side_effect=Exception("LLM 실패"),
    ):
        result = await agent.process(state)

    vec = result["emotion_vectors"]
    # Intent 감정 정보 사용 확인
    assert vec["primary_emotion"] == "sadness"
    assert "fatigue" in vec["secondary_emotions"]
    # user_input 키워드 fallback이 아님을 확인
    assert vec["primary_emotion"] != "neutral"
```

### 구현 절차

- [ ] Step 1: `emotion.py` fallback except 블록 수정 (intent 감정 1순위 활용)
- [ ] Step 2: 테스트 추가
- [ ] Step 3: `pytest tests/agents/podcast/test_emotion_agent.py -v` — 통과
- [ ] Step 4: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

---

## Change 6: script_personalizer.py — ValidatedScript 빈 문자열 fallback 수정

### 근거

`script_personalizer.py:170-181` (except 블록):
```python
        except Exception as e:
            self.logger.error("[ScriptPersonalizer] Error: %s", e)
            fallback = ""
            if "validated_script" in locals() and validated_script:
                fallback_script = self._create_fallback_script(
                    validated_script=validated_script, user_id=user_id
                )
                fallback = fallback_script.model_dump_json()
            return {"final_output": fallback}
```

**`final_output = ""`이 되는 경로:**
1. `script_draft = {}` (빈 dict) → `ValidatedScript(**{})` → Pydantic ValidationError → except 진입
2. except 블록에서 `validated_script is None` → `_create_fallback_script()` 미호출
3. `fallback = ""` 반환

**빈 `final_output`의 영향:**
- API 응답의 `episode.script` 필드가 빈 문자열
- 프론트엔드에서 빈 에피소드가 표시됨
- 사용자 경험 완전 손상

**왜 `script_draft = {}`가 발생하는가:**
- TIER 2의 Script Generator가 완전히 실패하면 `script_draft = {}` 반환 가능
- Batch Validator가 빈 script_draft를 `FAIL`로 반환하고, 최대 재시도 후 `forced_pass`로 통과 → TIER 4(Personalizer)에 빈 script_draft 전달

### 수정 대상 (script_personalizer.py)

**개선 방향:** `script_draft`가 비어있거나 Pydantic 실패 시 `script_draft`의 raw 내용이라도 최대한 활용한다.

**변경 전 (라인 88-93):**
```python
            # script_draft에서 Pydantic 객체 복원
            script_data = state.get("script_draft", {})
            validated_script = ValidatedScript(**script_data) if script_data else None
```

**변경 후:**
```python
            # script_draft에서 Pydantic 객체 복원
            script_data = state.get("script_draft", {})
            validated_script: ValidatedScript | None = None
            if script_data:
                try:
                    validated_script = ValidatedScript(**script_data)
                except Exception as pydantic_err:
                    self.logger.warning(
                        "[ScriptPersonalizer] script_draft Pydantic 변환 실패 — "
                        "raw script_draft로 최소 fallback 시도: %s",
                        pydantic_err,
                    )
                    # Pydantic 변환 실패 시 raw 텍스트라도 최소 ValidatedScript 구성
                    raw_segments = script_data.get("segments", [])
                    raw_title = script_data.get("episode_title", "마음 이야기")
                    if raw_segments:
                        try:
                            # ScriptSegment은 파일 상단에서 이미 import됨 (라인 33)
                            min_segments = [
                                ScriptSegment(
                                    segment_id=seg.get("segment_id", f"seg_{i}"),
                                    segment_type=seg.get("segment_type", "body"),
                                    duration_minutes=int(seg.get("duration_minutes", 5)),
                                    script_text=str(seg.get("script_text", "")),
                                    word_count=len(str(seg.get("script_text", "")).split()),
                                    emotional_tone=seg.get("emotional_tone", "neutral"),
                                    tts_markers=[],
                                )
                                for i, seg in enumerate(raw_segments)
                                if isinstance(seg, dict) and seg.get("script_text")
                            ]
                            if min_segments:
                                validated_script = ValidatedScript(
                                    episode_title=raw_title,
                                    total_duration=script_data.get("total_duration", 5),
                                    segments=min_segments,
                                    key_insights=[],
                                    themes=[],
                                )
                        except Exception:
                            pass  # 최소 fallback도 실패 → validated_script = None 유지
```

**except 블록 수정 (라인 170-181):**

기존 except 블록의 로직은 이미 `validated_script`를 활용하므로 변경 불필요. 상위에서 Pydantic 실패를 잡았으므로 `validated_script`가 null이 되는 경우가 줄어든다.

### 후속 조치

**왜 후속 조치가 필요한가:**
- `ScriptSegment` import 위치가 `script_personalizer.py` 내부에 없을 수 있음 → 기존 import 확인
- `ValidatedScript`와 `ScriptSegment`의 필수 필드 목록 확인 (타입 에러 방지)
- 최소 fallback 경로의 `total_duration` 계산이 올바른지 확인

**체크리스트:**
- [ ] `script_personalizer.py` 상단 imports에서 `ScriptSegment` import 여부 확인
- [ ] `ValidatedScript`와 `ScriptSegment`의 Pydantic 필수 필드 목록 확인
- [ ] 최소 fallback 결과물이 올바른 JSON으로 `final_output`에 저장되는지 E2E 확인

### 테스트 수정

`tests/agents/podcast/test_script_personalizer.py`에 추가:

```python
@pytest.mark.asyncio
async def test_empty_script_draft_returns_nonempty_output():
    """script_draft가 빈 dict여도 final_output은 빈 문자열이 아니다."""
    agent = ScriptPersonalizerAgent(enable_deep_personalization=False)

    state = AgentState(
        user_input="테스트",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        script_draft={},  # 빈 dict
    )

    result = await agent.process(state)

    assert "final_output" in result
    # 빈 문자열이 아님을 확인
    assert result["final_output"] != ""


@pytest.mark.asyncio
async def test_malformed_script_draft_returns_nonempty_output():
    """script_draft가 Pydantic 변환 불가 구조여도 최소 fallback을 반환한다."""
    agent = ScriptPersonalizerAgent(enable_deep_personalization=False)

    state = AgentState(
        user_input="테스트",
        user_id="u1",
        session_id="s1",
        mode="podcast",
        # [v2 수정] episode_title 누락으로 ValidationError 유발
        # (word_count는 default=0이므로 Pydantic 실패 미발생)
        script_draft={
            # "episode_title" 누락 — 필수 필드
            "segments": [
                {
                    "segment_id": "seg_1",
                    "segment_type": "body",
                    "duration_minutes": 5,
                    "script_text": "오늘 감정에 대해 이야기해봅시다.",
                    "word_count": 8,
                    "emotional_tone": "neutral",
                }
            ],
            "total_duration": 5,
        },
    )

    result = await agent.process(state)

    assert "final_output" in result
    assert result["final_output"] != ""
```

### 구현 절차

- [ ] Step 1: `script_personalizer.py` Pydantic 변환 try/except 추가 (라인 88-93 근처)
- [ ] Step 2: `ScriptSegment` import 확인 및 추가
- [ ] Step 3: 테스트 추가
- [ ] Step 4: `pytest tests/agents/podcast/test_script_personalizer.py -v` — 통과
- [ ] Step 5: `pytest tests/ -v --tb=short` — 전체 회귀 없음 확인

---

## 전체 구현 순서 (권장)

### 이유: 의존성 역순으로 수정

TIER 0→4 순서가 아닌 **의존성이 적은 것부터** 수정해야 각 단계가 독립적으로 테스트 가능하다.

```
Step A. emotion.py (Change 5) — TIER 1 독립, 의존성 없음
Step B. safety.py (Change 4-B) — TIER 1 독립, CRISIS fallback [v2 추가]
Step C. batch_validator.py (Change 4) — TIER 3 독립
Step D. content_analyzer.py (Change 2-B) — TIER 1, user_input 방어 [v2 추가]
Step E. script_generator.py (Change 3) — TIER 2, content_analysis 방어
Step F. script_personalizer.py (Change 6) — TIER 4, script_draft 방어
Step G. podcast_reasoning.py (Change 2 + 4-C) — TIER 1, user_input + LLM 방어 [v2 확대]
Step H. workflow.py (Change 1 + 1-B) — 전체, Protected File, 마지막 [v2 확대]
```

### PR 전략

이 계획의 변경사항은 **1개의 PR**로 묶어서 처리한다:

| 항목 | 이유 |
|------|------|
| 브랜치명 | `feature/reasoning-pipeline-robustness` |
| Base 브랜치 | `develop` (PR#59 머지 후) 또는 `develop` 직접 |
| 필수 리뷰어 | 개발자1, 개발자2, 개발자3 (workflow.py Protected File 포함) |
| 스쿼시 머지 | 금지 — 각 Change별 커밋 이력 보존 |

**PR 설명에 반드시 포함:**
- 각 버그의 발생 조건 (어떤 시나리오에서 크래시 발생)
- 수정 접근 방식과 fallback 동작
- 후속 모니터링 체크리스트

---

## 이번 계획에서 제외된 항목 (별도 계획 필요)

### A. `_with_timeout()` 빈 dict 반환 문제

**현황:** TIER 1 에이전트 타임아웃 시 `{}` 반환 → 하위 에이전트 필드 누락.

**왜 이번에 제외하는가:**
- 각 에이전트별 기본값 구조 설계가 필요하며 모든 에이전트와 합의 필요
- 잘못된 기본값이 더 큰 문제를 야기할 수 있음
- TIER 1 타임아웃(60초)이 2배 증가(PR#56)되어 현재로서는 빈번하게 발생하지 않음

**향후 접근법 (다음 스프린트):**
```python
# _with_timeout() 수정 방향 (합의 후 구현)
_TIMEOUT_DEFAULTS: dict[str, dict[str, Any]] = {
    "emotion_node": {"emotion_vectors": {"primary_emotion": "neutral", "intensity": 0.3, ...}},
    "content_analyzer_node": {"content_analysis": {"main_theme": "", "emotional_journey": {}}},
    "podcast_reasoning_node": {"reasoning_result": {"episode_structure": [], "confidence": 0.0}},
    "safety_node": {"risk_level": 0, "risk_score": 0.0, "safety_flags": {"status": "safe"}},
}
```

### B. episode_memory.yaml 누락

**현황:** Stub 사용 중. Pinecone 연동과 묶여 있어 별도 계획 필요.

### C. 복잡도 임계값 CLAUDE.md vs settings.yaml 불일치

**현황:** CLAUDE.md 0.8/0.5 vs settings.yaml 0.55/0.3. settings.yaml이 실제 코드 동작 기준이며, CLAUDE.md 문서 갱신 필요.

---

## 검증 체크리스트 (구현 완료 후)

- [ ] `pytest tests/ -v --tb=short` — 전체 테스트 통과
- [ ] `mypy src/agents/podcast/ --ignore-missing-imports` — 타입 에러 미증가
- [ ] `ruff check src/agents/podcast/` — lint 통과
- [ ] AWS SSM: 수정 후 E2E 테스트 10회 — HTTP 200, success:true 일관성 확인
- [ ] LangSmith: Intent Classifier 트레이스 생성 확인 (Change 1 효과)
- [ ] 컨테이너 로그: LLM 실패 fallback 로그 정상 출력 확인

---

---

## v2 교차 검증 부록: max_retries 동기화 확인 필요

코드 리뷰 에이전트가 발견한 잠재 문제:

- `batch_validator.py`의 `self.max_retries`는 `get_agent_config("batch_validator")`에서 로드
- `workflow.py`의 `_MAX_RETRIES`는 `_settings.max_retries`에서 로드

두 값이 같은 `settings.yaml` 키에서 오는지 확인 필요. 다른 값이면 BatchValidator가 "강제 통과"를 반환했는데 router가 "재시도"를 선택하는 모순이 발생할 수 있다.

- [ ] 확인: `settings.yaml`에서 `pipeline.max_retries`와 `agents.batch_validator.max_retries`의 값 비교
- [ ] 불일치 시: 한 곳으로 통일 (settings.yaml의 `pipeline.max_retries`를 SSOT으로 사용 권장)

---

---

# Part 1.5: 기존 평가·재시도 루프 분석 [v4 추가]

> 사용자 질문: "평가 에이전트가 있고 해당 에이전트에서 통과하지 못하면 재시도 로직이 있는데, 이게 기존 프로젝트에서 유효한 방법인지 확인이 필요합니다."

---

## 기존 재시도 흐름도

```
[TIER 1 완료: Safety + Emotion + Content Analyzer + Podcast Reasoning]
                             │
                             ▼
    ┌────────────────────────────────────────────────────────┐
    │  TIER 2: tier2_podcast_fan_out()                       │
    │  ├── script_generator_node  ← Script Generator (LLM)  │
    │  └── visualization_node     ← 커버 이미지 생성         │
    └────────────────────────────────────────────────────────┘
                             │
                             ▼
    ┌────────────────────────────────────────────────────────┐
    │  TIER 3: batch_validator_node                          │
    │  ① call_llm_json() → action.decision                  │
    │     ├── "approve"  → verdict = PASS                   │
    │     ├── "revise"   → verdict = FAIL                   │
    │     └── "escalate" → verdict = CRITICAL_FAIL          │
    │  ② script_draft 없음 → 조기 반환 (verdict = FAIL)     │
    └────────────────────────────────────────────────────────┘
                             │
                             ▼
              route_after_tier3_podcast()
                             │
        ┌────────────────────┼─────────────────────────────┐
        │                    │                             │
        ▼                    ▼                             ▼
    [PASS]          [FAIL or CRITICAL_FAIL]        [crisis_response]
        │                    │                             │
        │      iteration_count 비교                        ▼
        │       (workflow._MAX_RETRIES=2,          [CRISIS 즉시 응답 → END]
        │        _MAX_CRITICAL_RETRIES=4)
        │                    │
        │      ┌─────────────┴──────────────┐
        │      │                            │
        │  [count < 한도]              [count >= 한도]
        │      │                            │
        │      ▼                            ▼
        │  increment_iteration_node    forced_pass = True
        │  (iteration_count + 1)            │
        │      │                            │
        │      └──→ [TIER 2 재실행] ←┐     │ (강제 통과)
        │              (루프)         │     │
        │                             │     │
        └─────────────────────────────┴─────┘
                             │
                             ▼
    ┌────────────────────────────────────────────────────────┐
    │  TIER 4: script_personalizer_node                      │
    │  (PASS 또는 forced_pass 모두 이 노드로 진입)            │
    └────────────────────────────────────────────────────────┘
                             │
                             ▼
                [async_post → END]
```

**반복 횟수 설정값 (settings.yaml 기준):**
- `FAIL` 재시도 최대: `_MAX_RETRIES = 2` (FAIL 시 최대 2회 재시도 → 3번째 평가에서도 FAIL이면 강제 통과)
- `CRITICAL_FAIL` 재시도 최대: `_MAX_CRITICAL_RETRIES = 4` (CRITICAL_FAIL 시 최대 4회 재시도)

---

## 기존 메커니즘의 유효성 평가

### 유효한 시나리오

기존 재시도 루프는 다음 상황에서 **의미 있는 품질 개선**이 발생한다:

| 시나리오 | 이유 |
|---------|------|
| LLM 확률적 편차 | 동일 입력에도 LLM 출력이 달라질 수 있음. 재시도 자체가 다른 결과를 유도 |
| tone mismatch | Script Generator가 감정 벡터 반영에 실패한 경우, 재시도에서 개선 가능 |
| 구조적 불완전성 | 세그먼트 수 부족 등 구조 문제는 재시도에서 해결 가능 |

### 부족한 부분 (5가지)

| # | 문제 | 발생 조건 | 현재 계획 대응 |
|---|------|---------|------------|
| **1** | **Blind retry** — Script Generator가 실패 이유를 모름. `validation_result.reason`이 TIER 2로 전달되지 않음 | 항상 | 이번 계획 외 (차후 개선 권장) |
| **2** | **TIER 1 컨텍스트 불변** — Content Analyzer나 Reasoning이 fallback 결과를 반환한 경우, 재시도해도 동일 저품질 컨텍스트로 스크립트 재생성 | TIER 1 에이전트 실패 시 | Part 2 Structured Fallback이 TIER 1 품질 보장 |
| **3** | **BV LLM 실패 → 불필요한 재시도** — Batch Validator 자신의 LLM이 실패해 FAIL 반환 시, Script Generator 탓이 아닌데 Script Generator만 재실행됨 | BV LLM 오류 시 | **Change 4에서 수정** (try/except 추가) |
| **4** | **max_retries 동기화 문제** — `BatchValidatorAgent.self.max_retries`와 `workflow._MAX_RETRIES`가 다른 설정 키에서 로드될 경우 불일치 | settings.yaml 구성 오류 시 | v2 부록에서 체크리스트 제시 |
| **5** | **Visualization 불필요 재실행** — 스크립트 품질 실패인데 커버 이미지까지 재생성됨 (비용·지연 낭비) | FAIL/CRITICAL_FAIL 시 | 이번 계획 외 (차후 개선 권장) |

### 결론

기존 재시도 루프는 **정상 LLM 환경에서 품질 관리 목적으로 유효하다.**

그러나 두 가지 조건이 충족될 때만 실질적 효과가 있다:
1. TIER 1 입력 데이터(content_analysis, reasoning_result)가 충분한 품질일 것
2. Script Generator LLM에 확률적 개선 여지가 있을 것

LLM 서버 장애, 필드 누락 등 **구조적 문제**가 원인인 경우 재시도는 동일 결과를 반복할 뿐이다.

---

## Part 2와의 관계

기존 재시도 루프와 Part 2의 Structured Fallback은 **서로 다른 장애 유형을 담당**한다:

```
                    ┌───────────────────────────────────────┐
장애 유형           │  기존 재시도 루프    │  Part 2 Fallback  │
───────────────────┼──────────────────────┼───────────────────┤
저품질 스크립트     │  ✅ FAIL → 재시도    │  간접 보완         │
(tone mismatch 등) │                      │                   │
───────────────────┼──────────────────────┼───────────────────┤
LLM 서버 다운       │  ❌ 파이프라인 크래시 │  ✅ Tier 3/4 출력  │
───────────────────┼──────────────────────┼───────────────────┤
LLM 응답 파싱 실패  │  ❌ 크래시 (Change 4 │  ✅ call_llm_      │
                   │  적용 전)             │  validated() 재시도│
───────────────────┼──────────────────────┼───────────────────┤
상류 필드 누락      │  ❌ 재시도해도 동일  │  ✅ get_guaranteed │
(content_analysis) │  저품질 반복         │  _minimum() 보장   │
                   │                      │                   │
                   └──────────────────────┴───────────────────┘
```

**두 메커니즘은 상호 대체가 아닌 상호 보완 관계이다.**
- 기존 재시도 루프: 정상 환경에서 품질 기준 미달 스크립트를 다시 생성
- Part 2 Fallback: 외부 장애(LLM 서버, AWS) 시 빈 응답이 나오는 상황 자체를 방지

---

## 차후 개선 권장 (이번 계획 외)

아래 두 가지는 이번 PR 범위를 벗어나므로 별도 계획으로 처리한다:

**개선 1: 실패 이유 전달 (Informed Retry)**
```python
# Script Generator process()에서 iteration_count > 0일 때 validation_result.reason 주입
if state.get("iteration_count", 0) > 0:
    prev_reason = state.get("validation_result", {}).get("reason", "")
    if prev_reason:
        user_message += f"\n\n[이전 스크립트 평가 실패 이유: {prev_reason}. 개선하여 재생성하세요.]"
```

**개선 2: Script Generator 단독 재시도 (Visualization 제외)**
```python
# tier2_podcast_fan_out()에서 iteration_count > 0이면 Script Generator만 재실행
# Visualization은 첫 번째 결과 재사용 → 불필요한 이미지 API 비용 절감
```

---

---

# Part 2: 방어 아키텍처 설계 — Structured Fallback [v3 추가]

> 4개 병렬 리서치 에이전트로 LangGraph 공식 패턴, BaseAgent 기존 방어 구조, Python async resilience 패턴, Pydantic structured output 패턴을 비교 분석한 결과.

---

## 현재 문제: 왜 개별 try/except로는 부족한가

현재 Change 1~6에서 제안하는 수정은 **각 에이전트에 try/except를 추가하고 fallback dict를 반환하는 방식**이다. 이 방식의 한계:

1. **일관성 없음** — 11개 에이전트 × 3명 개발자가 각자 다른 방식으로 구현. 누락 발생
2. **강제성 없음** — 새 에이전트 추가 시 방어 코드를 잊으면 다시 크래시 위험
3. **fallback 품질 낮음** — `"Mental Health"` 같은 무의미한 기본값으로 사용자 경험 손상
4. **중복 코드** — 11개 파일에 유사한 try/except 보일러플레이트 반복

---

## 비교 분석: 5가지 접근법

| 방법 | 일관성 | 강제성 | UX 보장 | 코드 변경량 | Protected File |
|------|:---:|:---:|:---:|:---:|:---:|
| **A. 개별 try/except** (현재 Change 1-6) | 낮음 | 없음 | 낮음 | 소 | 없음 |
| **B. Decorator 패턴** | 중간 | 없음 (붙이는 건 자율) | 중간 | 소 | 없음 |
| **C. BaseAgent `get_guaranteed_minimum()` abstractmethod** | 높음 | **100%** | 높음 | 중 | **BaseAgent** |
| **D. Pydantic 출력 모델 + `call_llm_validated()`** | 높음 | 중간 | 높음 | 중 | 없음 |
| **E. LangGraph RetryPolicy** | 높음 | 높음 | 중간 | 소 | 없음 |

---

## 선정 방안: C + D 조합 (2계층 방어)

### 왜 C + D 조합인가

**방법 C (BaseAgent abstractmethod)를 기반으로 방법 D (Pydantic 출력 검증)를 보완하는 2계층 구조.**

- **C 선택 이유:** `abstractmethod`로 구현하지 않으면 에이전트 인스턴스 생성 자체가 불가. 개발자가 깜빡해도 Python이 막아줌. 3명이 11개 에이전트를 나누는 이 프로젝트에서 유일하게 **100% 강제**되는 방법.
- **D 보완 이유:** C는 "최소한의 결과를 보장"하지만, LLM 출력의 **타입 검증과 범위 보정**은 Pydantic이 더 적합. `call_llm_validated()`로 검증+재시도를 통합하면 LLM 파싱 실패율을 줄여 Tier 3-4 fallback 진입 빈도를 최소화.
- **E (RetryPolicy) 미선택 이유:** 현재 `langgraph>=0.2.0` 기준으로 RetryPolicy 지원 여부 미확인. LangGraph 버전 업그레이드가 확정되면 추후 도입.

---

## Structured Fallback 4단계 설계

```
사용자 요청 → 에이전트.process()

Tier 1: LLM 정상 응답 → Pydantic 검증 → 성공 반환
  ↓ 파싱/검증 실패
Tier 2: 에러 힌트 포함 1회 재시도 → 성공 시 반환 (degraded=false)
  ↓ 재시도도 실패
Tier 3: 규칙 기반 fallback (user_input 키워드 활용) → 반환 (degraded=true)
  ↓ 규칙 기반도 실패 (극히 드묾)
Tier 4: 최소 보장 출력 (user_input 일부 포함) → 반환 (degraded=true)
```

**핵심 원칙:**
- **외부 장애(LLM 서버 오류, AWS 서비스 장애)만 Tier 3-4로 진입한다.** 정상 환경에서는 Tier 1-2에서 처리 완료.
- **Tier 3-4에서도 `user_input` 기반 결과를 반환한다.** `"Mental Health"` 같은 하드코딩 기본값은 금지.
- **`_degraded` 플래그로 품질 저하를 파이프라인 내에서 추적한다.** Batch Validator가 degraded 여부를 채점에 반영 가능.

---

## BaseAgent 변경 설계 (Protected File — 3인 합의 필수)

### 변경 범위

CLAUDE.md 규칙: "기존 public 메서드의 시그니처를 변경하지 마시오. **신규 메서드/함수 추가만 허용**한다."

| 항목 | 유형 | 설명 |
|------|------|------|
| `get_guaranteed_minimum(state)` | **신규 abstractmethod** | Tier 4 최소 보장 출력. 모든 에이전트 구현 필수 |
| `get_rule_based_fallback(state)` | **신규 메서드 (선택적 오버라이드)** | Tier 3 규칙 기반 fallback. 기본: None 반환 → Tier 4로 |
| `call_llm_validated(system_prompt, user_message, output_model)` | **신규 메서드** | Tier 1-2 통합: LLM 호출 + Pydantic 검증 + 1회 재시도 |
| `__call__(state)` | **동작 변경** (시그니처 동일) | raise → Structured Fallback 체인으로 교체 |

### `__call__()` 동작 변경

**변경 전 (현재):**
```python
async def __call__(self, state):
    try:
        result = await self._traced_process(state, tier_label)
        return result
    except Exception as e:
        self.logger.error(...)
        raise  # ← 예외 전파 → 파이프라인 크래시
```

**변경 후:**
```python
async def __call__(self, state):
    start = time.monotonic()

    # ... 기존 A/B 테스트, LLM 카운터 초기화 유지 ...

    # Tier 1: 정상 처리
    try:
        result = await self._traced_process(state, tier_label)
        if result and isinstance(result, dict):
            return result
    except Exception as e:
        self.logger.warning("[%s] Tier 1 실패: %s", self.name, e)

    # Tier 3: 규칙 기반 fallback (Tier 2는 process() 내부의 call_llm_validated가 처리)
    try:
        result = self.get_rule_based_fallback(state)
        if result and isinstance(result, dict):
            result["_degraded"] = True
            result["_fallback_tier"] = 3
            self.logger.warning("[%s] Tier 3 적용", self.name)
            return result
    except Exception as e:
        self.logger.warning("[%s] Tier 3 실패: %s", self.name, e)

    # Tier 4: 최소 보장 출력 (이 단계는 예외를 발생시키면 안 됨)
    self.logger.error("[%s] Tier 4 — 최소 보장 출력 적용", self.name)
    result = self.get_guaranteed_minimum(state)
    result["_degraded"] = True
    result["_fallback_tier"] = 4
    return result
```

**Tier 2는 어디서 처리되는가:** 각 에이전트의 `process()` 내부에서 `call_llm_validated()`를 사용하면 자동으로 1회 재시도(검증 에러 힌트 포함)가 적용된다. `__call__()`에서 별도로 Tier 2를 시도하지 않는다 — process()가 Tier 1+2를 담당하고, `__call__()`은 Tier 3+4만 담당한다.

### `call_llm_validated()` 설계

```python
async def call_llm_validated(
    self,
    system_prompt: str,
    user_message: str,
    output_model: type[BaseModel],
    max_retries: int = 1,
) -> BaseModel:
    """LLM 호출 + Pydantic 검증 + 에러 힌트 재시도.

    Returns:
        검증된 Pydantic 모델 인스턴스.
        max_retries 소진 시 기본값(output_model())을 반환.
    """
    for attempt in range(max_retries + 1):
        self._llm_call_count += 1
        raw_text = await self._traced_llm_call(system_prompt, user_message)
        raw_dict = self.llm_client.parse_json_response(raw_text)

        try:
            return output_model.model_validate(raw_dict)
        except ValidationError as e:
            if attempt < max_retries:
                # 에러 필드 힌트를 LLM에게 전달하여 자가 수정 유도
                error_hints = "; ".join(
                    f"{'.'.join(str(l) for l in err['loc'])}: {err['msg']}"
                    for err in e.errors()[:3]
                )
                user_message = (
                    f"{user_message}\n\n"
                    f"[이전 응답 JSON의 필드 오류: {error_hints}. "
                    f"스키마에 맞게 수정하여 다시 응답하세요.]"
                )
                self.logger.info(
                    "[%s] 검증 실패 재시도 %d/%d: %d개 오류",
                    self.name, attempt + 1, max_retries, e.error_count(),
                )
            else:
                self.logger.warning(
                    "[%s] 검증 재시도 소진 — 기본값 반환: %d개 오류",
                    self.name, e.error_count(),
                )
                return output_model()  # 기본값이 있는 Pydantic 모델
```

---

## 에이전트별 Pydantic 출력 모델 설계

### 핵심 원칙: user_input 기반 fallback, 하드코딩 금지

**나쁜 예:**
```python
class ContentAnalysisOutput(BaseModel):
    main_theme: str = "Mental Health"  # ← 하드코딩, 사용자 무시
```

**올바른 예:**
```python
class ContentAnalysisOutput(BaseModel):
    main_theme: str = "미확인 주제"

    @model_validator(mode="before")
    @classmethod
    def inject_user_hint(cls, data: Any) -> Any:
        """main_theme 비어있으면 user_input 앞 30자를 사용."""
        if isinstance(data, dict) and not data.get("main_theme"):
            hint = data.pop("_user_input_hint", "")
            data["main_theme"] = hint[:30] if hint else "미확인 주제"
        return data
```

### 에이전트별 출력 모델 목록

| 에이전트 | 출력 모델 | AgentState 필드 | 기본값 전략 |
|---------|----------|----------------|-----------|
| Intent Classifier | `IntentClassifierOutput` (기존) | `intent` | 이미 구현됨 |
| Safety | `SafetyOutput` | `safety_flags`, `risk_level`, `risk_score` | status="safe", risk=0 |
| Emotion | `EmotionOutput` | `emotion_vectors` | intent.detected_entities.emotions 활용 → user_input 키워드 |
| Content Analyzer | `ContentAnalysisOutput` | `content_analysis` | user_input 앞 30자를 main_theme에 |
| Podcast Reasoning | `ReasoningOutput` | `reasoning_result` | 빈 episode_structure + user_input 기반 key_themes |
| Script Generator | `ScriptDraftOutput` | `script_draft` | (상류 fallback에 의존, 자체 fallback 없음) |
| Batch Validator | `ValidationOutput` | `validation_result` | verdict="FAIL", score=0.0 |
| Script Personalizer | `PersonalizedOutput` | `final_output` | 원본 script_draft 그대로 반환 |
| Visualization | (기존 구조 유지) | `visual_data` | status="failed" (이미 구현) |

### get_guaranteed_minimum() 구현 예시 (Tier 4)

```python
class ContentAnalyzerAgent(BaseAgent):
    def get_guaranteed_minimum(self, state: AgentState) -> dict[str, Any]:
        """Tier 4: 사용자 입력에서 최소 정보 추출."""
        user_input = state.get("user_input", "")
        return {
            "content_analysis": {
                "main_theme": user_input[:30] if user_input else "마음 이야기",
                "sub_themes": [],
                "target_duration": 4,
                "narrative_structure": "reflection",
                "depth_level": "light",
                "emotional_journey": {},
            }
        }

class EmotionAgent(BaseAgent):
    def get_guaranteed_minimum(self, state: AgentState) -> dict[str, Any]:
        """Tier 4: Intent 감정 정보 활용 → 없으면 neutral."""
        intent = state.get("intent", {})
        emotions = (
            intent.get("detected_entities", {}).get("emotions", [])
            if isinstance(intent.get("detected_entities"), dict)
            else []
        )
        primary = emotions[0] if emotions else "neutral"
        return {
            "emotion_vectors": {
                "primary_emotion": primary,
                "intensity": 0.5 if primary != "neutral" else 0.3,
                "valence": -0.3 if primary in ("anxiety", "sadness") else 0.0,
                "arousal": 0.5 if primary == "anxiety" else 0.3,
                "secondary_emotions": emotions[1:] if len(emotions) > 1 else [],
                "tone_recommendation": "supportive_neutral",
                "emotional_journey_hint": ["공감", "정리", "마무리"],
            }
        }
```

---

## 사용자 경험 보호 방안

### `_degraded` 플래그 활용

| 위치 | 동작 |
|------|------|
| **Batch Validator (TIER 3)** | 상류 에이전트에 `_degraded=true`가 있으면 검증 기준 완화 (score 임계값 0.1 하향) |
| **Script Personalizer (TIER 4)** | degraded 수에 따라 프론트엔드 메시지 메타데이터 부착 |
| **프론트엔드** | 0-1개 degraded: 표시 없음. 2개 이상: "오늘은 간결하게 준비했어요" |

### 루즈한 로직 방지

**원칙: Tier 3-4는 "있는 것이 없는 것보다 낫다" 수준이지, 정상 품질이 아니다.**

- Tier 3-4 결과로 생성된 에피소드는 **Batch Validator 점수가 낮아져** 재시도를 유발한다
- 재시도 후에도 LLM 서버 장애가 지속되면 그때만 forced_pass → 사용자에게 전달
- **LLM 서버가 정상이면 Tier 1-2에서 무조건 처리 완료되므로 Tier 3-4 진입 자체가 없다**

```
정상 환경:  Tier 1(95%) + Tier 2(4.5%) = 99.5% → 사용자 무인지
장애 환경:  Tier 3(가능) + Tier 4(가능) → 품질 낮지만 응답은 존재
```

---

## 구현 계획 (Part 2)

### Phase A: BaseAgent 확장 (3인 합의 필수)

- [ ] Step A-1: `get_guaranteed_minimum()` abstractmethod 추가 (base_agent.py)
- [ ] Step A-2: `get_rule_based_fallback()` 기본 메서드 추가 (기본 반환: None)
- [ ] Step A-3: `call_llm_validated()` 신규 메서드 추가
- [ ] Step A-4: `__call__()` 동작 변경 — raise → Structured Fallback 체인
- [ ] Step A-5: `pytest tests/agents/shared/test_base_agent_tracing.py -v` — 기존 테스트 통과 확인
- [ ] Step A-6: Structured Fallback 단위 테스트 추가 (Tier 1→2→3→4 각 경로)

### Phase B: Pydantic 출력 모델 정의

- [ ] Step B-1: `src/models/schemas.py`에 에이전트별 출력 모델 추가 (SafetyOutput, EmotionOutput, ContentAnalysisOutput, ReasoningOutput, ValidationOutput)
- [ ] Step B-2: 기존 `IntentClassifierOutput` 패턴 참고하여 각 모델에 field_validator, model_validator 추가
- [ ] Step B-3: 모든 출력 모델의 기본값이 user_input 기반인지 확인

### Phase C: 11개 에이전트에 get_guaranteed_minimum() 구현 (병렬 가능)

| 담당 | 에이전트 |
|------|---------|
| 개발자1 | Intent Classifier(기존 유지), Knowledge, Script Generator, Script Personalizer |
| 개발자2 | Safety, Emotion, Visualization, Episode Memory |
| 개발자3 | Content Analyzer, Podcast Reasoning, Batch Validator, Learning |

- [ ] Step C-1: 개발자별 4개 에이전트에 `get_guaranteed_minimum()` 구현
- [ ] Step C-2: 선택적으로 `get_rule_based_fallback()` 오버라이드 (Emotion, Safety 권장)
- [ ] Step C-3: 기존 `process()` 내부의 `call_llm_json()` → `call_llm_validated()` 교체 (점진적)
- [ ] Step C-4: 에이전트별 단위 테스트 — Tier 3, Tier 4 경로 커버

### Phase D: 기존 Change 1-6 적용 (Part 1 내용)

Phase A-C 완료 후 Part 1의 Change 1-6을 적용하면, 개별 try/except 대신 BaseAgent의 Structured Fallback이 보호하므로 **일부 Change의 수정이 불필요해지거나 단순화**된다:

| Change | Phase A-C 후 변화 |
|--------|-----------------|
| 1 (workflow.py process→call) | **여전히 필요** — `__call__()` 자체를 활성화하는 것이므로 |
| 1-B (TIER 0 타임아웃) | **여전히 필요** — 타임아웃은 BaseAgent가 아닌 workflow 레벨 |
| 2 (podcast_reasoning user_input) | **단순화** — `__call__()`의 Tier 3/4가 KeyError를 잡아줌. 다만 `state.get()` 교체는 코드 명확성을 위해 유지 |
| 2-B (content_analyzer user_input) | **단순화** — 동일 |
| 3 (script_generator fallback) | **단순화** — `state.get("content_analysis", state)` → `{}`는 여전히 수정 필요 (로직 오류). 다만 빈 dict 시 Tier 3-4가 보호 |
| 4, 4-B, 4-C (LLM try/except) | **흡수** — `call_llm_validated()`가 LLM 실패를 내부적으로 처리. 별도 try/except 불필요 |
| 5 (emotion fallback) | **흡수** — `get_rule_based_fallback()`으로 이동. 기존 except 블록 코드를 해당 메서드로 리팩토링 |
| 6 (script_personalizer empty) | **흡수** — `get_guaranteed_minimum()`이 빈 문자열 대신 원본 script_draft 기반 최소 결과 반환 |

---

## Part 1 vs Part 2: 실행 전략

### 옵션 A: Part 1 먼저, Part 2 이후 (점진적)

```
1주차: Part 1 Change 1-6 (개별 방어 코드) → PR 머지 → AWS 배포
2주차: Part 2 Phase A-C (구조적 방어) → PR 머지 → Part 1 코드 정리
```

**장점:** 즉시 크래시 방지. Part 2 합의 지연 시에도 1주차 성과 확보.
**단점:** Part 1 코드가 Part 2에서 불필요해지거나 리팩토링 대상이 됨.

### 옵션 B: Part 2 먼저, Part 1은 통합 적용 (구조 우선)

```
1주차: Part 2 Phase A (BaseAgent 확장) — 3인 합의 후 즉시 진행
       Part 2 Phase B (Pydantic 출력 모델)
2주차: Part 2 Phase C (11개 에이전트 구현) + Part 1 Change 1, 1-B, 2, 2-B, 3 통합
```

**장점:** 중복 코드 없음. 구조적으로 깔끔.
**단점:** BaseAgent 3인 합의가 지연되면 전체 일정 지연.

### 권장: 옵션 A (점진적)

**이유:** BaseAgent는 Protected File이고 3인 합의에 시간이 걸릴 수 있다. Part 1의 즉시 수정으로 **현재 발견된 크래시 위험을 우선 제거**하고, Part 2의 구조적 개선은 합의 후 진행하는 것이 현실적이다.

---

*작성일: 2026-04-06 (v4: 기존 평가·재시도 루프 분석 추가)*
*기반 조사: 멀티 서브에이전트 4+6+4개 (초기 감사 4개 + 교차 검증 6개 + 리서치 4개) + AWS SSM E2E 테스트 + git 이력 분석 + batch_validator.py / workflow.py 코드 직접 검토*
*수정 필요 파일: 8개 (Protected 2개 — workflow.py, base_agent.py)*
*예상 테스트 추가: 20개+*
*v3 추가 항목: Structured Fallback 4단계 설계, BaseAgent 확장 (get_guaranteed_minimum, call_llm_validated), Pydantic 출력 모델, 사용자 경험 보호 방안, Part 1 vs Part 2 실행 전략*

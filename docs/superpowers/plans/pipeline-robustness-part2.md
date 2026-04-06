# Phase 2: 선택적 방어 아키텍처 개선 (축소 재검토)

← [인덱스로 돌아가기](./pipeline-robustness-index.md) | [← Phase 1](./pipeline-robustness-part1.md)

> **[v5 재검토 결과 — 2026-04-07]**
>
> 이전 버전(v3-v4)에서 설계한 **Structured Fallback 4단계** (`get_guaranteed_minimum()` abstractmethod + `call_llm_validated()` Pydantic 체인 + `__call__()` 동작 변경)는 **오버 엔지니어링**으로 판단하여 **제거**한다.
>
> **제거 근거:**
> - LangGraph 공식 문서는 "핸들링할 수 없는 예외는 bubble up하라"고 명시. `__call__()`에서 예외를 삼키는 fallback 체인은 이 원칙 위반
> - `call_llm_validated()`의 Pydantic 재시도가 TIER 1 병렬 에이전트에 적용되면 latency 2배 위험
> - 11개 에이전트 전체에 abstractmethod 강제는 Protected File(`base_agent.py`) 변경 + 3인 동시 작업 필요 — 비용 과다
> - LLMClient에 이미 Circuit Breaker + Bedrock exponential backoff retry(3회)가 구현되어 있음
> - LangGraph의 `RetryPolicy`가 더 단순하고 공식적인 방법

**Phase 2는 다음 3가지 최소 개선으로 대체한다.**

---

## 변경 A: BaseAgent — `get_fallback_output()` 선택적 메서드 추가

### 근거

Phase 1의 개별 try/except 방식은 각 에이전트가 직접 fallback dict를 반환한다. 이 패턴을 **선택적으로** 표준화할 수 있다 — 강제가 아닌 권고 패턴으로.

### 변경 내용 (base_agent.py)

CLAUDE.md 규칙 준수: "신규 메서드 추가만 허용. 기존 시그니처 변경 금지."

```python
# base_agent.py에 신규 메서드 추가 (기존 __call__() 동작 불변):

def get_fallback_output(self, state: AgentState) -> dict[str, Any]:
    """
    process() 실패 시 반환할 최소 fallback dict.

    기본 구현은 빈 dict를 반환한다.
    필요한 에이전트만 오버라이드하여 의미 있는 기본값을 제공할 수 있다.

    이 메서드는 abstractmethod가 아니다 — 오버라이드는 선택사항이다.
    """
    return {}
```

**이 메서드를 활용하는 방식:**

Phase 1의 각 Change에서 except 블록의 fallback dict 값을 `get_fallback_output()` 내부로 이동하는 것이 선택사항이다. 단, 이 리팩토링은 Phase 1 완료 후 별도로 진행한다.

```python
# 예: BatchValidatorAgent (Phase 1 Change 4 적용 후)
class BatchValidatorAgent(BaseAgent):
    def get_fallback_output(self, state: AgentState) -> dict[str, Any]:
        """LLM 호출 실패 시 기본 FAIL 반환."""
        return {
            "validation_result": {
                "verdict": "FAIL", "decision": "revise",
                "overall_score": 0.0, "action": {"decision": "revise"},
                "error": "llm_call_failed",
            }
        }
```

### 구현 절차

- [ ] Step A-1: `base_agent.py`에 `get_fallback_output()` 메서드 추가 (빈 dict 반환)
- [ ] Step A-2: Phase 1 완료 후, 필요한 에이전트에서 선택적 오버라이드
- [ ] Step A-3: `pytest tests/agents/shared/test_base_agent_tracing.py -v`

> **Protected File — 3인 합의 필수. 단, 변경 범위가 작으므로 Phase 1 PR에 포함 가능.**

---

## 변경 B: LangGraph RetryPolicy 검토 (조건부 적용)

### 근거

LangGraph 공식 문서는 일시적 오류(네트워크, rate limit)에 `RetryPolicy`를 권장한다:

```python
from langgraph.pregel import RetryPolicy

workflow.add_node(
    "safety",
    safety_node,
    retry_policy=RetryPolicy(max_attempts=2, initial_interval=1.0)
)
```

이 방식은 **노드 전체를 재실행**하므로 "process() 전체 재시도"가 된다. `call_llm_validated()`처럼 LLM만 재시도하는 것과 다르다.

### 조건

`langgraph` 설치 버전에서 `RetryPolicy`를 지원하는지 먼저 확인:

```bash
python -c "from langgraph.pregel import RetryPolicy; print('지원됨')"
```

지원되지 않으면 버전 업그레이드 여부를 3인 합의 후 결정.

### 적용 대상 (지원 확인 후)

| 에이전트 | 적용 여부 | 이유 |
|---------|---------|------|
| Safety (TIER 1) | ✅ 권장 | CRISIS 판정 핵심, 일시적 실패 재시도 가치 높음 |
| Podcast Reasoning (TIER 1) | ✅ 권장 | 가장 긴 LLM 호출, 재시도 효과 있음 |
| Batch Validator (TIER 3) | ⚠️ 선택 | 이미 TIER 2 재시도 루프 존재, 중복 고려 |
| Script Personalizer (TIER 4) | ❌ 불필요 | 마지막 단계, 재시도보다 fallback이 더 적합 |

### 주의사항

- RetryPolicy는 **일시적 예외**에만 적용. LLM 파싱 오류(JSONDecodeError) 같은 코드 수준 문제는 재시도해도 동일 결과.
- TIER 1 RetryPolicy가 60초 타임아웃 내에 완료되어야 함. `max_attempts=2`면 단일 에이전트 최대 2배 시간 필요.

### 구현 절차

- [ ] Step B-1: LangGraph 버전 확인 (`python -c "import langgraph; print(langgraph.__version__)"`)
- [ ] Step B-2: 지원 여부 확인 후 3인 합의
- [ ] Step B-3: Safety, PodcastReasoning 노드에 `RetryPolicy(max_attempts=2)` 추가
- [ ] Step B-4: `pytest tests/graph/ -v`

---

## 변경 C: settings.yaml max_retries 최종 확인

> Phase 1에서 이미 포함 (Settings 조정 항목). 여기서는 확인만.

```yaml
# 목표 설정값:
pipeline:
  max_retries: 1
  max_critical_retries: 2
```

최악 시나리오 파이프라인 누적 시간 (수정 후):
- FAIL 1회: 760초 (약 12분)
- CRITICAL_FAIL 2회: 1140초 (약 19분)

**추가 고려사항:** 사용자 경험 관점에서 20분은 여전히 길다. 장기적으로 TIER 2 timeout(280초)을 줄이는 것이 근본 해결책. 단, Script Generator의 실제 평균 응답 시간을 모니터링 후 결정.

---

## 제거된 설계 (참고용)

아래는 v3-v4에서 계획했으나 v5에서 **제거**한 항목이다. 과잉 설계로 판단:

| 항목 | 제거 이유 |
|------|---------|
| `get_guaranteed_minimum()` abstractmethod | abstractmethod 강제 = 11개 에이전트 동시 수정 필요. 비용 과다 |
| `call_llm_validated()` + Pydantic 체인 | TIER 1 병렬 에이전트 latency 2배 위험. LLMClient에 이미 JSON fallback 존재 |
| `__call__()` Fallback 체인으로 변경 | LangGraph 공식 권고 위반 ("예외는 bubble up") — 디버깅 어려워짐 |
| Pydantic 에이전트별 출력 모델 11개 | 기존 `call_llm_json()` + dict 방식이 충분히 동작 중 |
| `_degraded` 플래그 전파 | 프론트엔드 연동 합의 없이 구현 시 사용처 불명확 |

**LangGraph 공식 권고 요약 (2026 기준):**
- Transient 오류 → `RetryPolicy`
- LLM-recoverable 오류 → 상태 저장 후 루프백 (`Command`, 이미 TIER3→TIER2 루프로 구현됨)
- Unexpected 오류 → bubble up (catch 하지 말 것)
- User-fixable → `interrupt()`

기존 프로젝트의 TIER 2-3 재시도 루프는 LangGraph 공식 "LLM-recoverable → 루프백" 패턴과 **이미 일치**하고 있었다.

---

*Part 2 — v5 (2026-04-07) | 오버 엔지니어링 제거, 단순화. 웹 조사 + 성능 분석 기반 재검토.*

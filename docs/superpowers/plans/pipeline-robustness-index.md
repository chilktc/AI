# 파이프라인 견고성 강화 — 마스터 인덱스

**목표:** TIER 0→4 파이프라인의 구조적 취약점 11개 수정 (에이전트 크래시·빈 응답·Blind retry 방지)

**브랜치:** `feature/reasoning-pipeline-robustness` (PR#59 머지 후 develop 기준 생성)
**필수 리뷰:** 3인 전원 (workflow.py, base_agent.py Protected File 포함)

---

## 문서 구조

| 문서 | 내용 | 우선순위 |
|------|------|---------|
| **이 파일** | 인덱스, 취약점 요약, 실행 순서 | — |
| [Part 1](./pipeline-robustness-part1.md) | Phase 1: 개별 방어 코드 (Changes 1-7) | **즉시** |
| [Part 2](./pipeline-robustness-part2.md) | Phase 2: Structured Fallback 아키텍처 | 합의 후 |

---

## 발견된 취약점 전체 목록

| # | 파일 | 취약점 | 위험도 | Phase |
|---|------|--------|--------|-------|
| 1 | workflow.py:118,127,185 | `agent.process()` 직접 호출 — `__call__()` 우회 (3곳) | CRITICAL | 1 |
| 1-B | workflow.py:576 | `_TIER0_TIMEOUT` dead code — TIER 0 타임아웃 미적용 | HIGH | 1 |
| 2 | podcast_reasoning.py:81 | `state["user_input"]` KeyError 무방비 | CRITICAL | 1 |
| 2-B | content_analyzer.py:81 | 동일 패턴 | CRITICAL | 1 |
| 3 | script_generator.py:48-50 | `content_analysis` fallback에 `state` 전체 사용 | HIGH | 1 |
| 4 | batch_validator.py:84-87 | `call_llm_json()` try/except 없음 | HIGH | 1 |
| 4-B | safety.py:45-47 | 동일 패턴 (CRISIS 판정 크래시 위험) | CRITICAL | 1 |
| 4-C | podcast_reasoning.py:270,298,328 | GoT/ToT/CoT LLM 호출 3곳 try/except 없음 | HIGH | 1 |
| 5 | emotion.py:97-109 | fallback이 `intent` 감정 정보 미활용 | MEDIUM | 1 |
| 6 | script_personalizer.py:88-93 | ValidatedScript 실패 시 `final_output=""` | HIGH | 1 |
| **7** | **script_generator.py:28~** | **FAIL 재시도 시 validation_result 피드백 무시** | **HIGH** | **1** |
| **8** | **visualization.py:51-54** | **`call_llm_json()` try/except 없음** | **CRITICAL** | **1** |
| **9** | **workflow.py:87-94** | **`_with_timeout()` 타임아웃 시 `{}` 반환 → TIER 3 자동 PASS** | **CRITICAL** | **1** |

**설정 불일치 (코드 변경 아닌 settings.yaml 조정):**

| 항목 | 현재 값 | 문제 | 권장 |
|------|---------|------|------|
| `pipeline.max_retries` | 2 | TIER 2 3회 × 280s = 최악 1140s | 1로 축소 |
| `pipeline.max_critical_retries` | 4 | TIER 2 5회 = 최악 1900s | 2로 축소 |

**이번 계획에서 제외 (별도 검토):**

| 파일 | 내용 | 제외 이유 |
|------|------|---------|
| learning.py | call_llm_json() try/except 없음 | 비동기 후처리 — 파이프라인 응답에 영향 없음 |
| llm_client.py | Semaphore race condition | asyncio 단일 이벤트루프 환경에서 실질적 위험 없음 |
| episode_memory.py | Stub 상태, 타임아웃 불일치 | Pinecone 연동 시 재점검 |
| base_agent.py | get_prompt() KeyError 미처리 | 프롬프트 로딩 실패 시 에이전트별 별도 처리 필요 — 규모 큼 |

---

## 기존 재시도 루프 평가 요약

Batch Validator(TIER 3) → FAIL → Script Generator(TIER 2) 재시도 루프는 **정상 LLM 환경에서 유효하나** 다음 조건에서 무효:

```
[BV 출력]  validation_result.action.revision_instructions  ← LLM이 구체적 수정 지침 생성
           validation_result.action.priority_fixes          ← 우선 수정 항목 배열
           validation_result.validation.issues[]            ← 각 실패 항목 상세

[문제]     Script Generator는 validation_result를 전혀 읽지 않음
           → 동일 입력으로 동일 품질 스크립트 재생성
           → Change 7에서 수정
```

---

## Phase별 실행 순서

### Phase 1 — 즉시 적용 (1 PR) → [Part 1 상세](./pipeline-robustness-part1.md)

```
Step A: emotion.py (Change 5)
Step B: safety.py (Change 4-B)
Step C: batch_validator.py (Change 4)
Step D: visualization.py (Change 8)              ← 신규
Step E: content_analyzer.py (Change 2-B)
Step F: script_generator.py (Change 3 + Change 7)   ← 두 변경 동일 파일
Step G: script_personalizer.py (Change 6)
Step H: podcast_reasoning.py (Change 2 + 4-C)
Step I: workflow.py (Change 1 + 1-B + Change 9) ← Protected, 3인 합의 마지막
Step J: settings.yaml max_retries 조정           ← 코드 아닌 설정 변경
```

### Phase 2 — 선택적 (별도 PR) → [Part 2 상세](./pipeline-robustness-part2.md)

> **[v5 재검토 결과]** 원래 설계한 `get_guaranteed_minimum()` abstractmethod + `call_llm_validated()` Pydantic 체인은 **오버 엔지니어링**으로 판단하여 제거. LangGraph 공식 권고와도 맞지 않음.

Phase 2는 다음 **3가지 단순 개선**으로 축소:
```
1. BaseAgent에 get_fallback_output() 선택적 메서드 추가 (abstractmethod 아님, 기본값 {})
2. LangGraph RetryPolicy 검토 (버전 확인 후 TIER 1 노드에 선택 적용)
3. max_retries 설정값 조정 (settings.yaml — Phase 1과 동시 가능)
```

---

## 공통 검증 체크리스트 (Phase 1 완료 후)

- [ ] `pytest tests/ -v --tb=short` — 전체 테스트 통과
- [ ] `mypy src/agents/podcast/ --ignore-missing-imports` — 타입 에러 미증가
- [ ] `ruff check src/agents/podcast/` — lint 통과
- [ ] AWS SSM E2E 10회 — HTTP 200, success:true 일관성
- [ ] LangSmith: Intent Classifier 트레이스 생성 확인 (Change 1 효과)
- [ ] FAIL 재시도 시 로그에 `[ScriptGenerator] 재시도 피드백 주입` 메시지 확인 (Change 7 효과)

---

## 공통 검증 체크리스트에 추가 (Phase 1 완료 후)

- [ ] TIER 3 타임아웃 시뮬레이션: `_TIER3_TIMEOUT`을 1초로 임시 설정 → `validation_result` 없을 때 `route_after_tier3_podcast()`가 PASS 아닌 재시도 경로 진입 확인 (Change 9 효과)
- [ ] visualization.py LLM 실패 시 `visual_data.error=="llm_call_failed"` 반환 확인 (Change 8 효과)

---

*v5 — 2026-04-07 | 멀티 서브에이전트 4+6+4+3개 + 취약점 재점검 3개 + 웹 조사(LangGraph 공식 패턴, 성능 분석)*

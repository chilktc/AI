# 최종 구현 로드맵 (2026-04-07 v2 — 검증 완료)

**목적**: 실제 미완료 작업만 포함한 최종 구현 계획  
**마지막 업데이트**: 2026-04-07 (3-에이전트 교차 검증 후 전면 수정)

> **v1 → v2 변경 이유:**  
> 3-에이전트 병렬 점검 결과, v1 로드맵의 작업 대부분이 PR #38~#60에서 이미 완료된 사실이 확인됨.  
> 불필요한 작업 제거 후 실제 미완료 항목만 남김.

---

## 확인된 기완료 항목 (v1에서 잘못 포함)

| v1 항목 | 실제 상태 | 근거 |
|---------|-----------|------|
| Phase A-1: refactor-cleanup | ✅ PR #38 완료 | 커밋 `ffe5290` 확인 |
| Phase A-2: SSM/환경변수 안정화 | ✅ PR #46 완료 | D-2/C-2/D-3 커밋 확인 |
| Phase A-3: mypy/Python 호환성 | ✅ PR #52 완료 | mypy 63→0, 타입힌트 완료 |
| Phase B-1: 타입 힌트 (Dict→dict) | ✅ PR #52 완료 | 전체 에이전트 적용 확인 |
| Phase B-2: 대화모드 제거 | ✅ PR #45/#48/#49 완료 | Phase 1-6 모두 완료 |
| Phase B-3: Bedrock 로컬 코드 | ✅ PR #39/#46 완료 | Task 1-5, 7 완료 |
| Phase C: Circuit Breaker | ✅ 기존 구현 존재 | llm_client.py:42 확인 |
| Phase C: 인젝션 방어 | ✅ PR #58 완료 | input_sanitizer.py 확인 |
| Phase C: SSE 스트리밍 | ✅ PR #48 완료 | /episodes/stream 엔드포인트 |
| Phase C: PII 정제 | ✅ PR #58 완료 | output_sanitizer.py 확인 |

---

## 실제 미완료 작업 (v2 기준)

**3가지만 남아있습니다.**

### 작업 1: 독스트링 보강 (우선순위: 🔴 높음)

**출처**: Plan#4 `2026-03-31-project-quality-review.md` Phase 2

| 항목 | 대상 | 영향 |
|------|------|------|
| Args/Returns 섹션 추가 | 11개 에이전트 파일 | 50+ 메서드 |
| Google-style 통일 | base_agent.py 기준 적용 | 전체 |
| Raises 섹션 추가 | exception 던지는 함수 | 20+ 함수 |

**복잡도**: 낮음 (반복 작업, LLM 보조 가능)  
**PR**: PR-1 (`feature/reasoning-docs-quality`)

---

### 작업 2: 주석 보완 + 깨진 링크 수정 (우선순위: 🟡 중간)

**출처**: Plan#4 Phase 4

**주석 보완 (Plan#4 Phase 4):**

| 항목 | 대상 | 영향 |
|------|------|------|
| MD5 해시 A/B 배정 알고리즘 설명 | base_agent.py:192 (`_resolve_ab_variant`) | 1곳 |
| Retry + Semaphore + 캐싱 로직 설명 | llm_client.py:389 (`_generate_bedrock`) | 1곳 |
| asyncio.Event 취소 메커니즘 설명 | workflow.py:211 (`run_with_cancel`) | 1곳 (Protected File) |
| `_MODEL_COSTS` 가격 기준일 | callbacks.py:52 | 1곳 |
| `WORDS_PER_MINUTE = 150` 한국어 근거 | script_generator.py:22 | 1곳 |

**깨진 링크 수정 (Plan#4 Phase 4-1):**

| 파일 | 깨진 링크 | 처리 |
|------|----------|------|
| README.md:99-100 | PROJECT_STRUCTURE.md, GIT_WORKFLOW.md 링크 없음 | 제거 또는 내용 직접 포함 |
| CONTRIBUTING.md:86, 120 | GIT_WORKFLOW.md 참조 | 내부 앵커로 변경 |
| docs/INDEX.md | 깨진 링크 항목 | 제거 |

**복잡도**: 낮음 (파일 수 적음)  
**PR**: PR-1과 통합 가능 (`feature/reasoning-docs-quality`)

---

### 작업 3: Bedrock EC2 벤치마크 (우선순위: 🟢 낮음, 인프라 별도)

**출처**: Plan#2 Task 6 = Plan#5 Step 2 (중복 통합)

| 항목 | 내용 |
|------|------|
| 목표 | 6종 Bedrock 모델 성능 비교 |
| 방법 | EC2에서 Phase 0-3 실행 (`run_bedrock_model_test.py`) |
| 코드 변경 | **없음** (실행만 필요) |
| 산출물 | 성능 비교 리포트, settings.yaml 최적 모델 재확인 |
| 의존성 | EC2 인스턴스 접근 권한 필요 |

**이 작업은 코드 PR 없이 인프라팀 협력으로 진행.**

---

## 구현 계획 (작업 1+2)

### 브랜치 전략

```bash
# origin/develop 최신에서 분기
git fetch origin
git checkout -b feature/reasoning-docs-quality origin/develop
```

### Phase 1: 깨진 링크 수정 (30분)

**파일**: `README.md`, `CONTRIBUTING.md`, `docs/INDEX.md`

- [ ] README.md:99-100 깨진 링크 제거 또는 대체 텍스트로 수정
- [ ] CONTRIBUTING.md:86, 120 GIT_WORKFLOW.md 참조 → 내부 앵커 또는 CLAUDE.md 참조로 변경
- [ ] docs/INDEX.md 깨진 링크 제거

**검증**: 링크 클릭 가능 여부 확인 (마크다운 렌더링)

**커밋**: `docs: 깨진 링크 수정 (README, CONTRIBUTING, docs/INDEX)`  
**푸시**: `git push origin feature/reasoning-docs-quality`

---

### Phase 2: 주석 보완 (2시간)

**파일**: `base_agent.py`, `llm_client.py`, `workflow.py`, `callbacks.py`, `script_generator.py`

- [ ] `base_agent.py:192` — `_resolve_ab_variant()` MD5 해시 A/B 배정 알고리즘 설명
- [ ] `llm_client.py:389` — `_generate_bedrock()` Retry + Semaphore + 캐싱 로직 설명
- [ ] `workflow.py:211` — `run_with_cancel()` asyncio.Event 취소 메커니즘 설명 (Protected File)
- [ ] `callbacks.py:52` — `_MODEL_COSTS` 가격 기준일(2026-02) 및 갱신 주기
- [ ] `script_generator.py:22` — `WORDS_PER_MINUTE = 150` 한국어 기준 근거

**검증**: `pytest tests/ -v` 통과 확인

**커밋**: `docs: 복잡 로직 설명 주석 추가 (5개 파일)`  
**푸시**: `git push origin feature/reasoning-docs-quality`

---

### Phase 3: 독스트링 보강 (4-5시간)

**대상**: 11개 에이전트 파일 + shared 2개

**에이전트별 작업 그룹:**

| 그룹 | 파일 | 우선순위 |
|------|------|---------|
| A | base_agent.py, llm_client.py | 🔴 높음 (공용) |
| B | safety.py, emotion.py, content_analyzer.py | 🔴 높음 (TIER 1) |
| C | script_generator.py, visualization.py, batch_validator.py | 🟡 중간 (TIER 2-3) |
| D | intent_classifier.py, podcast_reasoning.py, script_personalizer.py | 🟡 중간 (TIER 0/1/4) |

**Google-style 기준 (base_agent.py 준수):**
```python
def example_method(self, param: str) -> dict[str, Any]:
    """메서드의 한 줄 요약.

    더 상세한 설명이 필요한 경우 여기에 작성한다.

    Args:
        param: 파라미터 설명.

    Returns:
        반환값 설명.

    Raises:
        ValueError: 예외 조건 설명.
    """
```

**검증**: `pytest tests/ -v` 통과 확인

**그룹별 커밋:**
- 커밋 A: `docs: base_agent, llm_client 독스트링 Google-style 통일`
- 커밋 B: `docs: TIER 1 에이전트 독스트링 보강 (safety, emotion, content_analyzer)`
- 커밋 C: `docs: TIER 2-3 에이전트 독스트링 보강 (script_generator, visualization, batch_validator)`
- 커밋 D: `docs: TIER 0/1/4 에이전트 독스트링 보강 (intent_classifier, podcast_reasoning, script_personalizer)`

**마지막 푸시**: `git push origin feature/reasoning-docs-quality`

---

## 최종 검증

모든 Phase 완료 후:

```bash
pytest tests/ -v
```

**성공 조건:**
```
444 passed, 14 skipped
```

---

## PR 양식 (완성 후 복사 사용)

**PR 제목:**
```
docs: 독스트링 보강 + 주석 추가 + 깨진 링크 수정
```

**Base**: `develop` | **Compare**: `feature/reasoning-docs-quality`

**PR Body 양식 (완료 후 실제 수치 채울 것):**

```markdown
## 개요

3-에이전트 교차 검증 결과 확인된 실제 미완료 작업 수행:
- 깨진 링크 수정 (README.md, CONTRIBUTING.md, docs/INDEX.md)
- 복잡 로직 설명 주석 추가 (5개 파일)
- 독스트링 Google-style 통일 (11개 에이전트 + 2개 shared)

## 변경 내역

| Phase | 파일 수 | 내용 |
|-------|---------|------|
| Phase 1 | 3개 | 깨진 링크 제거/수정 |
| Phase 2 | 5개 | 복잡 로직 설명 주석 |
| Phase 3 (그룹 A) | 2개 | base_agent, llm_client 독스트링 |
| Phase 3 (그룹 B) | 3개 | TIER 1 에이전트 독스트링 |
| Phase 3 (그룹 C) | 3개 | TIER 2-3 에이전트 독스트링 |
| Phase 3 (그룹 D) | 3개 | TIER 0/1/4 에이전트 독스트링 |

## 테스트 결과

```
444 passed, 14 skipped
```

## 코드 변경 없음 확인

이 PR은 독스트링/주석/문서만 변경합니다. 로직 변경 없음.

## 참고

- 교차 검증 결과: `docs/superpowers/PLAN_INDEX.md` v2
- 독스트링 기준: `src/agents/shared/base_agent.py` Google-style
```

---

## Bedrock EC2 벤치마크 (별도 진행)

코드 PR 없음. 인프라팀 협력 필요:

1. EC2 인스턴스에서 `python -m dev.live_tests.run_bedrock_model_test` 실행
2. 6종 모델 비교 결과 리포트 저장 (`dev/live_tests/results/bedrock_phase3_*.json`)
3. 결과 바탕으로 `config/settings.yaml` 모델 최적값 재확인

---

*구현 로드맵 v2 — 2026-04-07*  
*이전 v1 삭제 (내용이 크게 변경됨)*

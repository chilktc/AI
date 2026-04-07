# 프로젝트 코드 품질 점검 체크리스트

**출처**: `2026-03-31-project-quality-review.md` 상세 분석  
**탐색 에이전트**: Haiku (자동화 목록화)  
**목적**: 코드 품질 개선 계획의 구현 항목 세분화  
**버전**: v3  
**마지막 업데이트**: 2026-04-07 15:00

---

## 요약

**총 작업량**: 9개 Phase, 7개 섹션, 75+ 개 지점 수정  
**파일 영향**: 40+ 개 파일  
**복잡도**: 낮음~중간 (반복 작업, 자동화 가능 부분 많음)  
**PR 분리 권고**: **3-4개 PR로 분리** (Phase별 또는 도메인별)

### 분리 제안

| PR | Phase | 내용 |
|----|-------|------|
| PR A | Phase 1-2 | 타입 힌트 + 로깅 통일 |
| PR B | Phase 3-4 | 독스트링 + 주석 보완 |
| PR C | Phase 5-7 | 에러 처리 + 폴더 구조 정리 |
| PR D | Phase 8-9 | dead code + 문서 정리 |

---

## Phase별 체크리스트

### Phase 1: 타입 힌트 현대화 (Dict → dict) ✅ 완료 — PR #52

| 항목 | 대상 | 상태 |
|------|------|------|
| ~~Dict → dict~~ | script_generator, knowledge, intent_classifier, script_personalizer, schemas.py | ✅ PR #52 완료 |
| ~~List → list~~ | 동일 파일 | ✅ PR #52 완료 |
| ~~Optional[T] → T \| None~~ | 동일 파일 | ✅ PR #52 완료 |
| ~~Union[A, B] → A \| B~~ | 동일 파일 | ✅ PR #52 완료 |

**검증**: mypy 63개 에러 → 0 (PR #52 커밋 `678a8fb` 확인)

---

### Phase 2: 로깅 포맷 통일

| 항목 | 대상 | 우선순위 | 복잡도 | 영향 |
|------|------|---------|--------|------|
| [ ] f-string → %-포맷 | 4개 파일 (22곳) | 🟡 중간 | 낮음 | 검색 + 치환 |
| [ ] module logger 정의 | podcasts.py, callbacks.py 등 | 🟡 중간 | 중간 | 53곳 |
| [ ] traceback.print_exc 제거 | podcasts.py:300 | 🔴 높음 | 낮음 | 1곳 |
| [ ] print() 제거 | callbacks.py:13-14 | 🟢 낮음 | 낮음 | docstring 예시 |

**표준**: `logger.info("[%s] %s", context, message)` 형식 통일

---

### Phase 3: 독스트링 통일 (Google-style) ✅ 완료

| 항목 | 대상 | 상태 |
|------|------|------|
| BaseAgent 스타일 적용 | 모든 에이전트 (11개) | ✅ 전체 완료 |
| Args/Returns 섹션 추가 | 에이전트 메서드 | ✅ safety.py + batch_validator.py process() 완료 |
| Raises 섹션 추가 | exception 던지는 함수 | ✅ safety.py + batch_validator.py 완료 |
| 예제 코드 추가 | public 메서드 | ⏸ 보류 (필수 아님) |

**표준**: Google 스타일 (base_agent.py 참조)

---

### Phase 4: 주석 보완 ✅ 완료 — 4-에이전트 검증 확인

| 항목 | 대상 | 상태 |
|------|------|------|
| ~~기능 설명 주석~~ | `base_agent.py:192` `_resolve_ab_variant()` | ✅ 주석 이미 존재 |
| ~~로직 설명 주석~~ | `src/agents/shared/llm_client.py:389` `_generate_bedrock()` | ✅ 주석 이미 존재 |
| ~~취소 메커니즘 주석~~ | `src/graph/workflow.py:211` `run_with_cancel()` | ✅ 주석 이미 존재 |
| ~~상수 설명~~ | `src/monitoring/callbacks.py:52` `_MODEL_COSTS` | ✅ 주석 이미 존재 |
| ~~상수 설명~~ | `src/agents/podcast/script_generator.py:22` `WORDS_PER_MINUTE` | ✅ 주석 이미 존재 |

> 경로 수정: ~~`src/utils/callbacks.py`~~ → 실제 경로: `src/monitoring/callbacks.py`  
> 경로 수정: ~~`src/api/routers/podcasts.py`~~ → 실제 경로: `src/api/routes/podcasts.py`

**원칙**: "왜(why)"를 설명, 코드 리딩만으로 이해 불가능한 부분만

---

### Phase 5: 불필요한 코드 제거

| 항목 | 위치 | 우선순위 | 영향 |
|------|------|---------|------|
| [ ] `features` 섹션 제거 | settings.yaml:237-241 | 🔴 높음 | 5줄 |
| [ ] `databases` 섹션 제거 | settings.yaml:264-272 | 🔴 높음 | 9줄 |
| [ ] `start_time` 변수 제거 | script_personalizer.py:75 | 🔴 높음 | 1줄 |
| [ ] `visual_data_raw` 중복 제거 | podcasts.py:162, 212 | 🟡 중간 | 로직 검토 필요 |
| [ ] 프롬프트 아카이브 정리 | prompts/podcast/_archive/ | 🟢 낮음 | 3개 YAML 파일 |

---

### Phase 6: 에러 처리 보완 ✅ 완료 — PR #60

| 항목 | 대상 | 상태 |
|------|------|------|
| ~~try-except 추가~~ | 외부 API 호출 | ✅ PR #60 파이프라인 견고성 강화 (13개 취약점 수정) |
| ~~타입 검증 추가~~ | 상태 접근 | ✅ PR #60 완료 |
| ~~타임아웃 처리~~ | LLM 호출 | ✅ PR #60 완료 (TIER 0~4 타임아웃 래퍼 추가) |
| ~~로깅 + 폴백~~ | 에러 핸들링 | ✅ PR #60 `get_fallback_output()` 추가 |

**검증**: `pipeline-robustness-index.md` — 13개 취약점 수정 확인 (PR #60)

---

### Phase 7: 폴더 구조 정리

| 항목 | 현황 | 우선순위 | 복잡도 | 액션 |
|------|------|---------|--------|------|
| [ ] src/models/ 병합 여부 결정 | schemas.py 위치 불명확 | 🟡 중간 | 높음 | 구조 검토 |
| [ ] prompts/ 아카이브 정리 | _archive/ 포함 의도 미문서화 | 🟢 낮음 | 낮음 | 정보성 주석 추가 |
| [ ] tests/ 디렉토리 정리 | 테스트 파일 위치 | 🟢 낮음 | 낮음 | 미정 |
| [ ] dead code 파일 제거 | 사용 안 하는 모듈 | 🟡 중간 | 중간 | Phase 8에서 병행 |

---

### Phase 8: 문서 통일성

| 항목 | 대상 | 우선순위 | 복잡도 | 영향 |
|------|------|---------|--------|------|
| [ ] README 전면 작성 | 프로젝트 루트 | 🔴 높음 | 중간 | 구조, 설치, 실행 |
| [ ] API 문서 생성 | docs/api/ | 🔴 높음 | 중간 | 엔드포인트 정리 |
| [ ] 아키텍처 문서 정리 | docs/architecture/ | 🔴 높음 | 중간 | v4.0 최종화 |
| [ ] 에이전트 역할 문서 업데이트 | docs/guides/ | 🟡 중간 | 중간 | 최신 코드 반영 |
| [ ] CLAUDE.md 최신화 | CLAUDE.md | 🔴 높음 | 낮음 | Protected Files 업데이트 |

---

### Phase 9: 불필요한 문서 정리

| 항목 | 대상 | 우선순위 | 액션 |
|------|------|---------|------|
| [ ] 중복 문서 병합 | docs/ 내 유사 파일 | 🟡 중간 | 검토 + 링크 통합 |
| [ ] 사용 안 하는 가이드 아카이브 | outdated 문서 | 🟢 낮음 | 이동만 (삭제 아님) |
| [ ] 테이블/목차 업데이트 | 모든 메인 문서 | 🟡 중간 | 링크 검증 |

---

## 실행 전략

### PR A: 타입 힌트 + 로깅 (Phase 1-2)

**예상 변경 파일**: 
- script_generator.py, knowledge.py, intent_classifier.py, script_personalizer.py, schemas.py
- podcasts.py, callbacks.py (로깅)

**예상 커밋 수**: 2-3개 (각 Phase별)

**자동화 가능**: 95% (도구 사용)

**검증**: `ruff check`, `mypy`

---

### PR B: 독스트링 + 주석 (Phase 3-4)

**예상 변경 파일**: 모든 에이전트 (11개)

**예상 커밋 수**: 5-6개 (에이전트 그룹별)

**자동화 불가**: 수동 작성 (LLM 보조 가능)

**검증**: 문서 생성 + 링크 테스트

---

### PR C: 에러 처리 + 폴더 (Phase 5-7)

**예상 변경 파일**: 전체 (40+ 파일)

**예상 커밋 수**: 4-5개 (도메인별)

**자동화 가능**: 50% (코드 스캔 후 수동)

**검증**: `pytest`, E2E 테스트

---

### PR D: Dead Code + 문서 정리 (Phase 8-9)

**예상 변경 파일**: docs/ + settings.yaml + prompts/

**예상 커밋 수**: 2-3개 (문서/설정)

**자동화 가능**: 80% (검색 + 정리)

**검증**: 링크 체크, 빌드 확인

---

## 4-에이전트 2차 검증에서 신규 발견된 항목

### external_schemas.py docstring 경로 오류

| 항목 | 파일 | 라인 | 현재 (오류) | 수정값 |
|------|------|------|-----------|--------|
| 엔드포인트 경로 | `src/api/external_schemas.py` | 684-685 | `/conversations/stream`, `ws/conversations` | `/episodes/stream` |

**성격**: docstring 텍스트 오류 (기능 영향 없음), 이 체크리스트 범위에는 없던 항목  
**처리**: `feature/reasoning-docs-quality` 브랜치에서 작업 1+2+3과 함께 처리

---

## 권장 사항

**현재 상태 (2026-04-07 v2 — 4-에이전트 2차 검증 기준):**
1. ✅ 완료: Plan#1 (refactor-cleanup)
2. ✅ 완료: Plan#5-remaining-issues (D-2, C-2, D-3)
3. ✅ 완료: Plan#7-comprehensive-execution (Phase 1-2)
4. ✅ 완료: Phase 1 (타입 힌트 — PR #52)
5. ✅ 완료: Phase 4 (주석 보완 — 4-에이전트 검증으로 모두 확인)
6. ✅ 완료: Phase 6 (에러 처리 — PR #60)
7. ✅ 완료: Phase 3 (safety.py + batch_validator.py 독스트링 — PR #61)

**처리 브랜치**: `feature/reasoning-docs-quality`  
**상세 계획**: `IMPLEMENTATION_ROADMAP.md` v3 참조

---

*체크리스트 v3 — 2026-04-07 15:00 (Phase 3 독스트링 구현 완료 반영)*

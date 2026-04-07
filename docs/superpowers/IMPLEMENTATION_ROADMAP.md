# 최종 구현 로드맵

**목적**: 실제 미완료 작업만 포함한 최종 구현 계획  
**버전**: v4  
**마지막 업데이트**: 2026-04-07 15:00

> **v2 → v3 변경 이유:**  
> 4-에이전트 2차 병렬 점검 결과,  
> - Phase 1 (깨진 링크): docs/INDEX.md 링크 모두 정상 확인 → 제거  
> - Phase 2 (주석 보완): 대상 5개 파일 모두 주석 이미 존재 확인 → 제거  
> - Phase 3 (독스트링): 11개 에이전트 중 실제 미완료는 2개(safety.py, batch_validator.py)만  
> - 경로 오류 수정: `src/utils/callbacks.py` → `src/monitoring/callbacks.py`  
> - 신규 발견 항목 추가: external_schemas.py, 빈 디렉토리, 보안 트래커

---

## v1/v2에서 제거된 항목 (이미 완료 또는 불필요)

| v2 항목 | 실제 상태 | 근거 |
|---------|-----------|------|
| Phase 1: 깨진 링크 수정 | ✅ 불필요 | docs/INDEX.md 내 링크 전수 확인, 모두 정상 |
| Phase 2: 주석 보완 (5개 파일) | ✅ 이미 존재 | base_agent.py:192, llm_client.py:389, workflow.py:211, callbacks.py:52, script_generator.py:22 주석 확인 |
| Phase 3: 독스트링 11개 에이전트 전체 | 🔶 2개만 미완료 | safety.py + batch_validator.py만 실제 미완료 |

---

## 완료된 작업 (v4 — PR #61)

### ✅ 작업 1: 독스트링 보강 — 소규모 2개 파일

| 항목 | 파일 | 완료 |
|------|------|------|
| process() 독스트링 | `src/agents/podcast/safety.py` | ✅ Google-style Args/Returns/Raises 추가 |
| process() 독스트링 | `src/agents/podcast/batch_validator.py` | ✅ Google-style 통일, next_step 오류 수정, iteration_count 추가 |

### ✅ 작업 2: docstring 내용 오류 수정

| 항목 | 파일 | 완료 |
|------|------|------|
| 엔드포인트 경로 오류 | `src/api/external_schemas.py` | ✅ GET conversations → POST podcasts/episodes, WS 줄 제거 |

### ✅ 작업 3: 빈 디렉토리 제거

| 항목 | 경로 | 완료 |
|------|------|------|
| 빈 껍데기 디렉토리 | `src/agents/conversation/` | ✅ __pycache__만 있던 디렉토리 삭제 (Git 미추적) |

---

### 작업 4: Bedrock EC2 벤치마크 (우선순위: 🟢 낮음, 인프라 별도)

**출처**: Plan#2 Task 6 = Plan#5 Step 2

| 항목 | 내용 |
|------|------|
| 목표 | 6종 Bedrock 모델 성능 비교 |
| 방법 | EC2에서 Phase 0-3 실행 (`run_bedrock_model_test.py`) |
| 코드 변경 | **없음** (실행만 필요) |
| 산출물 | 성능 비교 리포트, settings.yaml 최적 모델 재확인 |
| 의존성 | EC2 인스턴스 접근 권한 필요 |

**이 작업은 코드 PR 없이 인프라팀 협력으로 진행.**

---

## 선택적 작업 (별도 PR 검토)

### ✅ 작업 5: Circuit Breaker 상태 전환 테스트

**출처**: PLAN_INDEX.md 그룹 2

| 항목 | 파일 | 완료 |
|------|------|------|
| CLOSED→OPEN (fail_max 초과) | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN→CircuitOpenError | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN→HALF_OPEN (timeout 경과) | `tests/agents/shared/test_llm_client.py` | ✅ |
| HALF_OPEN→CLOSED (1회 성공) | `tests/agents/shared/test_llm_client.py` | ✅ |
| HALF_OPEN→OPEN (1회 실패) | `tests/agents/shared/test_llm_client.py` | ✅ |
| success failure_count 리셋 | `tests/agents/shared/test_llm_client.py` | ✅ |
| CLOSED check() 통과 | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN timeout 미경과 유지 | `tests/agents/shared/test_llm_client.py` | ✅ |
| 초기 상태 CLOSED 확인 | `tests/agents/shared/test_llm_client.py` | ✅ |

**총 9개 테스트 추가**

---

### ✅ 작업 6: SSE 엔드포인트 테스트

**출처**: PLAN_INDEX.md 그룹 2

| 항목 | 파일 | 완료 |
|------|------|------|
| Content-Type 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| Cache 헤더 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| connected 첫 이벤트 | `tests/api/test_sse_streaming.py` | ✅ |
| done 마지막 이벤트 | `tests/api/test_sse_streaming.py` | ✅ |
| custom tier 이벤트 전달 | `tests/api/test_sse_streaming.py` | ✅ |
| result 이벤트 데이터 | `tests/api/test_sse_streaming.py` | ✅ |
| timestamp 포함 확인 | `tests/api/test_sse_streaming.py` | ✅ |
| 전체 이벤트 순서 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| 파이프라인 에러 핸들링 | `tests/api/test_sse_streaming.py` | ✅ |
| compiled_graph=None 에러 | `tests/api/test_sse_streaming.py` | ✅ |
| 잘못된 요청 422 반환 | `tests/api/test_sse_streaming.py` | ✅ |

**총 11개 테스트 추가**

---

## 구현 계획 (작업 1+2+3)

### 브랜치 전략

```bash
# origin/develop 최신에서 분기 (이미 생성됨)
# feature/reasoning-docs-quality
```

### Phase 1: docstring 내용 오류 수정 (15분)

**파일**: `src/api/external_schemas.py:684-685`

- [ ] `/conversations/stream` → `/episodes/stream` 수정
- [ ] `ws/conversations` → 올바른 WebSocket 경로로 수정 (또는 제거)

**검증**: 파일 정상 확인  
**커밋**: `docs: external_schemas.py 엔드포인트 경로 오류 수정 (conversations→episodes)`

---

### Phase 2: 독스트링 보강 (1시간)

**파일**: `src/agents/podcast/safety.py`, `src/agents/podcast/batch_validator.py`

- [ ] `safety.py:process()` — Google-style Args/Returns/Raises 추가
- [ ] `batch_validator.py:process()` — 커스텀 형식 → Google-style 통일

**Google-style 기준 (base_agent.py 준수):**
```python
def process(self, state: AgentState) -> dict[str, Any]:
    """메서드의 한 줄 요약.

    Args:
        state: 현재 AgentState.

    Returns:
        변경된 필드만 담긴 dict.

    Raises:
        ValueError: 상태에 필수 필드가 없을 때.
    """
```

**검증**: `pytest tests/ -v` 통과 확인  
**커밋**: `docs: safety, batch_validator process() 독스트링 Google-style 통일`

---

### Phase 3: 빈 디렉토리 제거 (5분)

**경로**: `src/agents/conversation/`

- [ ] 빈 디렉토리 확인 후 삭제

**검증**: `pytest tests/ -v` 통과 확인  
**커밋**: `chore: src/agents/conversation/ 빈 디렉토리 제거 (대화모드 제거 잔재)`

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
docs: 독스트링 보강 + docstring 오류 수정 + 빈 디렉토리 제거
```

**Base**: `develop` | **Compare**: `feature/reasoning-docs-quality`

**PR Body 양식:**

```markdown
## 개요

4-에이전트 2차 교차 검증 결과 확인된 실제 미완료 작업 수행:
- external_schemas.py 엔드포인트 경로 오류 수정 (conversations → episodes)
- safety.py + batch_validator.py process() 독스트링 Google-style 통일
- src/agents/conversation/ 빈 디렉토리 제거 (대화모드 제거 잔재)

## 변경 내역

| Phase | 파일 수 | 내용 |
|-------|---------|------|
| Phase 1 | 1개 | external_schemas.py 경로 오류 수정 |
| Phase 2 | 2개 | safety, batch_validator 독스트링 보강 |
| Phase 3 | 1개 | 빈 디렉토리 제거 |

## 테스트 결과

```
444 passed, 14 skipped
```

## 코드 변경 없음 확인

이 PR은 독스트링/주석/문서만 변경합니다. 로직 변경 없음.
(external_schemas.py는 docstring 텍스트만 수정, 기능 변경 없음)

## 참고

- 교차 검증 결과: `docs/superpowers/PLAN_INDEX.md` v3
- 독스트링 기준: `src/agents/shared/base_agent.py` Google-style
```

---

## 외부 의존성 / 수동 작업 (코드 PR 없음)

### 보안 수동 조치 (SECURITY_REMEDIATION_TRACKER.md)

| # | 작업 | 상태 |
|---|------|------|
| 1 | KT Cloud API 토큰 로테이션 | ❌ 미완료 |
| 2 | OpenAI API 키 로테이션 | ❌ 미완료 |
| 3 | LangSmith API 키 로테이션 | ❌ 미완료 |
| 4 | Grafana/OpenSearch 비밀번호 변경 | ❌ 미완료 |
| 5 | 로컬 DB 비밀번호 재설정 | ❌ 미완료 |
| 6 | Git history 정리 (KT Cloud 토큰 잔존) | ❌ 미완료 — 3인 합의 필요 |

### Stub 에이전트 (Pinecone 연동 후 처리)

| 파일 | 라인 | 내용 | 의존성 |
|------|------|------|--------|
| `src/agents/podcast/podcast_reasoning.py` | 58-59 | `EpisodeMemoryStub()`, `KnowledgeAgentStub()` | Pinecone 연동 |
| `src/agents/podcast/base_memory.py` | 88-89 | `_save_to_store()` stub | KT Cloud API |
| `src/agents/podcast/episode_memory.py` | 15 | `mock_db.json` → Pinecone 전환 | Pinecone 연동 |

### Bedrock EC2 벤치마크

인프라팀 협력 필요:
1. EC2 인스턴스에서 `python -m dev.live_tests.run_bedrock_model_test` 실행
2. 6종 모델 비교 결과 리포트 저장 (`dev/live_tests/results/bedrock_phase3_*.json`)
3. 결과 바탕으로 `config/settings.yaml` 모델 최적값 재확인

---

*구현 로드맵 v5 — 2026-04-07*  
*v1~v3: 기획/점검 → v4: 작업 1-3 구현 완료 (PR #61) → v5: 작업 5-6 테스트 구현 완료 (CB 9개 + SSE 11개)*

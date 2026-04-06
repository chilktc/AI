# Mind-Log 종합 실행 계획서 (2026-04-06 v2)

> **목적:** 미완료 항목 현황 조사를 기반으로 실행 가능한 작업을 Phase별로 구성한다.
>
> **검증 방법:** 10개 병렬 에이전트가 각 Phase의 대상 파일을 실제 코드와 교차 검증.
> 이전 버전(v1) 대비 수정사항은 `[v2 수정]` 태그로 표기.
>
> **기준:** develop 브랜치 (194116e)

---

## Phase 1: CI 정상화 — Python 호환성 + mypy 타입 에러 수정

> **목표:** CI lint 단계 + 테스트 수집 단계 동시 정상화.
> **얻는 결과:** CI 파이프라인이 green 상태가 되어 이후 Phase의 변경사항을 안전하게 검증할 수 있다.

### 1-1. Python 3.10+ 문법 호환성 수정 [v2 추가]

> **근거:** `src/models/schemas.py:43`에서 `str | None` (PEP 604) 문법을 사용하는데,
> 로컬 환경(Python 3.9)에서 이 한 줄이 import 체인 전체를 붕괴시킨다.
> schemas.py → intent_classifier.py → workflow.py → main.py → **모든 API 테스트 19건 ERROR**.
> CI(3.11/3.12)에서는 발생하지 않지만, 로컬 개발 환경 호환성을 위해 수정한다.
>
> **얻는 결과:** 로컬 환경에서 19 ERROR + 4 FAILED (import 연쇄) 즉시 해소. 341→364건 테스트 수집 가능.

**수정:**
```python
# 변경 전 (line 43)
reasoning: str | None = Field(default=None, ...)
# 변경 후
reasoning: Optional[str] = Field(default=None, ...)
```
- `from __future__ import annotations` 또는 `from typing import Optional` 추가

- [ ] Step 1: `src/models/schemas.py` 전체에서 `X | None` 패턴 검색 및 `Optional[X]`로 교체
- [ ] Step 2: 로컬에서 `python3 -c "from src.models.schemas import *"` — ImportError 없음 확인

### 1-2. mypy 63에러 수정

> **근거:** Black/Ruff/isort는 전체 통과. mypy만 63에러/18파일로 CI lint 차단.
> **얻는 결과:** CI lint 단계 전면 통과.

**에러 분류 (10개 에이전트 검증 결과):**

| 분류 | 건수 | 수정 방향 | 예시 |
|------|------|----------|------|
| TRIVIAL — 반환 타입 미선언 | 8건 | `-> dict[str, Any]` 등 추가 | main.py, health.py, podcasts.py |
| TRIVIAL — no-any-return | 6건 | `cast()` 또는 타입 가드 | middleware.py, llm_client.py |
| TRIVIAL — None 체크 미비 | 3건 | `if x is None: raise` 또는 `assert x` | neo4j_client.py, mysql_client.py |
| LOGIC — StateGraph arg-type | 4건 | `type: ignore[arg-type]` (LangGraph 라이브러리 타입 한계) | workflow.py |
| LOGIC — 에이전트 타입 불일치 | 15건 | 타입 가드, Optional 처리 | knowledge.py(7), intent_classifier.py(6) |
| LOGIC — dict/list 구조 | 4건 | 타입 캐스팅, 필터링 | script_generator.py, output_sanitizer.py |
| LIBRARY — 외부 스텁 미설치 | 4건 | `pyproject.toml`에 types-PyYAML, types-PyMySQL 추가 또는 ignore | loader.py, prompt_loader.py, mysql_client.py |
| 기타 | 19건 | 개별 확인 | base_agent.py, llm_client.py 등 |

**주요 파일별 에러 수:**
- knowledge.py: 7건, intent_classifier.py: 6건, workflow.py: 6건 [v2 수정: 이전 "5건"→실측 "6건"]
- main.py: 4건, mysql_client.py: 3건, 나머지 12파일: 각 1~2건

- [ ] Step 3: TRIVIAL 에러 수정 (타입 힌트 추가, 약 17건)
- [ ] Step 4: LIBRARY 에러 수정 (types-PyYAML 등 추가 또는 `# type: ignore`, 4건)
- [ ] Step 5: LOGIC 에러 수정 (타입 가드, 캐스팅, StateGraph ignore, 약 42건)
- [ ] Step 6: `mypy src/ --ignore-missing-imports` — 0 에러 확인
- [ ] Step 7: `pytest tests/ -v --tb=short` — 기존 테스트 통과 확인
- [ ] Step 8: 커밋

---

## Phase 2: 테스트 실패·에러 수정

> **목표:** 5 failed + 19 errors 해소.
> **얻는 결과:** 테스트 스위트가 안정화되어 이후 Phase에서 회귀를 탐지할 수 있다.

### 2-1. import 연쇄 에러 해소 (19 errors + 4 failed) [v2 수정: 근본 원인 특정]

> **근거:** 10개 에이전트 검증 결과, 24건 중 23건이 **단일 근본 원인**(schemas.py의 `str | None`)에서 파생.
> Phase 1-1에서 수정하면 자동 해소된다.
>
> **얻는 결과:** Phase 1 완료 후 이 단계는 대부분 자동 해소. 잔여 실패만 수정하면 된다.

**Phase 1 완료 후 잔여 예상:**
| 테스트 | 원인 | 수정 |
|--------|------|------|
| `test_backend_health::test_backend_server_reachable` | 외부 서버 미실행 (ConnectionRefusedError) | `@pytest.mark.live` 이미 존재 — pytest 실행 시 `-m "not live"` 또는 skip 조건 추가 |

- [ ] Step 1: Phase 1 완료 후 전체 테스트 재실행 — 잔여 실패 확인
- [ ] Step 2: 외부 의존 테스트에 skip 조건 추가 (필요 시)
- [ ] Step 3: 잔여 에러가 있다면 개별 수정
- [ ] Step 4: `pytest tests/ -v` — 0 failed, 0 errors 목표
- [ ] Step 5: 커밋

---

## ~~Phase 3: Stub → 실제 에이전트 연결~~ [v3 차후 이관]

> **이관 사유:** episode_memory, knowledge 에이전트는 아직 개발 중이며, Pinecone(벡터 DB) 연결 작업과
> 복합적으로 묶여 있어 단독 진행 불가. Pinecone 통합 시점에 함께 계획한다.

<details>
<summary>참고: 검증된 갭 분석 (차후 작업 시 활용)</summary>

**핵심 갭 3가지:**
1. **인터페이스 불일치:** Stub은 `search(query, user_id)`, 실제 에이전트는 `process(state)`. 어댑터 필요.
2. **반환 형식 불일치:** Stub(`episodes`, `relevance_scores`) vs 실제(`memory_results.items`). 변환 필요.
3. **DB 클라이언트 미주입:** KnowledgeAgent 생성자에 `(db_client, pinecone_client, embedding_client)` 필요. factory.py 연결.

**전제 조건:** `storage.mode`를 `local`로 변경하거나 `STORAGE_MODE=local` 환경변수 오버라이드 필요.

**수정 대상:** `episode_memory.py` (어댑터), `knowledge.py` (어댑터), `podcast_reasoning.py` (DI 연결). workflow.py 수정 불필요.
</details>

---

## ~~Phase 4: script_personalizer 규칙 구현~~ [v3 차후 이관]

> **이관 사유:** script_personalizer는 개발자1 담당 에이전트로, 현재 사용자의 개발 담당 영역이 아님.

<details>
<summary>참고: 검증된 구현 방향 (차후 작업 시 활용)</summary>

**대상:** `_apply_attitude_adjustment()` empathetic/rational 분기 (pass), `_apply_accessibility_adjustments()` hearing_impairment 분기 (pass).
**활용 자원:** `config/app_config.py:94-114`의 `ATTITUDE_SETTINGS` — tone_keywords, avoid_keywords 이미 정의됨.
**호출 경로:** `deep_personalization` 설정과 무관하게 rule-based 흐름에서 항상 호출됨.
</details>

---

## Phase 5: 정리 작업

> **목표:** dead code 제거, 문서 정리, 설정 정비.
> **얻는 결과:** 코드베이스에 미사용 코드·스테일 문서가 없는 깨끗한 상태.

### 5-1. Dead code 제거

| 파일 | 변경 | 근거 |
|------|------|------|
| `intent_classifier.py` | `next_step` 설정 코드 제거 (line 121, 168, 184) | `route_after_tier0()`가 항상 `"tier1_podcast"` 반환. next_step 미참조 (검증됨) |
| `batch_validator.py` | `next_step` 설정 코드 제거 (line 78, 109, 134, 146) | `route_after_tier3_podcast()`가 `validation_result.verdict`로 직접 판단. next_step은 `"crisis_response"` 체크에만 사용되는데 batch_validator는 crisis 값을 설정하지 않음 (검증됨) |

> **[v2 수정] 주의:** `route_after_tier1()` (workflow.py:424)에서 `state.get("next_step") == "crisis_response"`를
> 확인하는 코드가 있다. 이 값은 `tier1_podcast_fan_out()` (workflow.py:334)에서 Safety CRISIS 시 설정된다.
> intent_classifier와 batch_validator가 설정하는 next_step 값(`"safety_intervention"`, `"process_normal"`, `"retry_script"` 등)은
> 이 체크와 무관하므로 제거해도 안전하다.

### 5-2. deploy.yml echo 통일

| 파일 | 변경 | 근거 |
|------|------|------|
| `.github/workflows/deploy.yml` line 103-104 | `echo` → `printf '%s\n'` 통일 | 나머지 89-102는 이미 printf. 비민감 값이지만 일관성 확보 |

### 5-3. 스테일 문서/파일 정리 [v2 추가]

| 파일 | 변경 | 근거 |
|------|------|------|
| `pr-body.md` | 삭제 또는 `docs/reports/`로 이동 | PR #51 머지 완료 후 루트에 방치된 스테일 파일 |
| `.env.example` line 57-62 | `[미사용]` 주석 블록 제거 | 4개 feature flag가 주석으로 남아있으나 구현 계획 없음. 혼란 방지 |
| `docs/reports/PROJECT_DECISIONS.md` line 102-104 | 팟캐스트 모드 구현 완료 반영 | "Memory, Reasoning — ⏳ 미구현"으로 표기되어 있지만 실제로는 팟캐스트용 구현 완료. 대화모드만 미구현으로 명확히 구분 |
| `src/api/external_schemas.py:228` | TODO 주석 제거 | max_length가 이미 각 필드에 500자로 설정됨. TODO 주석만 스테일 상태 (검증됨) |

- [ ] Step 1: intent_classifier dead code 제거
- [ ] Step 2: batch_validator dead code 제거
- [ ] Step 3: deploy.yml echo→printf 통일
- [ ] Step 4: pr-body.md 처리
- [ ] Step 5: .env.example, PROJECT_DECISIONS.md, external_schemas.py 정리
- [ ] Step 6: 테스트 통과 확인
- [ ] Step 7: 커밋

---

## 백엔드 팀 협의 목록 (실행 계획 범위 밖)

> [v2 수정] 검증 결과 잘못 분류된 항목 제거, 정확한 건수 반영.

### 실제 외부 의존 항목

| # | 항목 | 건수 | 참조 | 근거 |
|---|------|------|------|------|
| 1 | API Proxy 엔드포인트 확정 | **13건** [v2: 12→13] | `src/db/api_proxy.py` | 벡터·그래프·RDB·S3 프록시 클라이언트. proxy 모드 동작에 필수 |
| 2 | API 리소스 경로 확정 | **5건** [v2: 4→5] | `src/api/backend_resources.py` | sessions, vector_search, graph_query, storage_upload, storage_object |
| 3 | API Key 인증 방식 | 1건 | PROJECT_DECISIONS | 설계 결정 필요 |
| 4 | 토큰 예산 관리 | 1건 | PROJECT_DECISIONS | 정책 정의 필요 (한도, 초과 시 동작) |
| 5 | Rate Limiting | 1건 | 인프라팀 | API Gateway 레벨 |
| 6 | user_profiles 테이블 스키마 | 1건 | script_personalizer.py:229-237 | proxy 모드에서 DB 프로필 조회에 필요. local 모드에서는 직접 MySQL 접근 가능 [v2 수정] |

### [v2 수정] 이전 버전에서 제거한 항목과 근거

| 항목 | 제거 근거 |
|------|----------|
| ~~S3 upload prefix~~ | 설정 값 결정일 뿐 코드 차단 아님. AI팀이 `"vis"` prefix를 결정하면 됨 |
| ~~텍스트 필드 max_length~~ | 이미 각 필드에 500자로 설정됨. TODO 주석만 스테일 (Phase 5에서 주석 제거) |
| ~~storage.mode 운영 값~~ | 배포 설정이지 코드 구현이 아님. DevOps 영역 |
| ~~_query_user_profile() DB 연동~~ | local 모드에서는 직접 MySQL 접근 가능. proxy 모드 전용 의존만 #6으로 분류 |

---

## 인프라 · EC2 작업 (접근 필요 — 실행 계획 범위 밖)

| # | 항목 | 현재 상태 | 비고 |
|---|------|----------|------|
| 1 | Bedrock 10개 에이전트 벤치마크 | haiku 단건 결과(BV 0.86) 존재. 체계적 벤치마크 미실행 | 코드 준비 완료 |
| 2 | settings.yaml 최적 모델 반영 | 1번 완료 후 | — |
| 3 | GitHub Secrets 등록 | pr-body.md Phase 10 | deploy.yml이 10+ secrets 사용하나 존재 여부 미검증 |
| 4 | EC2 ALB DNS 확인 | pr-body.md Phase 10 | AWS 콘솔 |
| 5 | Neo4j 스키마 초기화 | pr-body.md Phase 10 | `init.cypher` 실행 필요. **deploy.yml에 자동화 미포함** [v2 추가] |
| 6 | Neo4j Backend 이관 | docker-compose 이관 주석 | 시기 미정 |
| 7 | t3.medium 메모리 압박 | AI(1.5GB)+Neo4j(1GB)+OS(0.5GB)=3GB/4GB | t3.large 업그레이드 권장 [v2 추가] |

> [v2 추가] **Neo4j 스키마 자동화 갭:** deploy.yml에 `init.cypher` 실행 단계가 없다.
> 첫 배포 시 Neo4j에 제약조건/인덱스가 없어 `_save_got_to_neo4j()` 실패 가능.
> deploy.yml에 health check 후 cypher-shell 실행 단계 추가를 권장한다.

---

## 데이터 영속화 — 현재 상태

| 컴포넌트 | 현재 | 의존 |
|---------|------|------|
| `base_memory._save_to_store()` | `return True` (stub) | KT Cloud 계약 |
| `episode_memory` 저장소 | `mock_db.json` (로컬 파일) | Pinecone + KT Cloud |
| DB 클라이언트 (Neo4j, Pinecone, MySQL, S3) | ✅ 실제 구현 | — |
| API Proxy | stub (13 TODO) | 백엔드 엔드포인트 확정 |

---

## 장기 로드맵 (현재 계획 범위 밖)

> [v2 수정] 구현 수준을 실제 코드 검증 결과로 보정.

| 항목 | 구현 수준 | 설명 | 다음 단계 |
|------|----------|------|----------|
| **대화모드** | 미착수 | workflow에서 완전 제거됨. stub 없음 | 재설계 필요 |
| **Telemetry 대시보드** | 98% [v2: "부분"→98%] | `MindLogTelemetryCallback` + 5개 메트릭 모델 + Prometheus 엔드포인트 완성. podcasts.py 런타임 통합 완료. Agent별 메트릭 기록 로직만 미흡 | Prometheus `record_pipeline()` agent_metrics 순회 보강 |
| **WebSocket 스트리밍** | SSE 100% [v2 보정] | SSE 엔드포인트(`/episodes/stream`) 완전 구현. StreamEvent 스키마 정의 완료. WebSocket 핸들러만 미구현 | WebSocket route 추가 (SSE 인프라 재활용 가능) |
| **A/B 테스트** | 95% [v2: "프레임워크"→95%] | base_agent.py에 MD5 해시 기반 세션 할당, ContextVar 격리, variant 프롬프트 preload 등 전체 코드 구현. loader.py에 `get_ab_test_config()` 완성 | settings.yaml에 `ab_tests:` 섹션 20줄 추가만으로 즉시 활성화 가능 |
| **프로덕션 운영** | 80% [v2 추가] | CI/CD, Health Check(`/health`, `/health/ready`), Prometheus `/metrics` 구현. LangSmith 트레이싱 연동 | Circuit Breaker 검증, 알림 시스템 |

---

## 실행 요약

| Phase | 작업 | 핵심 결과 | 난이도 | 커밋 |
|-------|------|----------|--------|------|
| **1** | Python 호환성 + mypy 63에러 | CI green 상태 확보 | 중간 | 1 |
| **2** | 잔여 테스트 실패 수정 | 테스트 스위트 안정화 (0 fail, 0 error) | 낮음 | 1 |
| **3** | Stub → 실제 에이전트 연결 | 추론 품질 향상 (빈 결과 → 실제 데이터) | 중간 | 1 |
| **4** | personalizer 규칙 구현 | 태도/접근성 기반 개인화 동작 | 낮음~중간 | 1 |
| **5** | Dead code + 문서 정리 | 깨끗한 코드베이스 | 낮음 | 1 |
| | | | **합계** | **5 커밋** |

**의존 관계:**
- Phase 1 → 2 (mypy 수정이 import 체인 복구)
- Phase 2 완료 후 Phase 3, 4는 **병렬 실행 가능** (파일 겹침 없음)
- Phase 5는 완전 독립

**범위 밖:** 백엔드 협의 6건, EC2 작업 7건, 장기 로드맵 5건 — 별도 트래킹.

---

### v2 수정 이력

| 항목 | v1 | v2 | 수정 근거 |
|------|----|----|----------|
| Phase 1 | mypy만 | Python 3.9 호환성 추가 | schemas.py:43이 19 error + 4 failed의 근본 원인 (검증됨) |
| Phase 2 | 5 fail + 19 error 개별 수정 | Phase 1 완료 후 잔여만 수정 | 24건 중 23건이 schemas.py 연쇄 (검증됨) |
| Phase 3 | "어댑터 추가" | 반환 형식 불일치 명시 + storage.mode 전제조건 | 실제 에이전트 반환값이 stub과 구조가 다름 (검증됨) |
| Phase 4 | 분기 구현 | ATTITUDE_SETTINGS 키워드 활용 명시 + 호출 경로 확인 | app_config.py에 이미 키워드 정의됨 (검증됨) |
| Phase 5 | dead code + echo | 스테일 문서/파일 정리 추가 | pr-body.md, PROJECT_DECISIONS.md, external_schemas.py TODO 스테일 (검증됨) |
| 백엔드 목록 | 9건 | 6건 | 4건이 잘못 분류: max_length(이미 구현), S3 prefix(설정 결정), storage.mode(DevOps), profile 쿼리(local 가능) |
| API Proxy TODO | 12건 | 13건 | 실측 13건 (검증됨) |
| 리소스 경로 | 4건 | 5건 | 실측 5건 (검증됨) |
| Telemetry | "부분 구현" | 98% | Callback+Models+Prometheus+런타임 통합 완료 확인 (검증됨) |
| A/B 테스트 | "프레임워크 완성" | 95% | MD5 해시 할당, ContextVar, preload 등 전체 구현 확인 (검증됨) |
| 인프라 | 6건 | 7건 | Neo4j 스키마 자동화 갭, t3.medium 메모리 압박 추가 (검증됨) |

---

*작성일: 2026-04-06 v2 | 기준: develop (194116e) | 검증: 10개 병렬 에이전트*

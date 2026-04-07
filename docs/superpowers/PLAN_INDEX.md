# 마스터 계획 인덱스 (Master Plan Index)

**목적**: 모든 기획 문서의 현황 추적 및 상태 관리  
**버전**: v9  
**마지막 업데이트**: 2026-04-07  
**관리 원칙**:
- 완료된 계획 → PR 링크 + 간단한 변경 사항 기록
- 미완료 계획 → 상태 및 다음 액션 기록
- 기존 파일은 모두 유지 (삭제 없음)

---

## 요약 표

| # | 계획명 | 파일 | 상태 | PR | 비고 |
|----|--------|------|------|-----|------|
| 1 | Bedrock 모델 최적화 | `2026-03-30-bedrock-model-optimization.md` | ✅ 완료 | #39 | Task 1-7 완료 |
| 2 | 팟캐스트 동시 요청 격리 | `2026-03-30-podcast-concurrency-isolation.md` | ✅ 완료 | #38 | 298 테스트 통과 |
| 3 | 동시성 격리 리팩토링 정리 | `2026-03-30-refactor-commit-and-cleanup.md` | ✅ 완료 | #38 | v27 커밋(ffe5290) 포함 |
| 4 | Bedrock 모델 최적화 v2 | `2026-03-31-bedrock-model-optimization-v2.md` | ✅ 완료 | #39, #46 | Task 1-7 완료 — 에이전트별 최적 모델 settings.yaml 반영 (Phase 3 결과) |
| 5 | 대화모드 잔재 제거 | `2026-03-31-conversation-removal.md` | ✅ 완료 | #45, #48, #49, #61 | 빈 디렉토리 제거 완료 |
| 6 | 프로젝트 종합 점검 (품질) | `2026-03-31-project-quality-review.md` | ✅ 완료 | #48, #52, #58, #60, #61, #62 | 9개 Phase 전체 완료 (Phase 8-9 문서 정리 포함) |
| 7 | 잔여 테스트 현황 확인 | `2026-03-31-remaining-issues-investigation.md` | ✅ 완료 | #46, #48, #59 | D-2 SSM wait, C-2 프로바이더 분기, D-3 printf 모두 해결 |
| 8 | 종합 점검 (미완료/미해결) | `2026-04-01-comprehensive-review.md` | ✅ 완료 | #48, #49, #52, #58 | 코드 항목 전부 해결 (A-1~D-3, mypy, 3.9 호환). 잔여: 외부 의존성(E-2)/장기 로드맵(H-*) |
| 9 | Neo4j 배포 + 프론트엔드 그래프 | `2026-04-02-neo4j-deployment-frontend-graph.md` | ✅ 완료 | #50, #51 | GoT→Neo4j→Backend 완료 |
| 10 | AWS 환경변수 & 보안 | `2026-04-06-aws-env-remediation.md` | ✅ 완료 | #59 | STORAGE_MODE, BACKEND_API_URL 완료 |
| 11 | 종합 실행 계획서 (2026-04-06) | `2026-04-06-comprehensive-execution-plan.md` | ✅ 완료 | #52, #57 | Phase 1-2 완료 (mypy, 테스트 격리) |
| 12 | 미완료 항목 현황 (2026-04-06) | `2026-04-06-pending-items-inventory.md` | 🔶 대부분 완료 | #52 | mypy/테스트 해결. 잔여: stub 에이전트(Pinecone), personalizer 분기, 영속화 레이어 |
| 13 | 파이프라인 견고성 (아카이브) | `2026-04-06-pipeline-robustness-remediation.md` | 📁 아카이브 | — | v1-v4 이력 보존 |
| 14 | 파이프라인 견고성 강화 마스터 | `pipeline-robustness-index.md` | ✅ 완료 | #60 | 13개 취약점 수정 |
| 15 | 파이프라인 견고성 - Phase 1 | `pipeline-robustness-part1.md` | ✅ 완료 | #60 | Changes 1-9 완료 |
| 16 | 파이프라인 견고성 - Phase 2 | `pipeline-robustness-part2.md` | ✅ 완료 | #60 | get_fallback_output() 추가 |
| 17 | 독스트링 품질 개선 구현 | `plans/2026-04-07-docs-quality-implementation.md` | ✅ 완료 | #61 (MERGED) | Phase 1-4 구현 + CB/SSE 테스트 추가 (479 passed, 14 skipped) |
| 18 | Neo4j 통합 구현 계획 | `plans/2026-04-07-neo4j-integration-plan.md` | 🔶 대부분 완료 | — | seed group 필드 수정 완료, E2E 검증은 인프라 선행 필요 |
| 19 | Pinecone 벡터 DB 공통 인프라 | `plans/2026-04-07-pinecone-vector-db-integration.md` | 🔶 일부 완료 | — | CLI 스크립트+pinecone_client 구현. 미완: BedrockEmbeddingClient, 팩토리 연동, 테스트 |

**범례:**
- ✅ 완료 — 코드 구현 완료, PR 머지됨
- 🔶 대부분 완료 — 핵심 작업 완료, 소규모 잔여 항목 존재
- 🔲 구현 대기 — 계획서 작성 완료, 구현 명령 대기 중
- 📁 아카이브 — 참조용 (독립 구현 목표 없음)

---

## 실제 미완료 항목 전체 (2차 교차 검증 기준)

### 그룹 1: 소규모 코드 정리 ✅ 완료 — PR #61

| # | 작업 | 파일 | 상태 |
|---|------|------|------|
| 1 | safety.py 독스트링 Google-style 통일 | `src/agents/podcast/safety.py` | ✅ `7c80efd` |
| 2 | batch_validator.py 독스트링 Google-style 통일 | `src/agents/podcast/batch_validator.py` | ✅ `228faf4` |
| 3 | external_schemas.py docstring 불일치 수정 | `src/api/external_schemas.py` | ✅ `c114a55` |
| 4 | src/agents/conversation/ 빈 디렉토리 제거 | `src/agents/conversation/` | ✅ Git 미추적 디렉토리 삭제 |

### 그룹 2: 테스트 보완 ✅ 완료

| # | 작업 | 파일 | 상태 |
|---|------|------|------|
| 5 | Circuit Breaker 상태 전환 테스트 | `tests/agents/shared/test_llm_client.py` | ✅ 9개 테스트 추가 (CLOSED→OPEN, OPEN→HALF_OPEN, HALF_OPEN→CLOSED/OPEN 등) |
| 6 | SSE `/episodes/stream` 엔드포인트 테스트 | `tests/api/test_sse_streaming.py` | ✅ 11개 테스트 추가 (SSE 이벤트 시퀀스, 에러 핸들링, 422 검증) |

### 그룹 3: 외부 의존성 (코드로 해결 불가)

| # | 작업 | 담당 | 상태 |
|---|------|------|------|
| ~~7~~ | ~~Bedrock EC2 벤치마크~~ | ~~인프라~~ | ✅ 완료 — 에이전트별 최적 모델 settings.yaml 반영 |
| 8 | TODO(backend) 21건 해소 | 백엔드 팀 | api_proxy.py 15건, backend_resources.py 5건, s3_client.py 1건 |
| 9 | API Key 인증 / max_length / Rate Limiting 협의 | 백엔드 팀 | comprehensive-review.md H-2,5,E-2 |
| ~~10~~ | ~~Neo4j Backend 이관~~ | — | ✅ 이관 불필요 — AI 서버에서 직접 운영 확정 |

### 그룹 4: 보안 수동 조치 (SECURITY_REMEDIATION_TRACKER.md)

| # | 작업 | 상태 |
|---|------|------|
| 11 | KT Cloud API 토큰 로테이션 | ❌ 미완료 |
| 12 | OpenAI API 키 로테이션 | ❌ 미완료 |
| 13 | LangSmith API 키 로테이션 | ❌ 미완료 |
| 14 | Grafana/OpenSearch 비밀번호 변경 | ❌ 미완료 |
| 15 | 로컬 DB 비밀번호 재설정 | ❌ 미완료 |
| 16 | Git history 정리 (KT Cloud 토큰 잔존) | ❌ 미완료 — 3인 합의 필요 |

### 그룹 5: 기능 미구현 (Pinecone/DB 연동 후 처리)

| # | 작업 | 파일 | 라인 | 의존성 |
|---|------|------|------|--------|
| 17 | EpisodeMemoryStub → 실제 에이전트 DI 연결 | `podcast_reasoning.py` | 58-59 | Pinecone 연동 |
| 18 | base_memory._save_to_store() stub 구현 | `base_memory.py` | 88-89 | KT Cloud API |
| 19 | episode_memory mock_db.json → Pinecone 전환 | `episode_memory.py` | 15 | Pinecone 연동 |
| 20 | script_personalizer empathetic/rational 구현 | `script_personalizer.py` | 402, 405 | 비즈니스 규칙 정의 |
| 21 | script_personalizer hearing_impairment 구현 | `script_personalizer.py` | 450 | 비즈니스 규칙 정의 |
| 22 | _query_user_profile() MySQL 구현 | `script_personalizer.py` | 275 | DB 연결 |
| 23 | data/cache/ 디렉토리 생성 | 프로젝트 루트 | — | episode_memory 런타임 의존 |

---

## 이미 구현된 주요 기능 (체크리스트 오인 방지)

| 기능 | 위치 | 완료 PR |
|------|------|--------|
| Circuit Breaker (구현체) | `src/agents/shared/llm_client.py:42` | 기존 구현 |
| Circuit Breaker 상태 전환 테스트 (9개) | `tests/agents/shared/test_llm_client.py` | `eaa6c28` |
| SSE 스트리밍 엔드포인트 | `src/api/routes/podcasts.py:381` | PR #48 |
| SSE 스트리밍 엔드포인트 테스트 (11개) | `tests/api/test_sse_streaming.py` | `eaa6c28` |
| 프롬프트 인젝션 방어 | `src/agents/shared/input_sanitizer.py` | PR #58 |
| PII 정제 | `src/agents/shared/output_sanitizer.py` | PR #58 |
| 타입 힌트 현대화 (Dict→dict) | 전체 에이전트 | PR #52 |
| TIER 0~4 타임아웃 래퍼 | `src/graph/workflow.py` | PR #48/#60 |
| mypy 63개 에러 수정 | 전체 | PR #52 |
| Python 3.9 호환성 | `schemas.py` 등 | PR #52 |
| 대화모드 제거 (기능) | 전체 | PR #45/#48/#49 |
| features 섹션 비활성화 | `config/settings.yaml:207` | 주석 처리됨 |
| prompts/_archive/ README | `prompts/podcast/_archive/README.md` | 작성됨 |
| AGENT_ROLES.md 모델명/이슈 갱신 | `docs/architecture/AGENT_ROLES.md` | PR #62 |
| QUICK_START.md ProjectDocs 참조 수정 | `docs/getting-started/QUICK_START.md` | PR #62 |
| README.md 프로젝트 구조 보완 | `README.md` | PR #62 |
| 코드 품질 9개 Phase 전체 완료 | `QUALITY_REVIEW_CHECKLIST.md` v6 | PR #52~#62 |
| 루트 테스트 파일 이동 | — | 파일 자체 없음 |
| deploy.yml printf 전환 | `.github/workflows/deploy.yml` | PR #59 |

---

## 완료 계획 상세 (주요 PR)

| PR | 브랜치 | 주요 작업 |
|----|--------|----------|
| #38 | refactor/concurrency-isolation | 동시성 격리, v27 리팩토링 |
| #39 | feature/bedrock-model-optimization | Bedrock 멀티 프로바이더 |
| #45 | refactor/podcast-only-conversion | 대화모드 Phase 1-3 |
| #46 | feature/bedrock-model-optimization-v2 | D-2/C-2/D-3, 최적 모델 반영 |
| #48 | feature/validation-comprehensive-review | SSE, 타임아웃, dead code, deploy.yml |
| #49 | feature/validation-comprehensive-review | 대화모드 Phase 5-6, 문서 |
| #50/#51 | feature/neo4j-deployment-frontend-graph | GoT→Neo4j, 그래프 API |
| #52 | feature/ci-fix-mypy-deadcode | mypy 63→0, Python 3.9 |
| #53 | feature/validation-graph-cumulative | 누적 그래프 저장 |
| #57 | feature/validation-ci-test-isolation-fix | CI 테스트 격리 |
| #58 | feature/reasoning-security-remediation | 보안 강화 |
| #59 | feature/reasoning-aws-env-remediation | 환경변수 보안 |
| #60 | feature/reasoning-pipeline-robustness | 파이프라인 취약점 13개 |
| #61 | feature/reasoning-docs-quality | 독스트링 품질 + CB/SSE 테스트 (MERGED) |
| #62 | feature/reasoning-code-quality-cleanup | 코드 품질 정리 — dead code 제거 + Phase 8-9 문서 (OPEN) |

---

*마스터 인덱스 v9 — 2026-04-07 (Plan #4/#7/#8 완료 확인, #12 mypy/테스트 해결, #19 일부 구현)*

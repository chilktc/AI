# 마스터 계획 인덱스 (Master Plan Index)

**목적**: 모든 기획 문서의 현황 추적 및 상태 관리  
**마지막 업데이트**: 2026-04-07 (3-에이전트 교차 검증 완료)  
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
| 4 | Bedrock 모델 최적화 v2 | `2026-03-31-bedrock-model-optimization-v2.md` | 🔶 대부분 완료 | #39, #46 | EC2 벤치마크(Task 6)만 미완료 |
| 5 | 대화모드 잔재 제거 | `2026-03-31-conversation-removal.md` | ✅ 완료 | #45, #48, #49 | Phase 1-6 모두 완료 |
| 6 | 프로젝트 종합 점검 (품질) | `2026-03-31-project-quality-review.md` | 🔶 대부분 완료 | #48, #52, #58, #60 | Phase 2(독스트링), 4(주석/링크) 미완료 |
| 7 | 잔여 테스트 현황 확인 | `2026-03-31-remaining-issues-investigation.md` | 🔶 대부분 완료 | #46, #48 | EC2 Bedrock 벤치마크만 미완료 |
| 8 | 종합 점검 (미완료/미해결) | `2026-04-01-comprehensive-review.md` | ✅ 완료 | #52, #48, #49 | Phase 3/4는 의도적 보류 유지 |
| 9 | Neo4j 배포 + 프론트엔드 그래프 | `2026-04-02-neo4j-deployment-frontend-graph.md` | ✅ 완료 | #50, #51 | GoT→Neo4j→Backend 완료 |
| 10 | AWS 환경변수 & 보안 | `2026-04-06-aws-env-remediation.md` | ✅ 완료 | #59 | STORAGE_MODE, BACKEND_API_URL 완료 |
| 11 | 종합 실행 계획서 (2026-04-06) | `2026-04-06-comprehensive-execution-plan.md` | ✅ 완료 | #52, #57 | Phase 1-2 완료 (mypy, 테스트 격리) |
| 12 | 미완료 항목 현황 (2026-04-06) | `2026-04-06-pending-items-inventory.md` | 📁 참고 | — | 교차검증 완료, 인벤토리 역할 |
| 13 | 파이프라인 견고성 (아카이브) | `2026-04-06-pipeline-robustness-remediation.md` | 📁 아카이브 | — | v1-v4 이력 보존 |
| 14 | 파이프라인 견고성 강화 마스터 | `pipeline-robustness-index.md` | ✅ 완료 | #60 | 13개 취약점 수정 |
| 15 | 파이프라인 견고성 - Phase 1 | `pipeline-robustness-part1.md` | ✅ 완료 | #60 | Changes 1-9 완료 |
| 16 | 파이프라인 견고성 - Phase 2 | `pipeline-robustness-part2.md` | ✅ 완료 | #60 | get_fallback_output() 추가 |

**범례:**
- ✅ 완료 — 코드 구현 완료, PR 머지됨
- 🔶 대부분 완료 — 핵심 작업 완료, 일부 항목 미완료
- 📁 참고/아카이브 — 참조용 (독립 구현 목표 없음)

---

## 실제 미완료 항목 (3-에이전트 교차 검증 결과)

교차 검증(2026-04-07)으로 대부분의 계획이 이미 완료됨을 확인했습니다.  
**진짜 남은 작업은 3가지입니다:**

| # | 작업 | 출처 계획 | 우선순위 | 브랜치 |
|---|------|----------|---------|--------|
| **1** | 독스트링 보강 (Google-style 통일) | Plan#4 Phase 2 | 🔴 높음 | feature/reasoning-docs-quality |
| **2** | 주석 보완 + 깨진 링크 수정 | Plan#4 Phase 4 | 🟡 중간 | feature/reasoning-docs-quality |
| **3** | Bedrock EC2 벤치마크 실행 | Plan#2 Task 6 = Plan#5 Step 2 | 🟢 낮음 (인프라 별도) | 코드 변경 없음 |

---

## 완료 계획 상세 (주요 PR)

| PR | 브랜치 | 주요 작업 | 커밋 수 |
|----|--------|----------|--------|
| #38 | refactor/concurrency-isolation | 동시성 격리, v27 리팩토링 | 8 |
| #39 | feature/bedrock-model-optimization | Bedrock 멀티 프로바이더, 모델 테스트 파이프라인 | 10 |
| #45 | refactor/podcast-only-conversion | 대화모드 Phase 1-3 제거 | 8 |
| #46 | feature/bedrock-model-optimization-v2 | D-2/C-2/D-3 수정, 최적 모델 반영 | 5 |
| #48 | feature/validation-comprehensive-review | SSE, TIER 타임아웃, dead code, deploy.yml | 15 |
| #49 | feature/validation-comprehensive-review | 대화모드 Phase 5-6, AGENT_ROLES.md | 5 |
| #50, #51 | feature/neo4j-deployment-frontend-graph | GoT→Neo4j 저장, 그래프 API | 12 |
| #52 | feature/ci-fix-mypy-deadcode | mypy 63→0, Python 3.9 호환성, dead code | 3 |
| #57 | feature/validation-ci-test-isolation-fix | CI 테스트 격리 | 2 |
| #58 | feature/reasoning-security-remediation | 민감정보 제거, 인젝션 방어, PII | 3 |
| #59 | feature/reasoning-aws-env-remediation | 환경변수 보안, .env.db 제거 | 5 |
| #60 | feature/reasoning-pipeline-robustness | 파이프라인 취약점 13개 수정 | 10 |

---

## 이미 구현된 주요 기능 (체크리스트 오인 방지)

다음 기능들은 이미 구현 완료됩니다. **별도 구현 불필요:**

| 기능 | 위치 | 완료 PR |
|------|------|--------|
| Circuit Breaker | `src/agents/shared/llm_client.py:42` | PR #48/기존 구현 |
| SSE 스트리밍 | `POST /episodes/stream` 엔드포인트 | PR #48 |
| 프롬프트 인젝션 방어 | `input_sanitizer.py` | PR #58 |
| PII 정제 | `output_sanitizer.py` | PR #58 |
| 타입 힌트 현대화 (Dict→dict) | 전체 에이전트 | PR #52 |
| TIER 2-4 타임아웃 래퍼 | `workflow.py` | PR #48/#60 |
| mypy 63개 에러 | 전체 | PR #52 |
| Python 3.9 호환성 | `schemas.py` 등 | PR #52 |
| 대화모드 제거 | 전체 | PR #45/#48 |

---

*마스터 인덱스 v2 — 2026-04-07 (3-에이전트 교차 검증 반영)*

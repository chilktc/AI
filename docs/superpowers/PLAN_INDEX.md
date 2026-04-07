# 마스터 계획 인덱스 (Master Plan Index)

**목적**: 모든 기획 문서의 현황 추적 및 상태 관리  
**마지막 업데이트**: 2026-04-07  
**관리 원칙**: 
- 완료된 계획 → PR 링크 + 간단한 변경 사항 기록
- 미완료 계획 → 상태 및 다음 액션 기록
- 기존 파일은 모두 유지 (삭제 없음)

---

## 요약 표

| # | 계획명 | 파일 | 상태 | PR | 커밋 수 |
|----|--------|------|------|-----|--------|
| 1 | Bedrock 모델 최적화 | `2026-03-30-bedrock-model-optimization.md` | ✅ 완료 | #39 | 10 |
| 2 | 팟캐스트 동시 요청 격리 | `2026-03-30-podcast-concurrency-isolation.md` | ✅ 완료 | #38 | 8 |
| 3 | 동시성 격리 리팩토링 정리 | `2026-03-30-refactor-commit-and-cleanup.md` | ⏸️ 보류 | — | — |
| 4 | Bedrock 모델 최적화 v2 | `2026-03-31-bedrock-model-optimization-v2.md` | ⏸️ 보류 | — | — |
| 5 | 대화모드 잔재 제거 | `2026-03-31-conversation-removal.md` | ⏸️ 보류 | — | — |
| 6 | 프로젝트 종합 점검 (품질) | `2026-03-31-project-quality-review.md` | ⏸️ 검토 중 | — | — |
| 7 | 잔여 테스트 현황 확인 | `2026-03-31-remaining-issues-investigation.md` | ⏸️ 검토 중 | — | — |
| 8 | 종합 점검 (미완료/미해결) | `2026-04-01-comprehensive-review.md` | ⏸️ 검토 중 | — | — |
| 9 | Neo4j 배포 + 프론트엔드 그래프 | `2026-04-02-neo4j-deployment-frontend-graph.md` | ✅ 완료 | #50, #51 | 12 |
| 10 | AWS 환경변수 & 보안 | `2026-04-06-aws-env-remediation.md` | ✅ 완료 | #59 | 5 |
| 11 | 종합 실행 계획서 (2026-04-06 v2) | `2026-04-06-comprehensive-execution-plan.md` | ⏸️ 검토 중 | — | — |
| 12 | 미완료 항목 현황 (2026-04-06) | `2026-04-06-pending-items-inventory.md` | ⏸️ 인벤토리 | — | — |
| 13 | 파이프라인 견고성 (아카이브) | `2026-04-06-pipeline-robustness-remediation.md` | 📁 아카이브 | — | — |
| 14 | 파이프라인 견고성 강화 마스터 | `pipeline-robustness-index.md` | ✅ 완료 | #60 | 10 |
| 15 | 파이프라인 견고성 - Phase 1 | `pipeline-robustness-part1.md` | ✅ 완료 | #60 | 10 |
| 16 | 파이프라인 견고성 - Phase 2 | `pipeline-robustness-part2.md` | ✅ 완료 | #60 | 10 |

**범례:**
- ✅ 완료 — 코드 구현 완료, PR 머지됨
- ⏸️ 보류 — 계획은 작성됨, 구현 미진행
- ⏸️ 검토 중 — 검토 대상 계획 (미구현)
- ⏸️ 인벤토리 — 상태 조사 문서 (action item 기록)
- 📁 아카이브 — 이전 버전 (아카이브용)

---

## 완료 계획 (5개)

### 1. Bedrock 모델 최적화 (PR #39)
- **파일**: `2026-03-30-bedrock-model-optimization.md`
- **변경사항**: 
  - Bedrock 멀티 프로바이더 지원 (Claude, Llama, Mistral)
  - 모델별 매개변수 맵핑 및 오류 처리
  - 테스트 파이프라인 (단일 워커, 배치 워커)
- **커밋**: `6f4e016` ~ `24f0b96` (10개)

### 2. 팟캐스트 동시 요청 격리 (PR #38)
- **파일**: `2026-03-30-podcast-concurrency-isolation.md`
- **변경사항**:
  - 동시 요청 격리 (별도 Agent 인스턴스 생성)
  - StateGraph 노드 함수 패턴 표준화
  - 298 테스트 통과 확인
- **커밋**: `6f88d6e` ~ `a586467` (8개)

### 3. Neo4j 배포 + 프론트엔드 그래프 (PR #50, #51)
- **파일**: `2026-04-02-neo4j-deployment-frontend-graph.md`
- **변경사항**:
  - GoT 결과 Neo4j 저장
  - Backend 프록시 API (그래프 조회)
  - 프론트엔드 그래프 변환 레이어
- **커밋**: `763e3fb` ~ `95f956c` (12개)

### 4. AWS 환경변수 & 보안 (PR #59)
- **파일**: `2026-04-06-aws-env-remediation.md`
- **변경사항**:
  - STORAGE_MODE 환경변수화
  - BACKEND_API_URL 폴백 방어
  - .env.db 추적 제거
  - CI/CD 환경 정비
- **커밋**: `5e5b5af` ~ `a6b9019` (5개)

### 5. 파이프라인 견고성 강화 (PR #60)
- **파일**: `pipeline-robustness-index.md`, `pipeline-robustness-part1.md`, `pipeline-robustness-part2.md`
- **변경사항**:
  - 13개 취약점 수정 (Changes 1-9)
  - 에이전트 크래시, 빈 응답 통과, Blind retry 방어
  - 설정값 조정 (max_retries 축소)
  - 8개 파일, 24개 테스트 신규 추가
- **커밋**: `f54d449` ~ `156ef8c` (10개)

---

## 미완료 계획 (7개)

### 상태: 검토 중 / 구현 대기

| 문서 | 설명 | 우선순위 | 다음 액션 |
|------|------|----------|----------|
| `2026-03-31-project-quality-review.md` (59KB) | 코드 품질, 컨벤션, 주석, 폴더 구조 종합 점검 | 🔴 높음 | Haiku 탐색 → 목록화 |
| `2026-04-01-comprehensive-review.md` (54KB) | 미완료/미해결 항목 종합 정리 | 🔴 높음 | 검토 필요 |
| `2026-04-06-comprehensive-execution-plan.md` (16KB) | 통합 실행 계획 | 🟡 중간 | 검토 필요 |
| `2026-04-06-pending-items-inventory.md` (8.5KB) | 미완료 항목 인벤토리 | 🟡 중간 | 정리 필요 |

### 상태: 보류 중

| 문서 | 설명 | 이유 | 다음 액션 |
|------|------|------|----------|
| `2026-03-30-refactor-commit-and-cleanup.md` | 동시성 리팩토링 정리 | 후속 청소 작업 | 필요시 수행 |
| `2026-03-31-bedrock-model-optimization-v2.md` | Bedrock v2 재설계 | v1 완료 후 평가 필요 | 추후 검토 |
| `2026-03-31-conversation-removal.md` | 대화모드 제거 | 팟캐스트 전용 전환 | 추후 검토 |

---

## 아카이브

| 문서 | 설명 |
|------|------|
| `2026-04-06-pipeline-robustness-remediation.md` (75KB) | 파이프라인 견고성 v1-v4 아카이브 (v5는 별도 파일) |

---

## 다음 단계

**즉시 (이번 세션):**
1. `2026-03-31-project-quality-review.md` → Haiku로 탐색/목록화 (`docs/superpowers/explorations/` 생성)
2. 미구현 계획 4개 검토 및 우선순위 재정리

**장기:**
- Neo4j 배포 이후 생길 후속 작업 추적
- 각 완료된 PR의 "다음 단계" 검증

---

*마스터 인덱스 v1 — 2026-04-07*

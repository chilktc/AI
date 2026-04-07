# 문서 인덱스

Mind-Log 프로젝트 문서 마스터 네비게이션입니다.

> **처음 보는 문서**: `QUICK_START.md` → `CLAUDE.md` → `WHY.md` 순서로 읽을 것.

---

## 핵심 참조

| 문서 | 설명 |
|------|------|
| [WHY.md](WHY.md) | **설계 결정과 진화 이력** — 왜 이렇게 구현했는가, 왜 삭제되었는가 |
| [SECURITY_REMEDIATION_TRACKER.md](SECURITY_REMEDIATION_TRACKER.md) | 보안 후속 조치 추적 (키 로테이션 등 미완료 항목) |

## 시작하기 (Getting Started)

| 문서 | 설명 |
|------|------|
| [QUICK_START.md](getting-started/QUICK_START.md) | 환경 설정 및 첫 에이전트 개발 가이드 |

## 아키텍처 (Architecture)

| 문서 | 설명 |
|------|------|
| [AGENT_ROLES.md](architecture/AGENT_ROLES.md) | 에이전트별 역할·입출력·스키마·이슈 정의서 |
| [API_SPEC.md](architecture/API_SPEC.md) | REST API 명세 인덱스 (v2.0, 5개 문서 모음) |
| [API_ARCHITECTURE.md](architecture/API_ARCHITECTURE.md) | 서버 구조 & 파이프라인 실행 흐름 |
| [API_ENDPOINTS_RECEIVING.md](architecture/API_ENDPOINTS_RECEIVING.md) | 수신 API (Backend→AI) 9개 엔드포인트 |
| [API_ENDPOINTS_INTERNAL.md](architecture/API_ENDPOINTS_INTERNAL.md) | 발신 API (AI→Backend) 5개 + Load API |
| [API_COMMON.md](architecture/API_COMMON.md) | 스트리밍 이벤트, 에러 코드, 재시도 정책 |
| [DATA_SCHEMA.md](architecture/DATA_SCHEMA.md) | DB 스키마 (MySQL 7테이블, Pinecone 2인덱스, Neo4j, S3) |
| [NEO4J_INTEGRATION.md](architecture/NEO4J_INTEGRATION.md) | Neo4j 통합 명세 v1.3 |
| [VECTOR_DB_RAG_GUIDE.md](architecture/VECTOR_DB_RAG_GUIDE.md) | Pinecone 벡터 DB + RAG 가이드 |

## 개발 가이드 (Guides)

| 문서 | 설명 |
|------|------|
| [AGENT_DEV_GUIDE.md](guides/AGENT_DEV_GUIDE.md) | 에이전트 구현 체크리스트, 템플릿, 테스트 패턴 |
| [E2E_TEST_GUIDE.md](guides/E2E_TEST_GUIDE.md) | LangGraph E2E 워크플로우 테스트 가이드 |
| [PROMPT_VERSIONING.md](guides/PROMPT_VERSIONING.md) | 프롬프트 멀티버전 관리 및 A/B 테스트 |

## 보고서 / 의사결정 (Reports)

| 문서 | 설명 |
|------|------|
| [PROJECT_DECISIONS.md](reports/PROJECT_DECISIONS.md) | 설계 결정 18개 ADR + 초기 계획 대비 변경사항 |
| [REFACTORING_LOG.md](reports/REFACTORING_LOG.md) | 리팩토링 이력 (v18까지) |

## 구현 계획 (Active Plans)

> 전체 계획 현황: [PLAN_INDEX.md](superpowers/PLAN_INDEX.md)
> 구현 로드맵: [IMPLEMENTATION_ROADMAP.md](superpowers/IMPLEMENTATION_ROADMAP.md)

| 문서 | 상태 | 설명 |
|------|------|------|
| [2026-04-06-pending-items-inventory.md](superpowers/plans/2026-04-06-pending-items-inventory.md) | 🔶 진행 중 | 잔여 미완료 항목 목록 |
| [2026-04-07-neo4j-integration-plan.md](superpowers/plans/2026-04-07-neo4j-integration-plan.md) | 🔶 진행 중 | Neo4j E2E 검증 대기 |
| [2026-04-07-pinecone-vector-db-integration.md](superpowers/plans/2026-04-07-pinecone-vector-db-integration.md) | 🔶 진행 중 | BedrockEmbeddingClient 미구현 |

## 변경 이력 (Recent Changelog)

| 문서 | 설명 |
|------|------|
| [CHANGELOG_v28.md](changelog/CHANGELOG_v28.md) | v28 — 문서 전수 점검 4사이클 (PR #70~#80) |
| [CHANGELOG_v27.md](changelog/CHANGELOG_v27.md) | v27 — 동시성 격리 리팩토링 |
| [CHANGELOG_v26.md](changelog/CHANGELOG_v26.md) | v26 — Docker 배포 + Bedrock Converse API |
| [CHANGELOG_v25.md](changelog/CHANGELOG_v25.md) | v25 — API 응답 슬림화 + Visualization TIER 2 이동 |
| [CODE_AUDIT_CHANGELOG.md](changelog/CODE_AUDIT_CHANGELOG.md) | 코드 보안 감사 + 품질 개선 (2026-03-24) |
| [changelog/INDEX.md](changelog/INDEX.md) | 전체 changelog 인덱스 (v1~v28) |

## 아카이브

완료된 계획서, 구 changelog, 폐기된 가이드: [`_archive/`](_archive/README.md)

---

*마지막 업데이트: 2026-04-08*

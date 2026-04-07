# 변경이력 v28

> 날짜: 2026-04-08  
> 브랜치: feature/reasoning-docs-stage1 ~ feature/reasoning-docs-stage11  
> PR: #70 ~ #80 (전체 MERGED → develop)  
> 담당: 개발자2

---

## 개요

전체 `docs/` 문서를 4차 사이클 병렬 점검하여 대화모드 잔재, 링크 오류, 버전 불일치, 날짜 오류,
설계 결정 누락 등 총 **35개 항목**을 수정했다. 코드 변경 없음, 문서 전용.

---

## Stage 1 (PR #70) — 대화모드 잔재 제거 + 이슈 RESOLVED

- `docs/architecture/AGENT_ROLES.md`: 해소된 Known Issues RESOLVED 처리
- `docs/getting-started/QUICK_START.md`: 대화모드 참조 제거
- `README.md`: 구현 현황 에이전트 수 최신화

## Stage 2 (PR #71) — 버전/수치 동기화 + Neo4j PR 반영

- `docs/architecture/NEO4J_INTEGRATION.md`: PR #50/#51/#53 반영
- `docs/superpowers/IMPLEMENTATION_ROADMAP.md`: 테스트 수 v6 갱신
- `docs/reports/REFACTORING_LOG.md`: v27까지 이력 반영

## Stage 3 (PR #72) — 코드 예시/경로/기타 정합성

- 코드 블록 내 경로 오류 수정
- 환경변수명, 포트번호 SSOT(settings.yaml) 기준 동기화

## Stage 4 (PR #73) — 구식 문서 아카이브 + 미기재 기능 보충

- 구식 인프라 가이드 아카이브 레이블 추가
- `docs/architecture/AGENT_ROLES.md`: Circuit Breaker, InputSanitizer, OutputSanitizer 기재

## Stage 5 (PR #74) — HIGH: Pinecone 인덱스명 + 대화모드 잔재

- `docs/architecture/DATA_SCHEMA.md`: 인덱스명 하이픈 통일 (`mem-podcast-episode`, `expert-knowledge`)
- `docs/architecture/VECTOR_DB_RAG_GUIDE.md`: 20여 개 언더스코어 → 하이픈 일괄 수정
- `docs/architecture/API_ENDPOINTS_INTERNAL.md`: 대화모드 잔재 문구 제거
- `docs/guides/E2E_TEST_GUIDE.md`: `"podcast" 또는 "conversation"` → `"podcast"`
- `docs/getting-started/OLLAMA_SETUP.md`: DEPRECATED 블록 추가

## Stage 6 (PR #75) — MEDIUM: 테스트 수 + 날짜 + 에이전트 템플릿

- `docs/superpowers/PLAN_INDEX.md`: 테스트 수 479 → 538 갱신
- `docs/changelog/INDEX.md`: 날짜 갱신
- `docs/superpowers/specs/2026-03-31-project-review-design.md`: `response_draft` Synthesis TODO 제거
- `docs/guides/AGENT_DEV_GUIDE.md`: ContextAgent 예제 → EmotionAgent 예제 교체

## Stage 7 (PR #76) — LOW: 클래스명 + Mode A + 링크

- `docs/architecture/API_ARCHITECTURE.md`: `TelemetryCallback` → `MindLogTelemetryCallback`
- `docs/architecture/API_SPEC.md`: CLAUDE.md 링크 경로 수정
- `docs/getting-started/QUICK_START.md`: 상대경로 수정
- `docs/superpowers/plans/2026-03-31-project-quality-review.md`: 링크 경로 수정
- `docs/superpowers/specs/2026-04-06-graph-cumulative-rdb-design.md`: Mode A 다이어그램 제거 + PR #69 note
- `docs/reports/ZONE_CD_INTEGRATION_REPORT.md`: 역사적 보고서 경고 추가
- `docs/guides/AGENT_DEV_GUIDE.md`: CLAUDE.md 링크 수정

## Stage 8 (PR #77) — HIGH: 대화모드 잔재 + PROJECT_DECISIONS

- `docs/architecture/API_ENDPOINTS_INTERNAL.md`: Load API 설명 수정
- `docs/reports/PROJECT_DECISIONS.md`: 날짜 갱신, 중기 로드맵 대화모드 삭제 반영

## Stage 9 (PR #78) — MEDIUM: 앵커 + PLAN_INDEX + graph-design

- `docs/guides/E2E_TEST_GUIDE.md`: CLAUDE.md 앵커 `#팟캐스트모드-실행-흐름` → `#실행-흐름`
- `docs/superpowers/PLAN_INDEX.md`: Plan #20 PR `—` → `#69`, 테스트 수 516 → 538
- `docs/superpowers/specs/2026-04-06-graph-cumulative-rdb-design.md`: 헤더 상태 갱신, `upsert_mode`/`ema_alpha` 삭제 주석 전체 반영

## Stage 10 (PR #79) — LOW: 날짜 갱신

- `docs/guides/E2E_TEST_GUIDE.md`, `docs/getting-started/OLLAMA_SETUP.md`, `docs/guides/PROMPT_VERSIONING.md`: 날짜 `2026-04-07`
- `README.md`: CONTRIBUTING.md 설명 보완

## Stage 11 (PR #80) — 4차 점검 수정

- `docs/guides/PROMPT_VERSIONING.md`: Round 4 확정 조합 PR `v3.0.0` → `v3.1.0` 핀닝 반영
- `docs/guides/AGENT_DEV_GUIDE.md`: 날짜 `2026-03-24` → `2026-04-07`
- `docs/architecture/API_SPEC.md`: 대화모드 "향후 구현 시" 문구 제거
- `docs/architecture/AGENT_ROLES.md`: 인덱스명(하이픈)/네임스페이스(언더스코어) 분리 명시
- `docs/reports/PROJECT_DECISIONS.md`: 설계 결정 #15~#18 추가 (Neo4j, Pinecone, PII, Mode B)
- `docs/superpowers/specs/2026-03-31-project-review-design.md`: 완료 아카이브 표시 추가

---

## 수정 집계

| 구분 | 건수 |
|------|------|
| HIGH 수정 | 8건 |
| MEDIUM 수정 | 15건 |
| LOW 수정 | 12건 |
| **합계** | **35건** |

---

*코드 변경 없음 — 테스트 수 유지: 538 passed, 14 skipped*

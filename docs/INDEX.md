# 문서 인덱스

Mind-Log 프로젝트 문서 마스터 네비게이션입니다.

---

## 시작하기 (Getting Started)

| 문서 | 설명 |
|------|------|
| [QUICK_START.md](getting-started/QUICK_START.md) | 환경 설정 및 첫 에이전트 개발 가이드 |
| [OLLAMA_SETUP.md](getting-started/OLLAMA_SETUP.md) | Ollama 로컬 LLM 설정 가이드 |

## 아키텍처 (Architecture)

| 문서 | 설명 |
|------|------|
| [PROJECT_STRUCTURE.md](architecture/PROJECT_STRUCTURE.md) | 디렉토리 구조 및 파일 역할 |
| [AGENT_ROLES.md](architecture/AGENT_ROLES.md) | 에이전트별 역할·입출력·스키마·이슈 정의서 |
| [API_SPEC.md](architecture/API_SPEC.md) | REST API 명세 인덱스 (v2.0, 5개 문서 모음) |
| [API_ARCHITECTURE.md](architecture/API_ARCHITECTURE.md) | API 아키텍처 — 서버 구조 & 파이프라인 실행 흐름 |
| [API_ENDPOINTS_RECEIVING.md](architecture/API_ENDPOINTS_RECEIVING.md) | 수신 API (Backend→AI) 9개 엔드포인트 상세 |
| [API_ENDPOINTS_INTERNAL.md](architecture/API_ENDPOINTS_INTERNAL.md) | 발신 API (AI→Backend) 5개 + Load API |
| [API_COMMON.md](architecture/API_COMMON.md) | 스트리밍 이벤트, 에러 코드, 재시도 정책 |
| [DATA_SCHEMA.md](architecture/DATA_SCHEMA.md) | 데이터 스키마 명세 (MySQL 7테이블 + Pinecone 2인덱스 + Neo4j 5노드 + S3) |
| [DATA_SCHEMA_PLAN.md](architecture/DATA_SCHEMA_PLAN.md) | 데이터 스키마 설계 계획 (참고용) |

## 가이드 (Guides)

| 문서 | 설명 |
|------|------|
| [AGENT_DEV_GUIDE.md](guides/AGENT_DEV_GUIDE.md) | 에이전트 개발 상세 가이드 (템플릿, 테스트 패턴) |
| [GIT_WORKFLOW.md](guides/GIT_WORKFLOW.md) | 브랜치 전략, 커밋 컨벤션, PR 가이드 |
| [E2E_TEST_GUIDE.md](guides/E2E_TEST_GUIDE.md) | E2E 테스트 가이드 |
| [PROMPT_VERSIONING.md](guides/PROMPT_VERSIONING.md) | 프롬프트 멀티버전 관리 및 A/B 테스트 가이드 |
| [INFRA_DEPLOYMENT_GUIDE.md](guides/INFRA_DEPLOYMENT_GUIDE.md) | 인프라 배포 가이드 (Docker, AWS) |
| [AI_Team_Work_Zone_Assignment.md](guides/AI_Team_Work_Zone_Assignment.md) | AI 팀 작업 영역(Zone) 배정표 |
| [ZONE_CD_INTEGRATION_AND_BACKEND_TEST_GUIDE.md](guides/ZONE_CD_INTEGRATION_AND_BACKEND_TEST_GUIDE.md) | Zone C/D 통합 및 백엔드 연동 테스트 가이드 |
| [인프라_적용_가이드.md](guides/인프라_적용_가이드.md) | 인프라 적용 가이드 (한국어) |

## 보고서 (Reports)

| 문서 | 설명 |
|------|------|
| [PROJECT_SUMMARY.md](reports/PROJECT_SUMMARY.md) | 프로젝트 현황 종합 보고서 |
| [AGENT_IO_ANALYSIS.md](reports/AGENT_IO_ANALYSIS.md) | 에이전트 I/O 분석 보고서 |
| [OLLAMA_MODEL_TEST_REPORT.md](reports/OLLAMA_MODEL_TEST_REPORT.md) | Ollama 모델 테스트 결과 |
| [REFACTORING_LOG.md](reports/REFACTORING_LOG.md) | 리팩토링 이력 |
| [CODE_REVIEW_2026-03-06.md](reports/CODE_REVIEW_2026-03-06.md) | 코드 리뷰 (2026-03-06) |

## 변경 이력 (Changelog)

| 문서 | 설명 |
|------|------|
| [CHANGELOG_v24.md](changelog/CHANGELOG_v24.md) | v24 변경이력 |
| [CHANGELOG_v23.md](changelog/CHANGELOG_v23.md) | v23 변경이력 |
| [CHANGELOG_v22.md](changelog/CHANGELOG_v22.md) | v22 변경이력 |
| [CHANGELOG_v21.md](changelog/CHANGELOG_v21.md) | v21 변경이력 |
| [CHANGELOG_v20.md](changelog/CHANGELOG_v20.md) | v20 변경이력 |
| [CHANGELOG_v19.md](changelog/CHANGELOG_v19.md) | v19 변경이력 |
| [CHANGELOG_v18.md](changelog/CHANGELOG_v18.md) | v18 변경이력 |
| [CHANGELOG_v16-v17.md](changelog/CHANGELOG_v16-v17.md) | v16~v17 변경이력 |
| [CHANGELOG_v14-v15.md](changelog/CHANGELOG_v14-v15.md) | v14~v15 변경이력 |
| [CHANGELOG_v10-v13.md](changelog/CHANGELOG_v10-v13.md) | v10~v13 변경이력 |
| [CHANGELOG_v9.md](changelog/CHANGELOG_v9.md) | v9 변경이력 |
| [CHANGELOG_v8.md](changelog/CHANGELOG_v8.md) | v8 변경이력 |
| [CHANGELOG_v7.md](changelog/CHANGELOG_v7.md) | v7 변경이력 |
| [CHANGELOG_v6.md](changelog/CHANGELOG_v6.md) | v6 변경이력 |
| [CHANGELOG_v1-v5.md](changelog/CHANGELOG_v1-v5.md) | v1~v5 변경이력 |

---

## 외부 문서

> 아래 문서는 프로젝트 저장소 외부에서 별도 관리됩니다. 임의 수정 방지를 위해 분리되어 있습니다.

| 문서 | 설명 |
|------|------|
| `ProjectDocs/INDEX.md` | 마스터 인덱스 (20개 에이전트 전체) |
| `ProjectDocs/ARCHITECTURE_v4.0.md` | v4.0 아키텍처 확정 명세 |
| `ProjectDocs/ARCHITECTURE_REDESIGN_v4.0.md` | v4.0 재설계 과정 및 상세 |
| `ProjectDocs/AGENTS_INDEX.md` | 에이전트 통합 인덱스 v2.0 |
| `ProjectDocs/AGENT_MESSAGE_PROTOCOL_v2.0.md` | 통합 메시지 프로토콜 v2.0 |

상세 경로는 `CLAUDE.md` 참고 문서 섹션을 참조하세요.

---

*마지막 업데이트: 2026-03-13*

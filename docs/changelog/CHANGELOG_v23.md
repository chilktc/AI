# 변경이력 v23

> 날짜: 2026-03-13

---

## v23: Zone C/D 통합 + API 문서 통합 + 데이터 스키마 명세

### 배경

Zone C(관측성/미들웨어)와 Zone D(백엔드 연동) 통합 작업을 완료한다.
동시에 Notion "API 기능 명세서" DB(16개 페이지)를 SSOT로 확정하고,
분산된 API 문서 3개를 단일 명세서(API_SPEC.md v1.2)로 일원화한다.

**원칙**: Protected 파일(agent_state.py, message.py, contracts.py, workflow.py) 수정 없음.
Shared Infrastructure 기존 시그니처 변경 없음.

---

### Zone C: 관측성 인프라

#### 신규 파일

| 파일 | 내용 |
|------|------|
| `src/api/middleware.py` | RequestLoggingMiddleware — HTTP 요청 로깅 (X-Request-ID 추적, ALB/Prometheus 경로 제외, 구조화 JSON 로깅) |

#### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/api/main.py` | RequestLoggingMiddleware 등록, Prometheus 메트릭 라우터 추가, 시작/종료 로깅 강화 (STORAGE_MODE, LangGraph 컴파일 완료 등) |

---

### Zone D: 에이전트 직접 퍼블리싱

v22에서 구현한 `AgentDataPublisher`를 에이전트에 적용. 파이프라인 완료 전에 에이전트가 직접 백엔드에 데이터를 전달한다.

| 파일 | 변경 내용 |
|------|----------|
| `src/agents/podcast/emotion.py` | AgentDataPublisher import + 감정 벡터 직접 퍼블리시 (`RESOURCE_EMOTION_LOG`) |
| `src/agents/podcast/content_analyzer.py` | AgentDataPublisher import + 콘텐츠 분석 결과 직접 퍼블리시 (`RESOURCE_CONTENT_ANALYSIS`) |
| `src/agents/shared/learning.py` | 하드코딩 문자열 → `TYPE_LEARNING`, `RESOURCE_LEARNING` 상수 전환 |

---

### API 수정

| 파일 | 변경 내용 |
|------|----------|
| `src/api/routes/podcasts.py` | EmotionSummary 한영 번역 딕셔너리(`_EMOTION_EN_TO_KR`) 추가, SafetyAlertData 추출 로직 수정, 필드명 정렬 (`title`→`episode_title`, `total_duration_minutes`→`total_duration`) |
| `src/api/routes/health.py` | ReadyResponse에 `storage_mode` 필드 추가 (Zone D 백엔드 식별) |
| `src/api/backend_resources.py` | 리소스/타입 상수 전면 재구조화 — `RESOURCE_PODCAST_EPISODE`, `RESOURCE_CONTENT_ANALYSIS`, `RESOURCE_EMOTION_LOG`, `RESOURCE_VISUALIZATION` 확정, `TYPE_*` 상수 섹션 분리 |
| `src/api/contracts.py` | ErrorDetail/ErrorResponse를 DEPRECATED 표기 (→ external_schemas.py 신버전 사용) |
| `src/api/external_schemas.py` | 데이터 흐름 문서화 강화, EmotionSummary의 arousal/emotional_journey_hint가 API 미노출임을 명시 |
| `src/api/routes/sessions.py` | 세션 관련 마이너 수정 |

---

### 스키마 정렬

Content Analyzer 출력과 일치하도록 EmotionalJourney 필드명을 변경한다.

| 파일 | 변경 내용 |
|------|----------|
| `src/models/schemas.py` | EmotionalJourney 필드: `start_emotion`→`opening`, `peak_emotion`→`development`, `resolution_emotion`→`resolution` |
| `src/agents/podcast/script_personalizer.py` | EmotionalJourney 필드 참조를 새 이름으로 수정 |

---

### 프롬프트 재구조화

| 파일 | 변경 내용 |
|------|----------|
| `prompts/podcast/podcast_reasoning.yaml` | flat 구조 → nested `prompts`(got/tot/cot) 전환. **GoT(Graph of Thoughts) 시스템 프롬프트 신규 추가** — core_pattern, nodes, edges, insights 추출 |
| `prompts/podcast/content_analyzer.yaml` | 포맷 마이너 수정 |

---

### 인프라

| 파일 | 변경 내용 |
|------|----------|
| `.env.example` | Backend URL 포트 8000→8080 수정, AI 서버/Backend 서버 구분 주석 추가 |
| `Dockerfile` | CMD를 `python -m src.api.main` → `uvicorn` 직접 호출로 변경 |
| `docker-compose.yml` | healthcheck를 `curl` → `python urllib` 변경 (python:3.11-slim에 curl 미설치) |
| `config/loader.py` | Backend URL 기본값 포트 수정 |

---

### 테스트

#### 신규 파일

| 파일 | 내용 |
|------|------|
| `tests/api/test_middleware.py` | RequestLoggingMiddleware 단위 테스트 (X-Request-ID 생성/보존, 제외 경로 동작) |
| `tests/api/test_publisher.py` | AgentDataPublisher 단위 테스트 (12개 케이스 — 성공/실패 경로, mock 주입, SaveRequest 구성) |
| `tests/agents/podcast/test_content_analyzer_publisher.py` | 콘텐츠 분석기 퍼블리셔 통합 테스트 |
| `tests/agents/podcast/test_emotion_publisher.py` | 감정 에이전트 퍼블리셔 통합 테스트 |

#### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `tests/agents/podcast/test_script_personalizer.py` | EmotionalJourney 샘플 데이터를 새 필드명으로 수정 |
| `tests/agents/shared/test_prompt_loader.py` | 프롬프트 버전 관련 마이너 수정 |

---

### 문서

#### API 문서 통합 (API_SPEC.md v1.1 → v1.2)

| # | 작업 | 출처 |
|---|------|------|
| 1-1 | 감정 추이 조회 — `/api/v1/users/{user_id}/emotions` (PathVar)로 변경 + 응답 갱신 | Notion N5 |
| 1-2 | 에피소드 목록 — `/api/v1/users/{user_id}/podcasts/episodes`로 변경 + 응답 갱신 | Notion N6 |
| 1-3 | 에피소드 단건 — `/api/v1/users/{user_id}/podcasts/episodes/{episode_id}`로 변경 | Notion N7 |
| 1-4 | 카테고리 테이블 + API 목록의 History 엔드포인트 수정 | N5,N6,N7 |
| 1-5 | 공통 에러 응답 섹션을 Notion N2 기준으로 갱신 | Notion N2 |
| 1-6 | API_FLOW.md → "아키텍처 흐름" 섹션으로 통합 (Phase 0~3) | API_FLOW.md |
| 1-7 | BACKEND_API_CONTRACT.md → 발신 API 섹션에 통합 (Save/Load 상세) | BACKEND_API_CONTRACT.md |
| 1-8 | 사용자 프로필 API 섹션 추가 (`PATCH /api/v1/users/{user_id}/profile`) | Notion N10 |
| 1-9 | 스트리밍 이벤트 스키마 섹션 추가 (StreamEventType + StreamEvent) | Notion N10 |
| 1-10 | 버전 v1.1 → v1.2, 변경이력 추가 | — |

#### 문서 생성/삭제

| 조치 | 파일 |
|------|------|
| **신규** | `docs/architecture/DATA_SCHEMA.md` — MySQL 7테이블 + Pinecone 2인덱스 + Neo4j 5노드 + S3 구조 |
| **삭제** | `docs/architecture/API_FLOW.md` (API_SPEC.md에 통합) |
| **삭제** | `docs/architecture/BACKEND_API_CONTRACT.md` (API_SPEC.md에 통합) |
| **삭제** | `docs/architecture/API_INTEGRATION_PLAN.md` (구버전 분석 문서) |

#### 기타 문서

| 파일 | 변경 내용 |
|------|----------|
| `CLAUDE.md` | 서버 아키텍처 다이어그램 추가 (Frontend→Backend→AI Server), API 연동 원칙 문서화 강화 |
| `docs/architecture/PROJECT_STRUCTURE.md` | src/api/ 트리 갱신 (3→8파일+routes/), tests/api/ 트리 추가 |
| `docs/INDEX.md` | BACKEND_API_CONTRACT 제거, DATA_SCHEMA 추가, v23 항목 추가 |
| `docs/changelog/INDEX.md` | v23 항목 추가 |
| `docs/guides/ZONE_CD_INTEGRATION_AND_BACKEND_TEST_GUIDE.md` | Zone C/D 통합 및 백엔드 연동 테스트 가이드 (신규) |

---

### 전체 파일 변경 요약

| 구분 | 파일 수 |
|------|--------|
| 코드 수정 | 14개 |
| 코드 신규 | 2개 (`middleware.py`, `publisher.py`) |
| 테스트 수정 | 2개 |
| 테스트 신규 | 4개 |
| 문서 수정 | 7개 |
| 문서 신규 | 4개 (`DATA_SCHEMA.md`, `CHANGELOG_v22.md`, `CHANGELOG_v23.md`, `ZONE_CD_INTEGRATION_AND_BACKEND_TEST_GUIDE.md`) |
| 문서 삭제 | 4개 (`PIPELINE_STREAMING_GUIDE.md`, `API_FLOW.md`, `BACKEND_API_CONTRACT.md`, `API_INTEGRATION_PLAN.md`) |
| 프롬프트 수정 | 2개 |
| **합계** | **수정 25개 + 신규 10개 + 삭제 4개** |

---

*Production 코드 변경: 14개 | Protected 파일 수정: 없음 | Shared Infrastructure 시그니처 변경: 없음*

*마지막 업데이트: 2026-03-13*

# Mind-Log 프로젝트 미완료 항목 현황 (2026-04-06)

> **목적:** 추가 작업 진행 전, 프로젝트에 실제로 남아있는 미완료 항목을 현재 코드 기준으로 정리한다.
> 기존 계획서 9개 + 코드베이스 8개 영역 병렬 검증 결과 기반.
> **이미 해결된 항목은 전부 제외**했으며, 각 항목은 현재 develop(194116e)에서 미해결 상태임을 코드로 확인했다.

> **2026-04-13 업데이트 (Plan #25 — feature/validation-restructure-0413)**
> - ✅ **백엔드 API 형상 불일치 해결**: `ingest_podcast_episodes()` 6개 파라미터 → 3개 (`session_id`, `image_url`, `text`)로 수정. 감정 컬럼(`primary_emotion`, `secondary_emotions`) `_save_core_data()` 추가.
> - ✅ **`RESOURCE_MIND_FREQUENCIES` 경로 수정**: `"tickets/mind-frequencies"` → `"mind-frequencies"` (백엔드 실제 경로 확인).
> - ✅ **`ingest_mind_frequencies` 로깅 수정**: 성공 시 INFO 로그 추가, 실패 시 WARNING → ERROR 격상, 중복 try/except 제거.
> - ✅ **ContentAnalyzer user_summary 신규 저장 추가**: `BackendClient.ingest_user_summary()` 신규 메서드 + content_analyses/user_summaries MySQL 테이블 추가.
> - ✅ **mypy 에러**: 기존 63건 → 0건 수정 완료 (PR #52 이전 이미 해결).
> - ✅ **테스트**: 512 passed, 0 errors (live 테스트 제외).

---

## 1. 기존 계획서 잔여 현황

종합점검 계획서(04-01)의 15개 Task 중 **13개가 develop 브랜치에 반영 완료**.

| 계획서 Task | 내용 | 현재 상태 |
|------------|------|----------|
| Task 1~8, 10, 12 | 싱글톤, timeout, 프롬프트, 대화모드 잔재 등 | ✅ 모두 해결됨 |
| Task 9 (F-1) | deploy.yml echo→printf | ⚠️ 비밀값은 printf 완료. 비민감 2줄(103-104)만 echo 잔존 |
| Task 11 (I-2,3) | Dead code next_step | ⚠️ 코드 잔존하나 `NOTE(dead-code)` 주석 추가됨 |
| Task 13 (J-1~4) | 린팅 컴플라이언스 | ✅ Black/Ruff/isort 통과. ❌ **mypy 63에러 18파일** |
| Task 14 | CI 파이프라인 검증 | ❌ mypy 실패로 CI lint 단계 차단 |
| Task 15 (G-1,2) | Bedrock EC2 벤치마크 | ⚠️ 단건 결과(haiku) 존재. 체계적 벤치마크 미실행 |

기타 계획서: Neo4j(04-02) ✅ 머지 완료, SSM wait(03-31) ✅ 구현 완료.

---

## 2. 실제 미완료 항목

### A. Stub → 실제 에이전트 전환 (파이프라인 핵심 갭) ✅ 종결 (2026-04-15)

> **2026-04-15 종결**: PR #145/#146로 KnowledgeAgent 본체 완성, feature/validation-knowledge-activation (PR #<TBD>)로
> Stub 잔존 경로 정식 제거. EpisodeMemoryAgent는 이미 lazy import fallback으로 실제 에이전트 사용 중.
> 후속 운영 검증은 `2026-04-15-knowledge-agent-activation-and-verification.md` Phase 4 (AWS SSM + docker exec) 참조.

| 항목 | 현재 코드 | 갭 |
|------|----------|-----|
| ~~`podcast_reasoning_node()`~~ | `PodcastReasoningAgent()` — DI 미전달 시 실제 KnowledgeAgent/EpisodeMemoryAgent로 fallback | ✅ 해결 |
| ~~`EpisodeMemoryStub.search()`~~ | 실제 `EpisodeMemoryAgent.process()` 사용 (어댑터로 기존 인터페이스 호환) | ✅ 해결 |
| ~~`KnowledgeAgentStub.search()`~~ | 클래스 삭제됨 (`src/agents/shared/stubs.py`). 실제 `KnowledgeAgent.search()` 사용 | ✅ 해결 |
| ~~인터페이스 불일치~~ | `podcast_reasoning.py` 내부 어댑터로 흡수 (Line 520~536) | ✅ 해결 |
| ~~DB 클라이언트 미주입~~ | PR #145/#146에서 KnowledgeAgent 생성자 최적화, KT Cloud RAG Suite 경로 구현 | ✅ 해결 |

### B. script_personalizer 미구현 분기

| 위치 | 메서드 | 상태 |
|------|--------|------|
| line 364-367 | `_apply_attitude_adjustment()` empathetic | `pass` — 미구현 |
| line 368-370 | `_apply_attitude_adjustment()` rational | `pass` — 미구현 |
| line 412-415 | `_apply_accessibility_adjustments()` hearing_impairment | `pass` — 미구현 |
| line 210-244 | `_query_user_profile()` | `return None` — MySQL 쿼리 주석 처리. DB 연결 전까지 항상 기본 프로필 사용 |

> `deep_personalization` 설정 연동은 ✅ 완료됨 (settings.yaml → 생성자).
> visual_impairment TTS 마커는 ✅ 구현됨.

### C. 데이터 영속화 레이어

| 컴포넌트 | 상태 | 설명 |
|---------|------|------|
| `base_memory._save_to_store()` | stub (`return True`) | 부모 클래스 기본 구현. PR #85 머지(2026-04-08) 완료 → `_save_to_store()` 실제 구현 반영됨 |
| `episode_memory` 저장소 | `mock_db.json` (로컬 파일) | **Pinecone EC2 연결 완료**(2026-04-09). PR #85 머지 완료. → Plan #23 즉시 구현 가능 |
| `data/cache/` 디렉토리 | 미생성 | mock_db.json 경로의 디렉토리 자체가 없음 |
| DB 클라이언트 (Neo4j, Pinecone, MySQL, S3) | ✅ 실제 구현 | factory.py 통해 접근 가능 |
| API Proxy 클라이언트 | stub (12개 TODO) | 백엔드 엔드포인트 미확정 |

> **운영 모드 주의**: `settings.yaml`의 `storage.mode`가 `proxy`로 설정되어 있으나,
> proxy 클라이언트 엔드포인트가 미확정 상태. 로컬 테스트 시 `local` 모드 사용 필요.

### D. 백엔드 팀 협의 대기

| 항목 | 건수 | 참조 |
|------|------|------|
| API Proxy 엔드포인트 확정 | 12건 (`api_proxy.py`) | 벡터·그래프·RDB·S3 4개 프록시 클라이언트 |
| API 리소스 경로 확정 | 4건 (`backend_resources.py`) | sessions, vector_search, graph_query, storage |
| API Key 인증 방식 | 1건 | PROJECT_DECISIONS 결정사항 |
| S3 upload prefix | 1건 (`settings.yaml:161`) | `"vis"` prefix 확정 필요 |
| 토큰 예산 관리 | 1건 | 추후 구현 |
| Rate Limiting | 1건 | API Gateway 레벨 — 인프라팀 |
| 텍스트 필드 max_length | 1건 (`external_schemas.py:228`) | 입력 제한 값 미확정 |

### E. CI/CD · 린팅

| 항목 | 현재 상태 |
|------|----------|
| Black (포맷팅) | ✅ 121파일 전체 통과 |
| Ruff (린팅) | ✅ 전체 통과 |
| isort (import 정렬) | ✅ 전체 통과 |
| **mypy (타입 검사)** | ❌ **63에러 / 18파일** — CI lint 차단 |
| deploy.yml echo 잔존 | 비민감 값 2줄 (line 103-104). 기능상 문제 없음 |
| Dead code (next_step) | `NOTE(dead-code)` 주석 처리됨. 제거 가능하나 기능 영향 없음 |

> mypy 주요 에러: 반환 타입 미선언(8건), LangGraph StateGraph API 타입 불일치(4건),
> podcast 에이전트 타입 불일치(15건) 등.

### F. 테스트 스위트

| 항목 | 현재 상태 |
|------|----------|
| 테스트 수집 | 341건 수집 가능 |
| 통과 | 341 passed, 13 skipped |
| **Python 3.9 호환성** | ❌ `src/models/schemas.py`에서 `str \| None` 문법 사용 → 3.9에서 9개 파일 수집 실패 (23 테스트 차단) |
| 실패 테스트 | 5건 (llm_client 초기화, tracing, endpoint 설정 관련) |
| 런타임 에러 | 19건 (AttributeError, ImportError, 설정 불일치) |

> 프로젝트 요구사항은 Python 3.11+. 로컬 환경이 3.9인 경우 일부 테스트가 차단됨.
> CI(3.11/3.12 매트릭스)에서는 이 문제 발생하지 않음.

### G. 인프라 · 배포 (EC2 접근 필요)

| 항목 | 현재 상태 |
|------|----------|
| Bedrock 모델 벤치마크 | 단건(haiku) 결과만 존재. 10개 에이전트 체계적 벤치마크 미실행 |
| settings.yaml 최적 모델 반영 | 벤치마크 완료 후 진행 |
| pr-body.md Phase 10 수동 작업 | GitHub Secrets, EC2 ALB DNS, Neo4j 스키마 초기화 |
| Neo4j Backend 이관 | docker-compose에 이관 주석 존재. 시기 미정 |

### H. 장기 로드맵

| 항목 | 구현 수준 | 설명 |
|------|----------|------|
| ~~**대화모드 에이전트**~~ | ~~미착수~~ | ~~workflow에서 완전 제거됨~~ — **영구 제외 (2026-04-08)** |
| ~~**Telemetry 실시간 모니터링**~~ | ~~부분 구현~~ | ~~Prometheus/Grafana 대시보드 미연동~~ — **영구 제외 (2026-04-08)** |
| **WebSocket 실시간 스트리밍** | 부분 구현 | `StreamEvent` 스키마 정의 + SSE 스트리밍 엔드포인트(`/episodes/stream`) 구현 완료. WebSocket 전용 핸들러 미구현 |
| **A/B 테스트** | 프레임워크 완성 | `base_agent.py`에 세션 기반 변이 할당, ContextVar 격리 등 전체 코드 구현됨. `settings.yaml`에 `ab_tests` 설정 미등록 |
| **프로덕션 운영** | 미착수 | 실전 배포 + 사용자 피드백 루프 |

---

## 3. 수량 요약

| 구분 | 건수 |
|------|------|
| Stub→실제 에이전트 전환 | 1건 (인터페이스 어댑터 + DI 연결) |
| script_personalizer 미구현 분기 | 4건 (3개 pass + 1개 return None) |
| 데이터 영속화 갭 | 3건 (base_memory stub, mock_db, 디렉토리 미생성) |
| 백엔드 협의 대기 | 7건 (API 16개 TODO 포함) |
| CI/린팅 | 1건 (mypy 63에러) |
| 테스트 실패/에러 | 24건 (5 fail + 19 error) |
| 인프라·배포 | 4건 (Bedrock, 수동 설정, Neo4j 이관) |
| 장기 로드맵 | 3건 (WebSocket, A/B, 프로덕션) — 대화모드·Telemetry 영구 제외 |
| **합계** | **약 47건** (대화모드·Telemetry 2건 영구 제외 후) |

### 즉시 작업 가능 항목

| 항목 | 난이도 | 의존성 |
|------|--------|--------|
| mypy 63에러 수정 → CI 정상화 | 중간 | 없음 |
| Stub→실제 에이전트 DI 연결 | 중간 | 없음 (factory, 실제 에이전트 모두 구현됨) |
| script_personalizer pass 분기 구현 | 낮음~중간 | 없음 (empathetic/rational 규칙 정의 필요) |
| A/B 테스트 활성화 | 낮음 | settings.yaml에 ab_tests 설정 추가만 필요 |
| 테스트 실패 5건 수정 | 낮음 | 없음 |

---

*작성일: 2026-04-06 | 기준 브랜치: develop (194116e) | 검증 에이전트: 8개 병렬*

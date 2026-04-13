# 마스터 계획 인덱스 (Master Plan Index)

**목적**: 모든 기획 문서의 현황 추적 및 상태 관리  
**버전**: v33
**마지막 업데이트**: 2026-04-13
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
| 5 | 대화모드 잔재 제거 | `2026-03-31-conversation-removal.md` | ✅ 완료 | #45, #48, #49, #61 | 7개 Phase 완료 (파일 이동, 프롬프트/설정 삭제, API 스키마 수정, 테스트 수정) |
| 6 | 프로젝트 종합 점검 (품질) | `2026-03-31-project-quality-review.md` | ✅ 완료 | #48, #52, #58, #60, #61, #62 | 9개 Phase 전체 완료 (Phase 8-9 문서 정리 포함) |
| 7 | 잔여 테스트 현황 확인 | `2026-03-31-remaining-issues-investigation.md` | ✅ 완료 | #46, #48, #59 | D-2 SSM wait, C-2 프로바이더 분기, D-3 printf 모두 해결 |
| 8 | 종합 점검 (미완료/미해결) | `2026-04-01-comprehensive-review.md` | ✅ 완료 | #48, #49, #52, #58 | 코드 항목 전부 해결 (A-1~D-3, mypy, 3.9 호환). 잔여: 외부 의존성(E-2)/장기 로드맵(H-*) |
| 9 | Neo4j 배포 + 프론트엔드 그래프 | `2026-04-02-neo4j-deployment-frontend-graph.md` | ✅ 완료 | #50, #51 | GoT→Neo4j→Backend 완료 |
| 10 | AWS 환경변수 & 보안 | `2026-04-06-aws-env-remediation.md` | ✅ 완료 | #59 | STORAGE_MODE, BACKEND_API_URL 완료 |
| 11 | 종합 실행 계획서 (2026-04-06) | `2026-04-06-comprehensive-execution-plan.md` | ✅ 완료 | #52, #57 | Phase 1-2 완료 (mypy, 테스트 격리) |
| 12 | 미완료 항목 현황 (2026-04-06) | `2026-04-06-pending-items-inventory.md` | 🔶 대부분 완료 | #52 | mypy/테스트 해결. 잔여: ① podcast_reasoning Stub→실제 DI 미연결 ② personalizer empathetic/rational pass, _query_user_profile return None ③ data/cache/ 디렉토리 미생성 |
| 13 | 파이프라인 견고성 (아카이브) | `2026-04-06-pipeline-robustness-remediation.md` | 📁 아카이브 | — | v1-v4 이력 보존 |
| 14 | 파이프라인 견고성 강화 마스터 | `pipeline-robustness-index.md` | ✅ 완료 | #60 | 13개 취약점 수정 |
| 15 | 파이프라인 견고성 - Phase 1 | `pipeline-robustness-part1.md` | ✅ 완료 | #60 | Changes 1-9 완료 |
| 16 | 파이프라인 견고성 - Phase 2 | `pipeline-robustness-part2.md` | ✅ 완료 | #60 | get_fallback_output() 추가 |
| 17 | 독스트링 품질 개선 구현 | `2026-04-07-docs-quality-implementation.md` | ✅ 완료 | #61 (MERGED) | Phase 1-4 구현 + CB/SSE 테스트 추가 (538 passed, 14 skipped — PR #67/#68 Pinecone 테스트 59개 추가 후) |
| 18 | Neo4j 통합 구현 계획 | `_archive/plans/2026-04-07-neo4j-integration-plan.md` | ✅ 완료 | — | 작업 1(GoT→Neo4j E2E) ✅ 6 passed in 0.59s (AWS SSM 2026-04-09). 작업 2(Mode A) ✅ PR #88. 코드 전체 완료. 부수: seed.py 제약조건 에러 핸들링 개선 필요 |
| 19 | Pinecone 벡터 DB 공통 인프라 | `2026-04-07-pinecone-vector-db-integration.md` | 🔶 대부분 완료 | #64~#68 | Task 1/3/4 완료. KnowledgeAgent+PineconeClient 코드 완전 구현됨 (테스트 32개 통과). ⚠️ 미완: ① EmbeddingClient(KTCloud 어댑터) 미구현 → `knowledge._search_knowledge_base()` fallback 동작 중 ② `podcast_reasoning.py` KnowledgeAgentStub 사용 (DI 미연결) ③ Task 5/6/7(CLI), Task 9(가이드) 미작성 |
| 20 | Graph Mode B 단일화 리팩터 | `2026-04-07-graph-mode-b-refactor.md` | ✅ 완료 | #69 | Mode A 삭제, publish_graph_to_rdb 단일 경로 확정, EMA를 Backend 책임으로 이관 (538 passed) |
| 21 | 문서 전수 점검 및 정합성 수정 | *(인라인 — 별도 계획서 없음)* | ✅ 완료 | #70~#80 | 4차 사이클 점검: 대화모드 잔재·링크·날짜·버전 일관성·설계 결정 갱신 전체 완료 |
| 22 | 에이전트 출력 감사 수정 | `2026-04-08-agent-output-audit-fix.md` | ✅ 완료 | — | v9: IC-1/SP-1/SP-2/schemas 완료(8건) + Task 1-7 구현 완료(SA/EA/CA/SG/VI/BV/횡단). 556 passed |
| 23 | 에피소드 메모리 저장 트리거 | `_archive/plans/2026-04-08-episode-memory-save-trigger.md` | ✅ 완료 | #86, #87 | AgentState memory_write 필드 추가, Script Personalizer 반환, async_post 트리거 전부 develop에 머지 확인 (6b61763~ea06bd9) |
| 24 | Mode A 부활 — 누적 그래프 EMA | `_archive/plans/2026-04-09-mode-a-revival-graph-cumulative.md` | ✅ 완료 | #88 | contracts.py GraphCumulativeData, client.py GET/PUT 메서드, graph_cumulative.py Mode B→A 전환, 테스트 27개 (549 passed). BE 3차 테스트: session_id/timestamp 제거 후 PUT ✅ 200, Test 6~8 전체 PASS, E2E(GET→PUT→GET) 검증 완료 |
| 25 | Agent I/O 통합 및 재가공 에이전트 | `plans/2026-04-13-agent-io-consolidation.md` | 🔶 Task 8 완료 | #96 | Task 8: ingest_podcast_episodes() 정합 + podcast_segments 제거 + 감정 컬럼. Task 9: ingest_user_summary() 추가했으나 Plan #27(884c18c)에서 제거 — mind-frequencies로 통합 확정. ⛔ 보류: PodcastReprocessingAgent/EpisodeSummaryAgent(백엔드 테이블 미확보), AGENT_IO_DATAFLOW.md 추출 |
| 26 | 프로덕션 버그 3종 수정 | `_archive/plans/2026-04-13-production-bugfix.md` | ✅ 완료 | #93, #94, #95 | Task 1: ScriptPersonalizer .segments→.script_text (c8ad23c). Task 2: graph_cumulative 타임스탬프 +00:00 제거 (29f66bf). Task 3: 프롬프트 YAML 5개 force-add (acb8903) |
| 27 | Backend API 전수 테스트 | `plans/2026-04-13-backend-api-test.md` | 🔶 버그 수정 완료 | 884c18c, a1d3e2f | B-2(session_id 백엔드 수정·원복), B-3(title추가), B-4(graph_nodes /api/v1 경로), user_summaries 제거, graph/query 제거. CLI 재검증 대기. graph_nodes GET/PUT 2개만 백엔드 통신 대상 (Neo4j 내부 확정) |
| 28 | Git History 민감정보 제거 | `plans/2026-04-13-git-history-cleanup.md` | 🔲 합의 대기 | — | 3인 합의 후 실행. 제거 대상: KT Cloud 토큰/엔드포인트, ALB 도메인, 내부 IP 4종, DB 비밀번호 3종 (총 10종). git-filter-repo --force, remote add 재등록, 전원 re-clone 필요 |
| 29 | CI/CD 워크플로우 개선 | *(인라인 — 별도 계획서 없음)* | ✅ 완료 | 1e27eb4, e4af0f8 | ① pinecone_mock.py 복원 (fe99482 커밋에서 실수 삭제) + Black 포맷 12개 파일 수정 → CI 통과. ② build-and-push 속도 개선: arm64 제거(amd64 전용), registry 레이어 캐시 추가. ③ Neo4j/Pinecone 보호: `docker compose pull/up ai-server`만 실행 (`--no-deps`). ④ CI pip 캐시 추가, codecov token, docker-build GHA 캐시. ⑤ `aws ssm wait`에 `--region` 추가 |
| 30 | SaveResponse 스키마 유연화 (긴급 핫픽스) | `_archive/plans/2026-04-13-saveresponse-schema-hotfix.md` | ✅ 임시 완료 | d4626bc | AWS 환경 save API 응답 형식 변경(`{'success': true}`→`{'code': 'ok', 'message': '성공'}`) 대응. SaveResponse를 양쪽 형식 모두 수용하도록 유연화. 임시 해결책 완료, 백엔드 API 계약 확정 대기 중. |
| 31 | 로깅 시스템 강화 | `_archive/plans/2026-04-13-logging-enhancement.md` | ✅ 완료 | 0e115d5 (PR #101) | HTTP 이벤트 훅 추가(모든 요청/응답 자동 로깅), 에러 응답 상세 기록, DeveloperFormatter(다중행 가독성), JSON 포맷터 ISO 8601 타임스탬프. `src/api/client.py`, `src/utils/logger.py` |
| 32 | 테스트 정리 — live 테스트 분리 | *(인라인 — 별도 계획서 없음)* | ✅ 완료 | PR #105 (3b43bc4) | pyproject.toml addopts="-m 'not live'" 추가, test_safety/test_backend_integration 삭제, live fixture 분리, api_client→backend_client 시그니처 수정. 539 passed (live 제외 ~9초). |
| 33 | KT Cloud RAG 통합 — Knowledge Ingestion Pipeline | `docs/architecture/API_ENDPOINTS_INTERNAL.md` | ✅ 완료 | PR #106 (afc3a56) | jun 개발자. KT Cloud RAG Suite 연동, Knowledge Ingestion 스크립트(`scripts/ingest_knowledge.py`), 지식 청크 적재 파이프라인. `src/agents/podcast/knowledge.py` 확장. |
| 34 | Stories 데이터 수신 인프라 | `plans/2026-04-13-stories-receive-infra.md` | 🔲 구현 대기 | — | 백엔드 `POST /api/stories/select` 수신 엔드포인트 신규 생성. `load_stories()` 삭제(방향 반대), `personalization-context` 중복 제거. 활용 에이전트·AgentState 주입 시점은 미정 — 수신 인프라만 구현. |

**범례:**
- ✅ 완료 — 코드 구현 완료, PR 머지됨
- 🔶 대부분 완료 — 핵심 작업 완료, 소규모 잔여 항목 존재
- 🔲 구현 대기 — 계획서 작성 완료, 구현 명령 대기 중
- 📁 아카이브 — 참조용 (독립 구현 목표 없음)

---

## ✅ 완료된 항목

### 코드 정리 (PR #61)

| # | 작업 | 파일 | PR |
|---|------|------|-----|
| 1 | safety.py 독스트링 Google-style 통일 | `src/agents/podcast/safety.py` | `7c80efd` |
| 2 | batch_validator.py 독스트링 Google-style 통일 | `src/agents/podcast/batch_validator.py` | `228faf4` |
| 3 | external_schemas.py docstring 불일치 수정 | `src/api/external_schemas.py` | `c114a55` |
| 4 | src/agents/conversation/ 빈 디렉토리 제거 | `src/agents/conversation/` | #61 |

### 테스트 보완

| # | 작업 | 파일 | PR |
|---|------|------|-----|
| 5 | Circuit Breaker 상태 전환 테스트 9개 | `tests/agents/shared/test_llm_client.py` | `eaa6c28` |
| 6 | SSE `/episodes/stream` 엔드포인트 테스트 11개 | `tests/api/test_sse_streaming.py` | `eaa6c28` |

### 외부 의존성 — 해소됨

| # | 작업 | 비고 |
|---|------|------|
| 7 | Bedrock EC2 벤치마크 | 에이전트별 최적 모델 settings.yaml 반영 |
| 10 | Neo4j Backend 이관 | 이관 불필요 — AI 서버에서 직접 운영 확정 |

### 기능 구현 완료

| # | 작업 | 파일 | PR |
|---|------|------|-----|
| 17 | EpisodeMemoryStub → 실제 DI 연결 | `podcast_reasoning.py` | #86 |
| 18 | base_memory._save_to_store() 실구현 | `base_memory.py` | #85/#86 |
| 19 | episode_memory mock_db.json → Pinecone | `episode_memory.py` | #85 |
| 24 | knowledge.py 인덱스명 하드코딩 수정 | `knowledge.py` | #67 |

### 구현된 주요 기능 목록

| 기능 | 위치 | 완료 PR |
|------|------|--------|
| Circuit Breaker (구현체) | `src/agents/shared/llm_client.py:42` | 기존 구현 |
| SSE 스트리밍 엔드포인트 | `src/api/routes/podcasts.py:381` | PR #48 |
| 프롬프트 인젝션 방어 | `src/agents/shared/input_sanitizer.py` | PR #58 |
| PII 정제 | `src/agents/shared/output_sanitizer.py` | PR #58 |
| 타입 힌트 현대화 (Dict→dict) | 전체 에이전트 | PR #52 |
| TIER 0~4 타임아웃 래퍼 | `src/graph/workflow.py` | PR #48/#60 |
| mypy 63개 에러 수정 | 전체 | PR #52 |
| Python 3.9 호환성 | `schemas.py` 등 | PR #52 |
| 대화모드 제거 (기능) | 전체 | PR #45/#48/#49 |
| features 섹션 비활성화 | `config/settings.yaml:207` | 주석 처리됨 |
| AGENT_ROLES.md 모델명/이슈 갱신 | `docs/architecture/AGENT_ROLES.md` | PR #62 |
| 코드 품질 9개 Phase 전체 완료 | `QUALITY_REVIEW_CHECKLIST.md` v6 | PR #52~#62 |
| deploy.yml printf 전환 | `.github/workflows/deploy.yml` | PR #59 |
| Pinecone 클라이언트 + CLI 스크립트 3종 | `src/db/pinecone_client.py`, `dev/scripts/` | PR #64 |
| Pinecone 테스트 59개 (client, mock, factory, scripts) | `tests/db/test_pinecone_*.py`, `tests/db/test_factory_vector.py` | PR #67/#68 |
| Pinecone 인덱스명 하이픈 통일 | `config/settings.yaml`, `dev/scripts/`, `src/agents/podcast/knowledge.py` | PR #67/#68 |
| EpisodeMemoryAgent 실구현 (KT Cloud + Pinecone) | `src/agents/podcast/episode_memory.py` | PR #85 |
| AgentState memory_write 트리거 + Script Personalizer 반환 | `src/models/agent_state.py`, `script_personalizer.py` | PR #86 |
| async_post 에피소드 메모리 저장 호출 | `src/graph/workflow.py` | PR #86 |
| GoT→Neo4j E2E 검증 (6 passed, AWS SSM) | `dev/local_db/test_neo4j_integration.py` | PR #90 |
| GraphCumulativeData 스키마 + Mode A EMA 전환 | `src/api/contracts.py`, `src/api/graph_cumulative.py` | PR #88 |
| BackendClient load/put_graph_cumulative | `src/api/client.py` | PR #88 |
| graph_cumulative 테스트 27개 (549 passed) | `tests/api/test_graph_cumulative.py` | PR #88 |
| TestPublishGraphToBackend 삭제 + TestSaveGraphData 수정 | `tests/agents/podcast/test_podcast_reasoning.py` | PR #90 |

---

## ❌ 미완료 항목

### 외부 의존성 — 백엔드 팀 대기

| # | 작업 | 담당 | 비고 |
|---|------|------|------|
| 8 | TODO(backend) 21건 해소 | 백엔드 팀 | api_proxy.py 15건, backend_resources.py 5건, s3_client.py 1건 |
| 9 | API Key 인증 / max_length / Rate Limiting 협의 | 백엔드 팀 | comprehensive-review.md H-2,5,E-2 |

### 보안 수동 조치 (SECURITY_REMEDIATION_TRACKER.md)

| # | 작업 | 상태 |
|---|------|------|
| 11 | KT Cloud API 토큰 로테이션 | ❌ 미완료 |
| 12 | OpenAI API 키 로테이션 | ❌ 미완료 |
| 13 | LangSmith API 키 로테이션 | ❌ 미완료 |
| 14 | Grafana/OpenSearch 비밀번호 변경 | ❌ 미완료 |
| 15 | 로컬 DB 비밀번호 재설정 | ❌ 미완료 |
| 16 | Git history 정리 (KT Cloud 토큰 잔존) | 🔲 합의 대기 — Plan #28 참조 |

### 기능 미구현 (Plan #12/#19)

| # | 작업 | 파일 | 비고 |
|---|------|------|------|
| 20 | KTCloudEmbeddingClient 어댑터 + factory.py + KnowledgeAgent DI | `src/db/`, `podcast_reasoning.py` | episode_memory._embed() 추출 ~30줄 |
| 21 | test_knowledge.py 벡터 검색 테스트 추가 | `tests/agents/podcast/test_knowledge.py` | 현재 stub 테스트만 존재 |
| 22 | script_personalizer empathetic/rational 구현 | `script_personalizer.py:402,405` | 비즈니스 규칙 정의 선행 필요 |
| 23 | script_personalizer hearing_impairment 구현 | `script_personalizer.py:450` | 비즈니스 규칙 정의 선행 필요 |
| 24 | _query_user_profile() MySQL 구현 | `script_personalizer.py:275` | DB 연결 선행 필요 |
| 25 | data/cache/ 디렉토리 생성 | 프로젝트 루트 | episode_memory 런타임 의존 |

### CLI 스크립트 / 문서 — Plan #19 (개발자 도구, 운영 필수 아님)

| # | 작업 | 파일 |
|---|------|------|
| 26 | test_embedding.py CLI 스크립트 | `dev/scripts/test_embedding.py` |
| 27 | test_vector_roundtrip.py CLI 스크립트 | `dev/scripts/test_vector_roundtrip.py` |
| 28 | ingest_knowledge_base.py + 샘플 데이터 | `dev/scripts/ingest_knowledge_base.py` |
| 29 | PINECONE_DEVELOPER_GUIDE.md | `docs/guides/PINECONE_DEVELOPER_GUIDE.md` |

> ③ `test_pinecone_mock.py` import error — `dev/local_db/pinecone_mock.py` 복원 완료 (1e27eb4, 27 passed)

### 완료 — Plan #22 에이전트 출력 감사

| # | 작업 | 상태 |
|---|------|------|
| 30 | 에이전트 출력 스키마 수정 7건 (Plan #22 v9) | ✅ 완료 — Task 1~7 전체 구현 (556 passed) |

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
| #62 | feature/reasoning-code-quality-cleanup | 코드 품질 정리 — dead code 제거 + Phase 8-9 문서 (MERGED) |
| #64 | feature/reasoning-pinecone-infra | Pinecone CLI 스크립트 3종 + pinecone_client 구현 (MERGED) |
| #65 | feature/reasoning-code-quality-cleanup | deploy.yml PINECONE_API_KEY/NEO4J_USER 누락 추가 (MERGED) |
| #66 | feature/reasoning-code-quality-cleanup | requirements.txt pinecone-client → pinecone 패키지명 수정 (MERGED) |
| #67 | feature/reasoning-code-quality-cleanup | Pinecone 인덱스명 언더스코어→하이픈 (config, dev/scripts, tests) (MERGED) |
| #68 | feature/reasoning-code-quality-cleanup | knowledge.py 인덱스명 수정 + PLAN_INDEX v10 + Pinecone 완료 현황 (MERGED) |
| #70 | feature/reasoning-docs-stage1 | 대화모드 잔재 제거 + 해소된 이슈 RESOLVED 처리 (MERGED) |
| #71 | feature/reasoning-docs-stage2 | 버전/수치 동기화 + Neo4j PR 반영 (MERGED) |
| #72 | feature/reasoning-docs-stage3 | 코드 예시/경로/기타 정합성 수정 (MERGED) |
| #73 | feature/reasoning-docs-stage4 | 구식 문서 아카이브 + 미기재 기능 보충 (MERGED) |
| #74 | feature/reasoning-docs-stage5-high | Pinecone 인덱스명 통일 + 대화모드 잔재 + DEPRECATED 표기 (MERGED) |
| #75 | feature/reasoning-docs-stage6-medium | 테스트 수 갱신 + 날짜 + 대화모드 TODO 제거 + 에이전트 템플릿 교체 (MERGED) |
| #76 | feature/reasoning-docs-stage7-low | 클래스명 동기화 + Mode A 삭제 반영 + 링크 6개 수정 (MERGED) |
| #77 | feature/reasoning-docs-stage8-high | 대화모드 잔재 제거 + PROJECT_DECISIONS 로드맵 갱신 (MERGED) |
| #78 | feature/reasoning-docs-stage9-medium | 앵커 오류 + PLAN_INDEX PR/테스트수 + graph-design 이력 주석 (MERGED) |
| #79 | feature/reasoning-docs-stage10-low | 날짜 갱신 3건 + README CONTRIBUTING 설명 보완 (MERGED) |
| #80 | feature/reasoning-docs-stage11 | PR 버전 불일치 + 대화모드 잔재 + 설계 결정 #15~#18 추가 (MERGED) |
| #88 | feature/reasoning-plan-sync-0409 | Plan #24 Mode A 부활: contracts/settings/resources/client/graph_cumulative + 테스트 27개 (549 passed) (MERGED) |
| #89 | feature/reasoning-plan-sync-0409 | black 포맷 수정 backend_resources.py — CI lint 통과 (MERGED) |
| #90 | feature/reasoning-lint-fix-0409 | TestPublishGraphToBackend 삭제 + TestSaveGraphData publish_graph_to_rdb 패치 수정 + PLAN_INDEX v18 (MERGED) |

---

*마스터 인덱스 v33 — 2026-04-13 (Plan #22 Task 1-7 구현 완료. SA/EA/CA/SG/VI/BV 출력 명시화 + 횡단 이슈 수정)*

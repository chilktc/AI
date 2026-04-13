# 최종 구현 로드맵

**목적**: 실제 미완료 작업만 포함한 최종 구현 계획  
**버전**: v8  
**마지막 업데이트**: 2026-04-14 11:00

> ⚠️ **이 문서는 v8 (2026-04-08) 기준 스냅샷입니다.**  
> v8 이후 변경사항(Plan #22/31/32/33/34 포함)은 `docs/superpowers/PLAN_INDEX.md` (현재 v33, 2026-04-13)를 참조하세요.

> **v2 → v3 변경 이유:**  
> 4-에이전트 2차 병렬 점검 결과,  
> - Phase 1 (깨진 링크): docs/INDEX.md 링크 모두 정상 확인 → 제거  
> - Phase 2 (주석 보완): 대상 5개 파일 모두 주석 이미 존재 확인 → 제거  
> - Phase 3 (독스트링): 11개 에이전트 중 실제 미완료는 2개(safety.py, batch_validator.py)만  
> - 경로 오류 수정: `src/utils/callbacks.py` → `src/monitoring/callbacks.py`  
> - 신규 발견 항목 추가: external_schemas.py, 빈 디렉토리, 보안 트래커

---

## v1/v2에서 제거된 항목 (이미 완료 또는 불필요)

| v2 항목 | 실제 상태 | 근거 |
|---------|-----------|------|
| Phase 1: 깨진 링크 수정 | ✅ 불필요 | docs/INDEX.md 내 링크 전수 확인, 모두 정상 |
| Phase 2: 주석 보완 (5개 파일) | ✅ 이미 존재 | base_agent.py:192, llm_client.py:389, workflow.py:211, callbacks.py:52, script_generator.py:22 주석 확인 |
| Phase 3: 독스트링 11개 에이전트 전체 | 🔶 2개만 미완료 | safety.py + batch_validator.py만 실제 미완료 |

---

## 완료된 작업 (v4 — PR #61)

### ✅ 작업 1: 독스트링 보강 — 소규모 2개 파일

| 항목 | 파일 | 완료 |
|------|------|------|
| process() 독스트링 | `src/agents/podcast/safety.py` | ✅ Google-style Args/Returns/Raises 추가 |
| process() 독스트링 | `src/agents/podcast/batch_validator.py` | ✅ Google-style 통일, next_step 오류 수정, iteration_count 추가 |

### ✅ 작업 2: docstring 내용 오류 수정

| 항목 | 파일 | 완료 |
|------|------|------|
| 엔드포인트 경로 오류 | `src/api/external_schemas.py` | ✅ GET conversations → POST podcasts/episodes, WS 줄 제거 |

### ✅ 작업 3: 빈 디렉토리 제거

| 항목 | 경로 | 완료 |
|------|------|------|
| 빈 껍데기 디렉토리 | `src/agents/conversation/` | ✅ __pycache__만 있던 디렉토리 삭제 (Git 미추적) |

---

### 작업 4: Bedrock EC2 벤치마크 (우선순위: 🟢 낮음, 인프라 별도)

**출처**: Plan#2 Task 6 = Plan#5 Step 2

| 항목 | 내용 |
|------|------|
| 목표 | 6종 Bedrock 모델 성능 비교 |
| 방법 | EC2에서 Phase 0-3 실행 (`run_bedrock_model_test.py`) |
| 코드 변경 | **없음** (실행만 필요) |
| 산출물 | 성능 비교 리포트, settings.yaml 최적 모델 재확인 |
| 의존성 | EC2 인스턴스 접근 권한 필요 |

**이 작업은 코드 PR 없이 인프라팀 협력으로 진행.**

---

## 선택적 작업 (별도 PR 검토)

### ✅ 작업 5: Circuit Breaker 상태 전환 테스트

**출처**: PLAN_INDEX.md 그룹 2

| 항목 | 파일 | 완료 |
|------|------|------|
| CLOSED→OPEN (fail_max 초과) | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN→CircuitOpenError | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN→HALF_OPEN (timeout 경과) | `tests/agents/shared/test_llm_client.py` | ✅ |
| HALF_OPEN→CLOSED (1회 성공) | `tests/agents/shared/test_llm_client.py` | ✅ |
| HALF_OPEN→OPEN (1회 실패) | `tests/agents/shared/test_llm_client.py` | ✅ |
| success failure_count 리셋 | `tests/agents/shared/test_llm_client.py` | ✅ |
| CLOSED check() 통과 | `tests/agents/shared/test_llm_client.py` | ✅ |
| OPEN timeout 미경과 유지 | `tests/agents/shared/test_llm_client.py` | ✅ |
| 초기 상태 CLOSED 확인 | `tests/agents/shared/test_llm_client.py` | ✅ |

**총 9개 테스트 추가**

---

### ✅ 작업 6: SSE 엔드포인트 테스트

**출처**: PLAN_INDEX.md 그룹 2

| 항목 | 파일 | 완료 |
|------|------|------|
| Content-Type 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| Cache 헤더 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| connected 첫 이벤트 | `tests/api/test_sse_streaming.py` | ✅ |
| done 마지막 이벤트 | `tests/api/test_sse_streaming.py` | ✅ |
| custom tier 이벤트 전달 | `tests/api/test_sse_streaming.py` | ✅ |
| result 이벤트 데이터 | `tests/api/test_sse_streaming.py` | ✅ |
| timestamp 포함 확인 | `tests/api/test_sse_streaming.py` | ✅ |
| 전체 이벤트 순서 검증 | `tests/api/test_sse_streaming.py` | ✅ |
| 파이프라인 에러 핸들링 | `tests/api/test_sse_streaming.py` | ✅ |
| compiled_graph=None 에러 | `tests/api/test_sse_streaming.py` | ✅ |
| 잘못된 요청 422 반환 | `tests/api/test_sse_streaming.py` | ✅ |

**총 11개 테스트 추가**

---

## 구현 이력 (PR #61 브랜치: feature/reasoning-docs-quality)

### ✅ Phase 1: docstring 내용 오류 수정 — `c114a55`

- [x] `src/api/external_schemas.py:684-685` — GET conversations → POST podcasts/episodes, WS 줄 제거

### ✅ Phase 2: 독스트링 보강 — `7c80efd`, `228faf4`

- [x] `safety.py:process()` — Google-style Args/Returns/Raises 추가
- [x] `batch_validator.py:process()` — 커스텀 형식 → Google-style 통일, next_step 오류 수정

### ✅ Phase 3: 빈 디렉토리 제거

- [x] `src/agents/conversation/` — __pycache__만 있던 디렉토리 삭제 (Git 미추적)

### ✅ Phase 4: 테스트 보완 — `eaa6c28`

- [x] Circuit Breaker 상태 전환 테스트 9개 (`tests/agents/shared/test_llm_client.py`)
- [x] SSE `/episodes/stream` 엔드포인트 테스트 11개 (`tests/api/test_sse_streaming.py`)

---

## 완료된 작업 (v6 — PR #62 브랜치: feature/reasoning-code-quality-cleanup)

### ✅ 작업 7: 코드 품질 Phase 5 — dead code 제거

- [x] `config/settings.yaml` — features 주석 블록 삭제, databases 섹션 삭제
- [x] `config/loader.py` — 미사용 `databases_config` 프로퍼티 삭제
- [x] `src/api/routes/podcasts.py` — `visual_data_raw` 중복 선언 통합

### ✅ 작업 8: 코드 품질 Phase 8 — 문서 통일성

- [x] `docs/architecture/AGENT_ROLES.md` — 모델명 12개 settings.yaml 기준 갱신, C-1/B-5/C-4/C-5 RESOLVED
- [x] `docs/getting-started/QUICK_START.md` — ProjectDocs/ 직접 참조 제거, INFRA→AGENT_ROLES로 필수 문서 변경
- [x] `README.md` — 프로젝트 구조 보완 (monitoring/, prompts/ 추가, 문서 링크 보강)

### ✅ 작업 9: 코드 품질 Phase 9 — 문서 정리

- [x] 계획서 점검: PLAN_INDEX/ROADMAP/PLAN_PRIORITY_REVISED 각각 목적 상이 → 병합 불필요
- [x] INFRA_*.md 3개 이미 아카이브 표시 확인
- [x] QUALITY_REVIEW_CHECKLIST v6: 전체 9개 Phase 완료 반영

### 최종 검증 (PR #62)

```
479 passed, 14 skipped (2 pre-existing failures in test_retry_loop.py)
```

---

## 완료된 작업 (v7 — PR #64~#68 브랜치: feature/reasoning-code-quality-cleanup)

### ✅ 작업 10: Pinecone 공통 인프라 구축 (PR #64)

- [x] `dev/scripts/validate_pinecone_env.py` — 환경변수 검증 스크립트
- [x] `dev/scripts/create_pinecone_indexes.py` — 인덱스 생성 스크립트 (expert-knowledge, mem-podcast-episode)
- [x] `dev/scripts/test_pinecone_connection.py` — 연결 헬스체크 3단계
- [x] `src/db/pinecone_client.py` — PineconeClient (BaseVectorClient 구현, asyncio.to_thread 래핑)
- [x] `dev/local_db/pinecone_mock.py` — 인메모리 Mock (코사인 유사도, $eq/$in/$ne 필터)

### ✅ 작업 11: Pinecone 인프라 보강 (PR #65~#68)

- [x] `deploy.yml` — EC2 .env에 PINECONE_API_KEY, NEO4J_USER 누락 추가 (PR #65)
- [x] `requirements.txt` — pinecone-client → pinecone 패키지명 수정 (PR #66)
- [x] 인덱스명 언더스코어 → 하이픈 통일 (config, dev/scripts, tests, knowledge.py) (PR #67/#68)

### ✅ 작업 12: Pinecone 테스트 59개 작성 (PR #67/#68)

| 파일 | 테스트 수 | 대상 |
|------|----------|------|
| `tests/db/test_pinecone_client.py` | 13 | PineconeClient: 초기화, 캐싱, query, upsert, close, 인터페이스 |
| `tests/db/test_pinecone_mock.py` | 27 | _cosine_similarity(7), _match_filter(10), MockClient 엣지케이스(10) |
| `tests/db/test_factory_vector.py` | 4 | create_vector_client: local/hybrid/proxy 모드별 반환 타입 |
| `tests/db/test_pinecone_scripts.py` | 15 | validate_env(5), connection helpers(7), index config(2), missing key(1) |

### 최종 검증 (PR #68)

```
538 passed, 14 skipped (2 pre-existing failures in test_retry_loop.py)
```

---

## 대기 중인 작업

### ✅ 작업 14: 문서 전수 점검 및 정합성 수정 (Plan #21) — PR #70~#80

- [x] 1차 점검 (Stage 1~4, PR #70~#73): 대화모드 잔재, 링크 경로, 버전/수치 동기화, 구식 아카이브
- [x] 2차/3차 점검 (Stage 5~8, PR #74~#77): Pinecone 인덱스명, 대화모드 TODO, 에이전트 템플릿, 클래스명, PROJECT_DECISIONS
- [x] 4차 점검 (Stage 9~11, PR #78~#80): 앵커 오류, graph-design 이력 주석, 설계 결정 #15~#18 추가
- [x] 11개 Stage 전체 완료, 전체 21개 계획서 상태 최신화

---

### ✅ 작업 13: Graph Mode B 단일화 리팩터 (Plan #20) — `8c31fc6`

계획서: `plans/2026-04-07-graph-mode-b-refactor.md`

- [x] `src/api/graph_cumulative.py` — Mode A 7함수→1함수 (`publish_graph_to_rdb`)
- [x] `tests/api/test_graph_cumulative.py` — 29개→6개 테스트 (group 검증, 에러 핸들링)
- [x] `config/loader.py` — `graph_upsert_mode`, `graph_ema_alpha` 프로퍼티 삭제
- [x] `config/settings.yaml` — `graph:` 블록 삭제
- [x] `src/api/backend_resources.py` — `RESOURCE_GRAPH_NODES` 삭제
- [x] `docs/architecture/NEO4J_INTEGRATION.md` — Mode A 내용 제거, 단일 흐름 기술

### 🔲 Neo4j 잔여 작업 (Plan #18 미완료)

| 항목 | 내용 | 의존성 |
|------|------|--------|
| E2E 검증 | Neo4j 프로덕션 환경 E2E 테스트 | 인프라팀 Neo4j 인스턴스 배포 |

### 🔲 Pinecone 잔여 작업 (Plan #19 미완료)

| 항목 | 내용 | 의존성 |
|------|------|--------|
| BedrockEmbeddingClient | Amazon Titan Embeddings v2 클라이언트 구현 | boto3, Bedrock 접근 권한 |
| create_embedding_client() | 팩토리 함수에 임베딩 클라이언트 통합 | BedrockEmbeddingClient |
| 개발자 가이드 문서 | Pinecone 인프라 사용법 문서 작성 | 전체 구현 완료 후 |

---

## 외부 의존성 / 수동 작업 (코드 PR 없음)

### 보안 수동 조치 (SECURITY_REMEDIATION_TRACKER.md)

| # | 작업 | 상태 |
|---|------|------|
| 1 | KT Cloud API 토큰 로테이션 | ❌ 미완료 |
| 2 | OpenAI API 키 로테이션 | N/A — 배포 환경(Bedrock) 불필요, 로컬 개발 전용 |
| 3 | LangSmith API 키 로테이션 | ❌ 미완료 |
| 4 | Grafana/OpenSearch 비밀번호 변경 | ❌ 미완료 |
| 5 | 로컬 DB 비밀번호 재설정 | ❌ 미완료 |
| 6 | Git history 정리 (KT Cloud 토큰 잔존) | ❌ 미완료 — 3인 합의 필요 |

### Stub 에이전트 (Pinecone 연동 후 처리)

| 파일 | 라인 | 내용 | 의존성 |
|------|------|------|--------|
| `src/agents/podcast/podcast_reasoning.py` | 58-59 | `EpisodeMemoryStub()`, `KnowledgeAgentStub()` | Pinecone 연동 |
| `src/agents/podcast/base_memory.py` | 88-89 | `_save_to_store()` stub | KT Cloud API |
| `src/agents/podcast/episode_memory.py` | 15 | `mock_db.json` → Pinecone 전환 | Pinecone 연동 |

### Bedrock EC2 벤치마크

인프라팀 협력 필요:
1. EC2 인스턴스에서 `python -m dev.live_tests.run_bedrock_model_test` 실행
2. 6종 모델 비교 결과 리포트 저장 (`dev/live_tests/results/bedrock_phase3_*.json`)
3. 결과 바탕으로 `config/settings.yaml` 모델 최적값 재확인

---

*구현 로드맵 v8 — 2026-04-08*  
*v1~v3: 기획/점검 → v4: 작업 1-3 (PR #61) → v5: 작업 5-6 테스트 (PR #61) → v6: 작업 7-9 코드 품질 (PR #62) → v7: 작업 10-12 Pinecone 인프라+테스트 59개 (PR #64~#68) → v8: 문서 전수 점검 + Graph Mode B 단일화 (PR #70~#80)*  
*v8 이후 이력: docs/superpowers/PLAN_INDEX.md 참조*

# Neo4j 통합 구현 계획서

**버전**: v3
**작성일**: 2026-04-07 14:00 (v3 갱신: 2026-04-09)
**기준 문서**: `docs/architecture/NEO4J_INTEGRATION.md` v1.3
**작성 브랜치**: `feature/reasoning-docs-quality` (계획서 커밋용)
**구현 브랜치**: `feature/validation-*` (개발자3), `feature/reasoning-*` (개발자2 — Mode A)

---

## v1 → v2 변경 이유

2차 다수 서브에이전트 점검으로 오류 발견 후 반영:
- NEO4J_INTEGRATION.md 5-2의 "Emotion/Topic 초기 데이터 없음" → 실제로 seed_data.json에 존재 (오류 수정)
- seed_data.json GoTNode 3개 group 필드 누락 → **즉시 수정 완료** (이번 세션에서 처리)
- NEO4J_INTEGRATION.md v1.3으로 갱신 (5-2 수정, GoTNode group 수정 완료 반영)
- 작업 1을 "완료"로 재분류, 작업 번호 재정렬

---

## 개요

Neo4j 통합 명세서(`NEO4J_INTEGRATION.md` v1.3)를 기반으로 다수의 서브에이전트 검증을 통해 확인된  
**실제 미완료 작업**만을 정리한 구현 계획서이다.

AI팀의 코드 및 시드 데이터 구현은 완료 상태이며, 남은 것은  
인프라 배포 후 실행할 E2E 검증 2건과 Backend팀 협업 항목이 핵심이다.

---

## 현황 요약 — 이미 완료된 것

| 구분 | 항목 | 검증 방법 |
|------|------|----------|
| 모델 설정 | `config/settings.yaml` — podcast_reasoning: sonnet_37, max_tokens: 6000 | 파일 직접 확인 |
| 프롬프트 | `prompts/podcast/podcast_reasoning.yaml` — v3.1.0 존재 (group 6개 카테고리 포함) | 커밋 `986e06d` |
| DB 접속 | `src/db/neo4j_client.py`, `base.py`, `factory.py` | 코드 확인 |
| GoT 저장 | `podcast_reasoning.py` — `_save_got_to_neo4j()`, `publish_graph_to_rdb()` 호출 | 코드 확인 |
| 누적 계산 | `src/api/graph_cumulative.py` — EMA Mode A (Mode B 제거됨, PR #69/#88) | 코드 확인 |
| 그래프 변환 | `src/api/graph_transformer.py` — `validate_group()` | 코드 확인 |
| DDL | `dev/local_db/neo4j/init.cypher` — 제약 5개 + 인덱스 7개 | 파일 확인 |
| 시드 스크립트 | `dev/local_db/seed.py` — Neo4j MERGE 로직 완성 | 코드 확인 |
| 시드 데이터 | `seed_data.json` — User(2), Session(2), Emotion(4), Topic(3), GoTNode(3, group 포함) | 파일 직접 확인 + v2 수정 |
| 통합 테스트 | `dev/local_db/test_neo4j_integration.py` | 파일 확인 |
| 로컬 Docker | `dev/local_db/docker-compose.db.yml` | 파일 확인 |

> **v2 수정**: `NEO4J_INTEGRATION.md` v1.2의 5-2에 "Emotion/Topic 초기 데이터 없음"으로 표기되어 있었으나,  
> 실제로는 `seed_data.json`에 이미 포함되어 있음을 2차 검증에서 확인.  
> GoTNode 3개의 `group` 필드 누락(DDL 인덱스와 불일치)은 이번 세션에서 즉시 수정 완료.  
> `NEO4J_INTEGRATION.md` v1.3에 반영 완료.

---

## 실제 미완료 작업 (AI팀 코드)

> **v1 작업 1 (GoTNode group 필드 추가)은 이 세션에서 완료됨** — 아래 구현 순서에서 제외.

### 작업 1: ✅ 완료 — GoT → Neo4j E2E 저장 검증

> **2026-04-09 완료**: AWS SSM (t7-mindlog-prod-app-2) 에서 E2E 테스트 실행.
> - Neo4j v5.26.24 (community), `bolt://localhost:7687`, 네이티브 실행 확인
> - 시드 데이터 적재: User(2), Session(2), Emotion(4), Topic(3), GoTNode(3), Relationships OK
> - `pytest dev/local_db/test_neo4j_integration.py -v` → **6 passed in 0.59s**
> - 검증 항목: Topic 조회, GoT 1~3 hop 탐색, Session→GoTNode 체인, Session→Topic COVERS, Emotion OFTEN_COOCCURS, GoTNode CREATE→READ→DELETE 라이프사이클
> - 부수 발견: `seed.py`의 init.cypher 실행이 기존 제약조건 충돌로 실패 → 노드 데이터 미적재. 임시 스크립트로 우회하여 MERGE 성공. seed.py 에러 핸들링 개선 필요.

**브랜치**: `feature/validation-*` (개발자3)
**선행 조건**: ~~Phase 2 인프라 완료~~ → ✅ Neo4j 배포 완료 (bolt://localhost:7687)

| 검증 항목 | 결과 |
|---------|------|
| Neo4j 연결 확인 | ✅ v5.26.24, 포트 7687 LISTEN |
| 시드 데이터 적재 | ✅ 5개 노드 타입 + 관계 MERGE 완료 |
| GoT 저장 E2E | ✅ `pytest dev/local_db/test_neo4j_integration.py -v` → 6 passed in 0.59s |

**성공 기준**: ✅ GoTNode MERGE + LEADS_TO 관계 생성 확인

---

### 작업 2: ✅ 완료 — RDB 누적 저장 Mode A

> **2026-04-09 완료**: BE 3차 테스트 (Test 6~8) 전체 PASS + E2E(GET→PUT→GET) 검증 완료.
> - Test 6: GET (신규 유저) → ✅ 200, 빈 nodes/links 반환
> - Test 7: GET (기존 유저) → ✅ 200, `data.data` 중첩 구조 + 전체 필드 일치
> - Test 8: PUT → ✅ 200, `session_id`/`timestamp` 제거 후 성공
> - **BE PUT 거부 필드**: root `session_id`, `timestamp` → `GRAPH_REQUEST_SCHEMA_MISMATCH`
> - **BE PUT 필수 필드**: `nodes[].first_seen/last_seen`, `links[].source_grp/target_grp/first_seen/last_seen`
> - Mode A AI 서버 코드 전환: **Plan #24** (PR #88) 구현 완료, 테스트 27개 추가 (549 passed)

**브랜치**: `feature/reasoning-*` (개발자2) — PR #88 MERGED
**선행 조건**: ~~Phase 3-B Backend API 완료~~ → ✅ 완료 (2026-04-08 테스트 확인)

| 검증 항목 | 결과 |
|---------|------|
| EMA 단위 테스트 | ✅ `pytest tests/api/test_graph_cumulative.py -v` PASS |
| client.py GET/PUT 테스트 | ✅ 27개 테스트 추가 (549 passed) |
| AWS SSM E2E 테스트 | ✅ GET→PUT→GET 신규유저 플로우 PASS |

**성공 기준**: ✅ Mode A 흐름 — Backend GET → AI EMA 계산 → Backend PUT 성공

---

## 외부 의존성 — 인프라팀 작업 (코드 PR 없음)

> AI팀은 이 작업들을 대신 수행할 수 없다.

### Phase 2 인프라 체크리스트

| 순서 | 작업 | 비고 |
|------|------|------|
| 2-1 | EC2 메모리 결정 | `t3.medium`(4GB) OOM 위험 → `t3.large`(8GB) 업그레이드 권고 |
| 2-2 | Neo4j 5 Community 인스턴스 배포 | Docker 또는 네이티브 |
| 2-3 | 인증 비밀번호 설정 + 포트 7687 ACL | AI서버에서만 접근 허용 |
| 2-4 | 환경변수 등록 | `NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD` |
| 2-5 | `dev/local_db/neo4j/init.cypher` 실행 | 제약 5개 + 인덱스 7개 생성 |
| 2-6 | `docker-compose.yml` Neo4j 서비스 주석 해제 | `depends_on` 활성화 포함 |

**완료 기준**: `bolt://<host>:7687` 연결 성공 + Cypher 쿼리 실행 확인

---

## 외부 의존성 — Backend팀 작업 (코드 PR 없음)

> 상세 DDL 및 쿼리는 `docs/architecture/NEO4J_INTEGRATION.md` 섹션 6-4 참고.

### Phase 3-B Backend팀 체크리스트

| 순서 | 작업 | 엔드포인트/파일 | 우선순위 |
|------|------|--------------|--------|
| 3-B-1 | MySQL DDL 생성 | `user_graph_nodes`, `user_graph_edges` 테이블 | ①필수 |
| 3-B-2 | 기존 누적 데이터 조회 API | `GET /api/graph_nodes?user_id=X` | ①필수 |
| 3-B-3 | 갱신된 누적 데이터 저장 API | `PUT /api/graph_nodes` | ①필수 |
| ~~3-B-4~~ | ~~GoT 분석 결과 저장 API~~ | ~~`POST /api/graph_analyses`~~ | ❌ 불필요 — PUT /graph_nodes의 nodes/links가 category_distribution + keyword_connections 데이터를 이미 포함. `_publish_graph_to_backend()` 제거됨 (2026-04-09) |
| 3-B-5 | 프론트엔드용 누적 그래프 조회 API | `GET /api/graph/users/{id}/data` | ③연동 시 |

**Mode A 기준** (AI서버가 EMA 계산 후 전송): `PUT /api/graph_nodes`는 단순 UPSERT만 수행.  
UPSERT 쿼리 및 요청 body 스키마: `NEO4J_INTEGRATION.md` 섹션 6-4 참고.

---

## 차후 작업 (의존성으로 인해 보류)

| 항목 | 의존성 | 담당 |
|------|--------|------|
| Knowledge Agent Stub → 실제 Neo4j 쿼리 구현 | Pinecone 연동 완료 후 | 개발자3 |
| MySQL ↔ Neo4j 동기화 로직 | Backend팀 협의 | 개발자3 + Backend팀 |
| `src/api/routes/graph.py` 라우터 삭제 | Backend팀 그래프 조회 API 완료 후 | 개발자3 |

---

## 구현 순서 (Phase별)

```
Phase 1 ─── 의사결정 (전체 팀, ~1일)
    의제: Neo4j 배포 위치 결정, 인스턴스 메모리 결정, RDB 스키마 합의

Phase 2 ─── 인프라 준비 (인프라팀, ~2일)
    선행: Phase 1 완료
    작업: Neo4j 배포, DDL 실행, 환경변수 등록

Phase 3 ─── 병렬 구현
    3-A: 개발자3 — 작업 1 E2E 검증 (Phase 2 선행 필요)
    3-B: Backend팀 — DDL + API 4개 구현 (3-A와 병렬 진행 가능)
    선행: Phase 2 완료 (작업 1), Phase 3-B 완료 (작업 2)

Phase 4 ─── 통합 검증 (전체 팀, ~2일)
    pytest tests/api/ -v
    GoT 저장 → Neo4j 조회 → EMA 계산 → Backend PUT 흐름 검증

Phase 5 ─── 프로덕션 배포 (인프라팀 주도)
```

---

## 전체 테스트 기준

**[완료됨] seed_data.json group 필드 수정 후**:
```
python -m dev.local_db.seed --neo4j  # 오류 없이 완료
```

**작업 1, 2 완료 후** (인프라 + Backend 준비 필요):
```
pytest dev/local_db/test_neo4j_integration.py -v
pytest tests/api/test_graph_cumulative.py -v
pytest tests/api/test_graph_routes.py -v
```

---

## PR 양식 (seed_data group 필드 수정용 — 이번 세션에서 처리됨)

> 이 변경사항은 `feature/reasoning-docs-quality` 브랜치에서 문서 수정과 함께 커밋됨.

**PR 제목:**
```
fix: seed_data.json GoTNode group 필드 추가 + NEO4J_INTEGRATION.md 오류 수정
```

**Base**: `develop` | **Compare**: `feature/reasoning-docs-quality`

**PR Body 요약:**
```markdown
## 개요

2차 다수 서브에이전트 점검에서 발견된 2가지 오류 수정:

1. seed_data.json GoTNode 3개에 group 필드 누락 (DDL got_group 인덱스와 불일치)
2. NEO4J_INTEGRATION.md 5-2의 "Emotion/Topic 초기 데이터 없음" 오류 (실제로는 존재)

## 변경 내역

| 파일 | 변경 내용 |
|------|----------|
| `dev/local_db/fixtures/seed_data.json` | GoTNode 3개에 group 필드 추가 |
| `docs/architecture/NEO4J_INTEGRATION.md` | 5-2 수정, v1.3 갱신 |
| `docs/superpowers/plans/2026-04-07-neo4j-integration-plan.md` | v2 갱신, 완료 항목 반영 |

## 테스트

- `python -m dev.local_db.seed --neo4j` 오류 없이 완료
- GoTNode group 인덱스 정합성 확인

## 비고

- 로직 변경 없음 (시드 데이터 + 문서 수정)
- E2E 검증은 인프라 배포 후 별도 진행
```

---

*Neo4j 통합 구현 계획서 v3 — 2026-04-09*
*v1: 초안 / v2: 2차 다수 서브에이전트 점검 — seed_data.json group 필드 수정 완료, 문서 오류 정정*
*v3: 작업 2 완료 반영 (BE 3차 테스트 PASS, Mode A 구현 PR #88), 3-B-4 graph_analyses 불필요 확정, _publish_graph_to_backend() 제거 반영*

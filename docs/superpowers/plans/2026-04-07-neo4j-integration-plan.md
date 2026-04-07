# Neo4j 통합 구현 계획서

**버전**: v1  
**작성일**: 2026-04-07 13:30  
**기준 문서**: `docs/architecture/NEO4J_INTEGRATION.md` v1.2  
**작성 브랜치**: `feature/reasoning-docs-quality` (계획서 커밋용)  
**구현 브랜치**: `feature/validation-*` (개발자3 담당 코드 변경)

---

## 개요

Neo4j 통합 명세서(`NEO4J_INTEGRATION.md` v1.2)를 기반으로 다수의 서브에이전트 검증을 통해 확인된  
**실제 미완료 작업**만을 정리한 구현 계획서이다.

AI팀의 코드 구현은 대부분 완료 상태이며, 남은 것은 소규모 시드 데이터 수정 1건,  
인프라 배포 후 실행할 E2E 검증 2건, 그리고 Backend팀 협업 항목이 핵심이다.

---

## 현황 요약 — 이미 완료된 것

| 구분 | 항목 | 검증 방법 |
|------|------|----------|
| 모델 설정 | `config/settings.yaml` — podcast_reasoning: sonnet_37, max_tokens: 6000 | 파일 직접 확인 |
| 프롬프트 | `prompts/podcast/podcast_reasoning.yaml` — v3.1.0 존재 (group 6개 카테고리 포함) | 커밋 `986e06d` |
| DB 접속 | `src/db/neo4j_client.py`, `base.py`, `factory.py` | 코드 확인 |
| GoT 저장 | `podcast_reasoning.py` — `_save_got_to_neo4j()`, `_publish_graph_to_backend()` | 코드 확인 |
| 누적 계산 | `src/api/graph_cumulative.py` — EMA Mode A/B | 코드 확인 |
| 그래프 변환 | `src/api/graph_transformer.py` — `validate_group()` | 코드 확인 |
| DDL | `dev/local_db/neo4j/init.cypher` — 제약 5개 + 인덱스 7개 | 파일 확인 |
| 시드 스크립트 | `dev/local_db/seed.py` — Neo4j MERGE 로직 완성 | 코드 확인 |
| 시드 데이터 | `seed_data.json` — User(2), Session(2), Emotion(4), Topic(3), GoTNode(3) 존재 | 파일 직접 확인 |
| 통합 테스트 | `dev/local_db/test_neo4j_integration.py` | 파일 확인 |
| 로컬 Docker | `dev/local_db/docker-compose.db.yml` | 파일 확인 |

> `NEO4J_INTEGRATION.md` 섹션 5-2에 "Emotion/Topic 초기 데이터 없음"으로 표기되었으나,  
> 실제로는 `seed_data.json`에 이미 포함되어 있다. 계획서 상 이 항목은 **완료로 재분류**한다.

---

## 실제 미완료 작업 (AI팀 코드)

### 작업 1: GoTNode 시드 데이터에 `group` 필드 추가 (우선순위: 🔴 높음)

**브랜치**: `feature/validation-*` (개발자3)  
**파일**: `dev/local_db/fixtures/seed_data.json`  
**위치**: `neo4j.nodes.GoTNode` 배열 — 3개 항목

**발견 근거**:
- DDL에 `CREATE INDEX got_group FOR (g:GoTNode) ON (g.group)` 존재
- NEO4J_INTEGRATION.md 섹션 3-1: GoTNode 주요 속성에 `group` 명시
- 현재 seed_data.json의 GoTNode 3개에는 `group` 필드가 없음

**현재 상태** (got-test-001 예시):
```json
{
  "got_node_id": "got-test-001",
  "episode_id": "ep-test-001",
  "node_type": "root",
  "label": "직장 스트레스 분석",
  "weight": 1.0,
  "mysql_id": "got-test-001",
  "created_at": "2026-03-10T09:35:00Z"
}
```

**수정 내용** — 각 GoTNode에 `group` 필드 추가:
```
got-test-001: "group": "work_structure"    (직장 스트레스 분석)
got-test-002: "group": "emotional_exhaustion"  (이완 기법 탐색)
got-test-003: "group": "emotional_exhaustion"  (점진적 근육 이완법)
```

**허용 group 값** (6개): `work_structure`, `leadership`, `peer_relations`, `career_growth`, `culture_system`, `emotional_exhaustion`

**검증**: `python -m dev.local_db.seed --neo4j` 오류 없이 완료  
**커밋**: `fix: seed_data.json GoTNode group 필드 추가 (6-category schema)`

---

### 작업 2: E2E 검증 — GoT → Neo4j 저장 (우선순위: 🟡 중간, 인프라 선행 필요)

**브랜치**: `feature/validation-*` (개발자3)  
**선행 조건**: Phase 2 인프라 완료 (Neo4j 배포, 환경변수 등록)

| 검증 항목 | 명령 |
|---------|------|
| Neo4j 연결 확인 | `python -m dev.local_db.test_neo4j_integration` |
| 시드 데이터 적재 | `python -m dev.local_db.seed --neo4j` |
| GoT 저장 E2E | `pytest dev/local_db/test_neo4j_integration.py -v` |

**성공 기준**: GoTNode MERGE + LEADS_TO 관계 생성 확인

---

### 작업 3: E2E 검증 — RDB 누적 저장 Mode A (우선순위: 🟡 중간, Backend 선행 필요)

**브랜치**: `feature/validation-*` (개발자3)  
**선행 조건**: Phase 3-B Backend API 완료 (`GET/PUT /api/v1/graph_nodes`)

| 검증 항목 | 명령 |
|---------|------|
| EMA 단위 테스트 | `pytest tests/api/test_graph_cumulative.py -v` |
| 누적 저장 통합 | `pytest tests/api/test_graph_routes.py -v` |

**성공 기준**: Mode A 흐름 — Backend GET → EMA 계산 → Backend PUT 성공

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
| 3-B-2 | 기존 누적 데이터 조회 API | `GET /api/v1/graph_nodes?user_id=X` | ①필수 |
| 3-B-3 | 갱신된 누적 데이터 저장 API | `PUT /api/v1/graph_nodes` | ①필수 |
| 3-B-4 | GoT 분석 결과 저장 API | `POST /api/v1/graph_analyses` | ②필수 |
| 3-B-5 | 프론트엔드용 누적 그래프 조회 API | `GET /api/v1/graph/users/{id}/data` | ③연동 시 |

**Mode A 기준** (AI서버가 EMA 계산 후 전송): `PUT /api/v1/graph_nodes`는 단순 UPSERT만 수행.  
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
    3-A: 개발자3 — 작업 1 (seed_data group 필드) → 작업 2 E2E 검증
    3-B: Backend팀 — DDL + API 4개 구현 (3-A와 병렬 진행 가능)
    선행: Phase 2 완료 (3-A-2/3-A-3), Phase 3-B 완료 (작업 3)

Phase 4 ─── 통합 검증 (전체 팀, ~2일)
    pytest tests/api/ -v
    GoT 저장 → Neo4j 조회 → EMA 계산 → Backend PUT 흐름 검증

Phase 5 ─── 프로덕션 배포 (인프라팀 주도)
```

---

## 전체 테스트 기준

작업 1 완료 후 (코드 변경 없음, seed 데이터만):
```
python -m dev.local_db.seed --neo4j  # 오류 없이 완료
```

작업 2, 3 완료 후 (인프라 + Backend 준비 필요):
```
pytest dev/local_db/test_neo4j_integration.py -v
pytest tests/api/test_graph_cumulative.py -v
pytest tests/api/test_graph_routes.py -v
```

---

## PR 양식 (작업 1용)

**PR 제목:**
```
fix: GoTNode 시드 데이터 group 필드 추가 (Neo4j schema 정합성)
```

**Base**: `develop` | **Compare**: `feature/validation-*`

**PR Body 요약:**
```markdown
## 개요

seed_data.json GoTNode 3개에 `group` 필드 누락 발견 (NEO4J_INTEGRATION.md 검토 중).
DDL의 `got_group` 인덱스 및 6-category spec과 불일치를 수정한다.

## 변경 내역

| 파일 | 변경 내용 |
|------|----------|
| `dev/local_db/fixtures/seed_data.json` | GoTNode 3개에 group 필드 추가 |

## 테스트

- `python -m dev.local_db.seed --neo4j` 오류 없이 완료
- GoTNode `group` 인덱스 정합성 확인

## 비고

- 로직 변경 없음 (시드 데이터 fix)
- E2E 검증은 인프라 배포 후 별도 진행
```

---

*Neo4j 통합 구현 계획서 v1 — 2026-04-07 13:30*  
*다수 서브에이전트 교차 검증 + seed_data.json 직접 확인 반영*

# Plan #8 재분류 — api_proxy Dead Code 정리 + PLAN_INDEX 팩트 정정 계획서

**작성일**: 2026-04-15 19:00
**최종 점검**: 2026-04-15 20:00 (storage_mode 의존관계 추가 확인)
**기준 문서**:
- `docs/superpowers/PLAN_INDEX.md` #8 (TODO(backend) 21건 해소)
- `src/db/api_proxy.py` (9건 TODO), `src/api/backend_resources.py` (5건 TODO), `src/db/s3_client.py` (1건 TODO)

**작업 유형**: 구현 계획 전용 — 본 문서 생성까지. 실제 코드 수정/커밋/푸시는 별도 승인 후 착수.

**범위**: Option A (api_proxy.py Dead Code 정리) + Option C (PLAN_INDEX 팩트 정정). **Plan #45 A9 및 기타 항목은 본 계획서 범위 외.**

---

## 0. Executive Summary

### 0.1 핵심 발견

1. **PLAN_INDEX #8 항목 숫자 오류**
   - 현재 표기: `TODO(backend) 21건 해소 — api_proxy.py 15건, backend_resources.py 5건, s3_client.py 1건`
   - **실제 집계** (`grep -rn "TODO(backend)" src/`):
     - `src/db/api_proxy.py`: 9건 (메타 주석 2건 제외, 함수 단위 TODO만)
     - `src/api/backend_resources.py`: 5건
     - `src/db/s3_client.py`: 1건
     - **총 15건** (not 21)
   - 추가로 `config/settings.yaml:163`에 1건 (src/ 범위 외), `CLAUDE.md:225`에 문서 참조 1건

2. **`src/db/api_proxy.py`는 사실상 Dead Code**
   - `create_vector_client()` / `create_rdb_client()` / `create_storage_client()` 는 **src/ 내 런타임 호출자 0건** (only docstring 예시 및 `dev/`, `tests/`)
   - `create_graph_client()` 만 2곳에서 런타임 호출 (`src/api/routes/graph.py:69`, `src/agents/podcast/podcast_reasoning.py:606`)
   - 하지만 프로젝트 결정 ([project_neo4j_no_migration](../../../.claude/projects/-Users-kttechup-Documents-NewProject-mind-log/memory/project_neo4j_no_migration.md)): **Neo4j AI 서버 직접 운영 확정** → proxy 분기는 영원히 실행되지 않음
   - `GraphProxyClient.execute_query()` 는 이미 `return []` 무조건 반환 (엔드포인트 미구현 상태로 고정)

3. **Backend 팀 협의 불필요 항목**
   - `RESOURCE_VECTOR_SEARCH` / `RESOURCE_GRAPH_QUERY` / `RESOURCE_STORAGE_UPLOAD` / `RESOURCE_STORAGE_OBJECT` (4건): api_proxy 전용 → proxy 제거 시 **상수 자체 불필요**
   - `api_proxy.py` 의 9건: 파일 통째 제거 시 자연 해소

4. **실제 Backend 팀 협의 필요 항목 (잔존)**
   - `RESOURCE_SESSION` (backend_resources.py:32): 세션 경로 협의 — Backend 팀 대기 중
   - `src/db/s3_client.py:67` upload_prefix: Backend와 협의 — 단, 현재 S3 직접 운영 확정이라 재검토 필요
   - `config/settings.yaml:163` upload_prefix (동일 건)

### 0.2 권장 실행 순서

1. **Option C 먼저** (1 PR, 소규모, 즉시 착수 가능)
   - PLAN_INDEX #8 숫자 정정: `21건 → 15건`
   - Dead code 사실 반영 주석 추가
2. **Option A** (1~2 PR, 중규모, Option C 머지 후 착수)
   - `src/db/api_proxy.py` 파일 제거
   - `src/db/factory.py` proxy 분기 제거 + mode 기본값 재평가
   - `src/api/backend_resources.py` 상수 4건 제거
   - 테스트 / 문서 / 설정 동기화

---

## 1. 브랜치 전략

| 브랜치명 | 옵션 | PR base | 리뷰 요건 |
|---------|------|---------|----------|
| `feature/validation-plan-index-fact-fix` | Option C | `develop` | 1인 이상 |
| `feature/validation-apiproxy-cleanup` | Option A | `develop` | 3인 합의 (factory.py / settings.yaml 공용 인프라 인접) |

**규칙**:
- 담당 개발자: 개발자3 (Batch Validator / Learning 영역 외이나 `docs/` 및 `src/db/` 정리 성격이라 `feature/validation-*` prefix 허용 — 3인 합의 사항에서 별도 승인 필요)
- Option C 머지 확인 후 Option A 착수 (PLAN_INDEX 수치 기준점 확정)

---

## 2. Option C — PLAN_INDEX 팩트 정정 (먼저)

### 2.1 목표

PLAN_INDEX #8 항목의 숫자 부정확성을 제거하고, Dead code 특성을 명시하여 후속 작업 (Option A) 에 대한 명확한 근거를 남긴다.

### 2.2 영향 파일

| 파일 | 변경 유형 | 라인 |
|------|---------|------|
| `docs/superpowers/PLAN_INDEX.md` | 수정 | 143 (본 항목) + 상단 version 헤더 |

### 2.3 변경 내용

#### 2.3.1 `docs/superpowers/PLAN_INDEX.md:143` 수정

**BEFORE**:
```markdown
| 8 | TODO(backend) 21건 해소 | 백엔드 팀 | api_proxy.py 15건, backend_resources.py 5건, s3_client.py 1건 |
```

**AFTER**:
```markdown
| 8 | TODO(backend) 15건 해소 | 백엔드 팀 + AI 팀 | api_proxy.py 9건 (※Dead code, Option A로 자연 해소 가능), backend_resources.py 5건 (proxy 전용 4건 포함), s3_client.py 1건. 상세: docs/superpowers/plans/2026-04-15-plan8-apiproxy-cleanup-plan.md |
```

**근거**:
- 실측 집계 명시 (15건)
- Dead code 특성으로 **Backend 팀 대기 항목이 아닌** AI 팀 자체 정리 가능 항목임을 표기
- 후속 계획서 참조 링크 제공

#### 2.3.2 version 헤더 범프

현재: `v41 (2026-04-15)` → `v42 (2026-04-15)` (날짜 동일, 마이너 정정)

### 2.4 비-수정 대상 (의도적 유지)

- `docs/reports/STRUCTURAL_REVIEW_2026-04-15.md:636` 의 `TODO(backend) 22건` 표기: 구조 보고서 원본은 특정 시점 스냅샷이므로 **유지** (PLAN_INDEX 가 최신 진실 소스).
- `docs/_archive/` 내 과거 계획서 (`14건`, `25건`, `26건` 등 역대 수치): archive 는 원본 보존.

### 2.5 검증

| 검증 항목 | 방법 |
|---------|------|
| grep 실측과 일치 | `grep -rn "TODO(backend)" src/ \| grep -v "^src/db/api_proxy.py:[78]:"` 결과 15줄 (9+5+1) |
| 링크 유효성 | `docs/superpowers/plans/2026-04-15-plan8-apiproxy-cleanup-plan.md` 파일 존재 여부 (본 문서) |
| Markdown 렌더 | VSCode / GitHub 프리뷰에서 테이블 깨짐 없음 |

### 2.6 커밋 / PR

- 커밋 메시지: `docs: PLAN_INDEX #8 TODO(backend) 수치 정정 (21→15) + Dead code 특성 명시`
- PR 타이틀: `docs: PLAN_INDEX #8 TODO(backend) 수치 정정`
- PR 본문 (요약):
  - 실측 재집계 결과 15건 (기존 표기 21건 오류)
  - api_proxy.py 9건은 Dead code → 별도 Option A 계획서로 이관
- Base: `develop`
- 리뷰: 1인 이상

---

## 3. Option A — api_proxy.py Dead Code 정리 (Option C 머지 후)

### 3.1 목표

1. `src/db/api_proxy.py` 전체 제거 → TODO(backend) 9건 자연 해소
2. `src/api/backend_resources.py` proxy 전용 상수 4건 제거 → TODO(backend) 4건 자연 해소
3. `src/db/factory.py` proxy 분기 제거 → 코드 단순화
4. `storage_mode` 설정의 의미 재정의 — 실제 사용되지 않는 `proxy` / `hybrid` 값 처리 결정

### 3.2 현재 상태 실측

#### 3.2.0 storage_mode 의존관계 전체 목록 (2차 점검 결과)

`storage_mode` / `STORAGE_MODE` 를 읽는 모든 위치를 확인한 결과:

| 위치 | 사용 목적 | 제거 가능 여부 |
|------|---------|------------|
| `src/db/factory.py:34,52,70,89` | proxy/hybrid 분기 — 삭제 대상 | ✅ 제거 |
| `config/loader.py:377` `storage_mode` 프로퍼티 | 값 읽기 제공 | ⚠️ **유지 필수** (아래 항목들이 의존) |
| `src/api/main.py:59,62,63,64` | 앱 시작 로그 (`STORAGE_MODE=%s` 출력) | ⚠️ **유지** (모니터링용) |
| `src/api/routes/health.py:63,68` | `/health/ready` 응답에 `storage_mode` 필드 포함 | ⚠️ **유지** (AWS ALB 헬스체크 관찰용) |
| `tests/api/test_health_endpoint.py:35,36` | `storage_mode` 필드 존재 여부 테스트 | ✅ 변경 없음 |
| `dev/scripts/validate_pinecone_env.py:48-55` | `proxy` 유효 여부 검증 + WARN 출력 | ⚠️ 수정 필요 (§3.4 TASK A-8) |
| `tests/db/test_pinecone_scripts.py:49-58` | `proxy` WARN 테스트 | ⚠️ 수정 필요 (TASK A-5 연동) |
| `dev/local_db/verify.py:430,431` | `STORAGE_MODE=local` 확인 | ✅ 변경 없음 (local만 허용 — 의도에 부합) |
| `dev/local_db/.env.db.example:3` | `STORAGE_MODE=local` 예시 | ✅ 변경 없음 |
| `docker-compose.yml:42` | "STORAGE_MODE=proxy로 변경" 주석 | ⚠️ 주석 삭제 필요 (TASK A-7) |

> **핵심 결론**: `config/loader.py` `storage_mode` 프로퍼티는 **절대 제거 불가** — `src/api/main.py`와 `src/api/routes/health.py`가 모니터링 목적으로 실제로 사용 중. 3인 합의 안건에서 "제거 여부" 는 범위 외.

#### 3.2.1 Proxy 클라이언트 사용처 (src/ 런타임)

| Factory 함수 | src/ 내 런타임 호출자 | proxy 분기 반환 클래스 |
|------------|-------------------|------------------|
| `create_vector_client()` | **0건** | `VectorProxyClient` (dead) |
| `create_graph_client()` | `src/api/routes/graph.py:69`, `src/agents/podcast/podcast_reasoning.py:606` | `GraphProxyClient` (`return []` 고정) |
| `create_rdb_client()` | **0건** | `RDBProxyClient` (dead) |
| `create_storage_client()` | **0건** | `StorageProxyClient` (dead) |

> 비 src/ 사용처 (참고만): `dev/local_db/verify.py`, `dev/local_db/test_factory_crossdb.py`, `tests/db/test_factory_vector.py`, `tests/agents/podcast/test_podcast_reasoning.py`, `tests/api/test_graph_routes.py`

#### 3.2.2 실제 운영 경로

- **Pinecone**: 에이전트는 `PineconeClient` 직접 인스턴스화 (factory 미경유) — `src/agents/podcast/episode_memory.py` 등
- **Neo4j**: `create_graph_client()` → local 분기 → `Neo4jClient` (proxy 분기는 사용 안 됨)
- **MySQL**: 에이전트는 `BackendClient.save()/load()` 직접 호출 (factory 미경유)
- **S3**: `S3Client` 직접 인스턴스화 (`src/agents/podcast/visualization.py` 등, factory 미경유)

### 3.3 영향 파일 (변경 매트릭스)

| 파일 | 변경 유형 | 영향 라인 / 범위 |
|------|---------|--------------|
| `src/db/api_proxy.py` | **삭제** | 전체 파일 (263줄) |
| `src/db/factory.py` | 수정 | `create_vector_client` / `create_graph_client` / `create_rdb_client` / `create_storage_client` proxy 분기 제거 (35~94번 라인) |
| `src/db/__init__.py` | 검토 (수정 없음 전망) | 4개 factory 함수는 유지 (이름 변경 없음) |
| `src/db/base.py` | 수정 (주석만) | docstring 에서 "STORAGE_MODE에 따라 자동 선택" 표현 단순화 |
| `src/api/backend_resources.py` | 수정 | `RESOURCE_VECTOR_SEARCH` / `RESOURCE_GRAPH_QUERY` / `RESOURCE_STORAGE_UPLOAD` / `RESOURCE_STORAGE_OBJECT` 4개 상수 + 섹션 주석 제거 (39~43 라인) |
| `config/settings.yaml` | 수정 | `storage.mode` 기본값 `proxy` → `local` (또는 섹션 전체 제거) |
| `config/loader.py` | 수정 | `storage_mode` 프로퍼티 제거 여부 결정 |
| `tests/db/test_factory_vector.py` | 수정 | `test_proxy_mode_returns_proxy_client` 삭제, 나머지 3건은 직접 클라이언트 반환 검증으로 유지 |
| `dev/scripts/validate_pinecone_env.py` | 수정 | `proxy` 경고 제거 |
| `docker-compose.yml` | 수정 | `STORAGE_MODE` 주석 정리 |
| `docs/architecture/VECTOR_DB_RAG_GUIDE.md` | 수정 | factory 예시에서 proxy 모드 언급 제거 |
| `docs/architecture/AGENT_OUTPUT_CONTRACT.md` | 수정 | `RESOURCE_*` 4건 관련 설명 제거 (565번대) |
| `docs/architecture/NEO4J_INTEGRATION.md` | 수정 | 프록시 모드 관련 서술 간소화 (294, 1156, 1187, 1195 라인) |
| `docs/guides/NEO4J_DEPLOYMENT_ANALYSIS.md` | 수정 | GraphProxyClient 관련 서술 제거/갱신 (45, 101, 117 라인) |
| `docs/architecture/API_ARCHITECTURE.md` | 검토 | TODO(backend) 서술 정리 여부 |
| `docs/reports/현재_구현_API_목록.md` | 검토 | proxy 엔드포인트 기대 목록 제거 |
| `docs/reports/SECURITY_REMEDIATION_TRACKER.md` | 참조만 | 변경 없음 |
| `docs/superpowers/PLAN_INDEX.md` | 수정 | #8 항목 재조정 (`15건 → 6건`) 또는 완료 표시 |
| `CLAUDE.md` | 수정 | `storage.mode` 설명 갱신 (181~182, 223~225 라인 부근) |

### 3.4 세부 태스크 분해 (실행 순서)

> TASK A-1, A-2, A-3 은 동일 커밋에 포함해야 import 에러를 피할 수 있다.

#### TASK A-1: `src/db/api_proxy.py` 삭제

**전제조건**: TASK A-2, A-3 (factory.py / backend_resources.py import 정리) 를 동일 커밋에 포함하여 import 에러 회피.

**변경**:
- 파일 전체 삭제
- `src/db/__init__.py` 에서 `api_proxy` 직접 import 없음 (검증 완료 — factory.py 내부 import 만 사용) → 추가 작업 불필요

**검증**:
- `grep -rn "api_proxy" src/ tests/` 결과 0건
- `grep -rn "VectorProxyClient\|GraphProxyClient\|RDBProxyClient\|StorageProxyClient" src/ tests/` 결과 0건 (docs/ 제외)

#### TASK A-2: `src/db/factory.py` proxy 분기 제거

**변경**:

`create_vector_client()` AFTER:
```python
def create_vector_client() -> BaseVectorClient:
    """벡터 DB 클라이언트를 생성한다 (Pinecone 직접 접속)."""
    from src.db.pinecone_client import PineconeClient
    return PineconeClient()
```

`create_graph_client()` AFTER:
```python
def create_graph_client() -> BaseGraphClient:
    """그래프 DB 클라이언트를 생성한다 (Neo4j 직접 접속)."""
    from src.db.neo4j_client import Neo4jClient
    return Neo4jClient()
```

`create_rdb_client()` AFTER:
```python
def create_rdb_client() -> BaseRDBClient:
    """관계형 DB 클라이언트를 생성한다 (MySQL 직접 접속)."""
    from src.db.mysql_client import MySQLClient
    return MySQLClient()
```

`create_storage_client()` AFTER:
```python
def create_storage_client() -> BaseStorageClient:
    """오브젝트 스토리지 클라이언트를 생성한다 (S3 직접 접속)."""
    from src.db.s3_client import S3Client
    return S3Client()
```

**삭제 대상 import**:
- `import os` (S3_MODE env 참조 제거 시)
- `from config.loader import get_settings` (mode 분기 제거 시)

**공용 인프라 영향**: `config/loader.py` 의 `storage_mode` 프로퍼티를 제거할 경우 3인 합의 필요. 제거 대신 **유지+deprecated 주석** 으로 시작하는 것을 권장 (후속 PR 에서 제거).

#### TASK A-3: `src/api/backend_resources.py` 상수 정리

**삭제**:
```python
# --- 프록시 전용 (STORAGE_MODE=proxy/hybrid 시) ---
RESOURCE_VECTOR_SEARCH = "vector/search"  # TODO(backend)
RESOURCE_GRAPH_QUERY = "graph/query"  # TODO(backend)
RESOURCE_STORAGE_UPLOAD = "storage/upload"  # TODO(backend)
RESOURCE_STORAGE_OBJECT = "storage/object"  # TODO(backend)
```

**유지**:
- `RESOURCE_SESSION` — Backend 팀 경로명 협의 대기 (TODO 유지)

**검증**:
- `grep -rn "RESOURCE_VECTOR_SEARCH\|RESOURCE_GRAPH_QUERY\|RESOURCE_STORAGE_UPLOAD\|RESOURCE_STORAGE_OBJECT" src/ tests/` → 0건

#### TASK A-4: `storage_mode` 설정 결정

**선택지 A (권장 — 단일 선택지)**:
- `config/settings.yaml:159`: `mode: "proxy"` → `mode: "local"` 로 변경
- `config/loader.py` `storage_mode` 프로퍼티: **유지 필수**
  - `src/api/main.py` 앱 시작 로그, `src/api/routes/health.py` ReadyResponse 가 실제로 사용 중
  - 제거 시 두 파일을 함께 수정해야 하며 /health/ready 응답 스키마 변경 → 별도 논의 필요
  - 프로퍼티 유지 + 기본값을 `"local"` 로 변경하는 것이 최소 변경

**선택지 B (범위 초과)**: `storage_mode` 프로퍼티 + `/health/ready` 필드 동시 제거 → 본 PR 범위 초과, 별도 안건으로 분리.

**결정**: 선택지 A 만 진행. 3인 합의 안건은 "settings.yaml 기본값 변경"으로 한정.

#### TASK A-5: 테스트 수정

**`tests/db/test_factory_vector.py`**:

| 기존 테스트 | 조치 | 이유 |
|-----------|------|------|
| `test_local_mode_returns_pinecone_client` | **수정** (mock 제거) | factory가 mode 분기 없이 항상 PineconeClient 반환 → `get_settings` mock 불필요 |
| `test_hybrid_mode_returns_pinecone_client` | **삭제** | hybrid 분기 제거로 독립 테스트 불필요 |
| `test_proxy_mode_returns_proxy_client` | **삭제** | proxy 분기 및 api_proxy 파일 삭제 |
| `test_returns_base_vector_client_interface` | **수정** (mock 제거) | mode 분기 없이 항상 PineconeClient → `get_settings` mock 불필요 |

변경 후 `test_factory_vector.py` 는 2개 테스트로 단순화:
1. `test_returns_pinecone_client` — `create_vector_client()` 가 `PineconeClient` 반환
2. `test_implements_base_vector_client` — `BaseVectorClient` 인터페이스 구현 여부

**`tests/db/test_pinecone_scripts.py`**:

| 기존 테스트 | 조치 | 이유 |
|-----------|------|------|
| `test_proxy_mode_shows_warning` | **수정** | validate_pinecone_env.py 에서 proxy WARN 동작 변경에 따라 기대값 조정 |

→ TASK A-8 (validate_pinecone_env.py 수정) 결과에 맞춰 갱신.

**`tests/agents/podcast/test_podcast_reasoning.py`**: `_patch_create_graph_client` 헬퍼 (680~731 라인) — `create_graph_client` 함수 자체는 유지되므로 변경 없음. CI 통과 확인만.

**`tests/api/test_graph_routes.py:45`**: `create_graph_client = MagicMock()` — 함수 서명 변경 없음. 변경 없음.

**`tests/api/test_health_endpoint.py:35,36`**: `storage_mode` 필드 유지 — 변경 없음.

**`dev/local_db/test_factory_crossdb.py`**: `STORAGE_MODE=local` 케이스만 테스트하므로 proxy 분기 제거 영향 없음. 확인만.

**전체 회귀**:
```bash
pytest tests/ -v -m "not live"
pytest dev/local_db/ -v  # 로컬 DB 연결 가능 시
```

#### TASK A-6: 문서 동기화

| 파일 | 변경 사항 |
|------|---------|
| `CLAUDE.md:181` | "저장 모드(`config/settings.yaml`의 `storage.mode`): `local` \| `proxy`(기본) \| `hybrid`" → `local` 단일값으로 갱신 |
| `CLAUDE.md:223~225` | "세션 리소스: sessions (`TODO(backend)`)" 서술 유지 (RESOURCE_SESSION 상수 유지되므로) |
| `src/db/base.py:5,9,13` | docstring 에서 "STORAGE_MODE 환경변수에 따라 프록시 구현체 선택" 서술 제거, proxy 언급 삭제 |
| `src/db/__init__.py:5` | docstring `STORAGE_MODE 환경변수에 따라 직접/프록시 구현체를 자동 선택` 갱신 |
| `docs/architecture/VECTOR_DB_RAG_GUIDE.md` | 389, 526~530 라인: proxy 언급 제거, factory 예시 단순화 |
| `docs/architecture/NEO4J_INTEGRATION.md` | 294, 1156, 1187, 1195 라인: 팩토리 예시 proxy 분기 서술 제거 |
| `docs/guides/NEO4J_DEPLOYMENT_ANALYSIS.md` | 45, 101, 117 라인: GraphProxyClient 서술 제거, "Neo4j 직접 운영 확정" 으로 통일 |
| `docs/architecture/AGENT_OUTPUT_CONTRACT.md` | 565 라인대: `RESOURCE_*` 4건 표 행 제거 반영 |
| `docs/reports/현재_구현_API_목록.md` | proxy 전용 엔드포인트 기대 목록 제거 |
| `docs/superpowers/PLAN_INDEX.md` | #8 항목: `15건 → 6건` (api_proxy.py 9건 + backend_resources.py proxy 전용 4건 = 13건 해소, 잔존 2건) 또는 완료 분류 후 잔존 2건을 별도 항목으로 이관 |

#### TASK A-7: settings.yaml / docker-compose 정리

**`config/settings.yaml:159`**:
```yaml
# 변경 전
storage:
  mode: "proxy"    # local | proxy | hybrid  [수정] 프로덕션 환경: proxy (백엔드 API 저장)

# 변경 후
storage:
  mode: "local"    # local (Pinecone/Neo4j/MySQL/S3 직접 접속) — proxy/hybrid 제거됨 (Plan #8 Option A)
```

**`docker-compose.yml:42`**: 이관 주석 블록 (38~42) 에서 line 42 삭제:
```
# 4. .env에서 STORAGE_MODE=proxy로 변경  ← 이 줄 삭제
```
Neo4j 직접 운영 확정으로 "Backend 이관 시 절차" 주석 자체 무의미. 주석 블록(38~42) 전체 삭제 권장.

#### TASK A-8: `dev/scripts/validate_pinecone_env.py` 수정

현재 `proxy` 는 유효한 값으로 인정 + WARN 출력. factory.py 에서 proxy 분기 제거 후에는:
- `STORAGE_MODE=proxy` 설정 시 factory 는 직접 클라이언트 반환 (proxy 무시)
- validate 스크립트의 "Pinecone 직접 연결 테스트 시 local 또는 hybrid 필요" WARN 은 의미 없음

**변경 방향 (권장 — 최소 변경)**:

```python
# 변경 전
elif mode == "proxy":
    print("\n[WARN] STORAGE_MODE=proxy (기본값)")
    print("  Pinecone 직접 연결 테스트 시 오버라이드 필요:")
    print("  STORAGE_MODE=local python dev/scripts/validate_pinecone_env.py")

# 변경 후
elif mode == "proxy":
    print("\n[WARN] STORAGE_MODE=proxy (Deprecated — factory에서 직접 클라이언트로 대체됨)")
    print("  로컬 테스트: STORAGE_MODE=local python dev/scripts/validate_pinecone_env.py")
```

`tests/db/test_pinecone_scripts.py:test_proxy_mode_shows_warning` 의 기대값도 함께 갱신:
```python
# 변경 전
assert "WARN" in captured.out
# 변경 후
assert "WARN" in captured.out
assert "Deprecated" in captured.out  # 또는 기존 "WARN" 만으로 충분 → 기대값 그대로 유지 가능
```

> WARN 키워드 자체는 유지되므로 `assert "WARN" in captured.out` 만 사용하는 기존 테스트는 **변경 불필요** — 가장 작은 변경.

### 3.5 위험 및 완화

| 위험 | 영향 | 완화 |
|------|-----|------|
| `STORAGE_MODE=proxy` 환경변수가 EC2 / .env 에 남아있을 경우 | factory는 직접 클라이언트 반환(무해), main.py/health.py는 로그에 `proxy` 출력 | 배포 .env 에서 값 `local` 로 변경 권고 (GitHub Secrets / SSM 확인) |
| `hybrid` 모드에서 RDBProxyClient 사용 중이라면 프로덕션에서 MySQL 직접 접속으로 전환 | MySQL 직접 연결 불가 시 에러 | **실측 확인 완료**: src/ 내 `create_rdb_client()` 런타임 호출 0건 → 영향 없음 |
| `config/loader.py` `storage_mode` 제거 시도 | `src/api/main.py`, `src/api/routes/health.py` 동시 수정 필요, /health/ready 스키마 변경 | **본 PR 에서 제거 안 함** — 프로퍼티 유지 확정 |
| TASK A-1,2,3 분리 커밋 시 import 에러 | CI 실패 | 3개 태스크 반드시 동일 커밋 |
| 테스트 CI 실패 (`test_proxy_mode_returns_proxy_client`, `test_hybrid_mode_returns_pinecone_client`) | PR 차단 | TASK A-5 로 동일 PR 에서 해소 — 단, `test_proxy_mode_shows_warning` 은 WARN 키워드 유지로 **변경 불필요** |

### 3.6 롤백 전략

- **전체 롤백**: git revert (단일 PR 로 처리 시)
- **부분 롤백**:
  - TASK A-1 (api_proxy.py 삭제) 만 롤백 불가능한 시나리오가 있다면 git 에서 해당 파일 복원 + factory.py proxy 분기 재추가
  - 실제로 proxy 분기가 필요해진다면 **KT Cloud RAG 연동 (Plan #33)** 에서 별도 설계 (본 프로젝트는 직접 접속 확정)

### 3.7 검증

| 검증 항목 | 방법 | 합격 기준 |
|---------|------|--------|
| TODO(backend) 감소 | `grep -rn "TODO(backend)" src/` | 15건 → 2건 (api_proxy.py 9 + backend_resources.py proxy 전용 4 = 13건 소멸) |
| import 에러 없음 | `python -c "from src.db import create_vector_client, create_graph_client, create_rdb_client, create_storage_client"` | ImportError 없음 |
| api_proxy 완전 제거 | `grep -rn "api_proxy\|VectorProxyClient\|GraphProxyClient\|RDBProxyClient\|StorageProxyClient" src/ tests/` | 0건 (docs/ 는 허용) |
| health 엔드포인트 | `pytest tests/api/test_health_endpoint.py -v` | 통과 (storage_mode 필드 유지 확인) |
| 전체 테스트 | `pytest tests/ -v -m "not live"` | 기존 596에서 proxy 테스트 2건 삭제 → 594 이상 passed |
| mypy | `mypy src/ --ignore-missing-imports` | 기존 대비 신규 에러 0건 |
| Docker 빌드 | `docker build -t mindlog-ai:test .` | 성공 |
| CI 전체 | GitHub Actions `lint / test / docker-build` | 3개 Job 성공 |

### 3.8 PR 전략

**단일 PR** (권장):
- 타이틀: `refactor: api_proxy.py Dead Code 제거 및 storage.mode 단순화 (Plan #8 Option A)`
- Base: `develop`
- 리뷰: 3인 합의 (공용 인프라 `config/loader.py`, `config/settings.yaml` 영향)

**2단계 PR** (대안):
1. PR#1: `src/db/api_proxy.py` 삭제 + factory.py + backend_resources.py + 테스트 (기능 정리)
2. PR#2: 문서 동기화 + settings.yaml 기본값 변경 + storage_mode deprecated (정책)

PR#1 은 개발자3 리뷰 1인, PR#2 는 3인 합의. 트레이드오프: PR 개수 증가 vs. 리스크 분산.

---

## 4. 전체 실행 순서

```
[Step 1] Option C 브랜치 생성
          ↓
feature/validation-plan-index-fact-fix
          ↓
PLAN_INDEX #8 수치 정정 + version bump
          ↓
PR 생성 → 1인 리뷰 → develop 머지
          ↓
[Step 2] storage_mode 정책 3인 협의 (선택지 A vs B)
          ↓
[Step 3] Option A 브랜치 생성
          ↓
feature/validation-apiproxy-cleanup
          ↓
TASK A-1 ~ A-7 순차 수행 (단일 커밋 or 단계별 커밋)
          ↓
로컬 검증: pytest / mypy / docker build
          ↓
PR 생성 → 3인 합의 → develop 머지
          ↓
[Step 4] PLAN_INDEX #8 완료 처리 (또는 잔존 2건 으로 재분류)
```

---

## 5. 남는 TODO(backend) 재분류

Option A 완료 후 `src/` 내 잔존 TODO(backend):

| 파일 | 항목 | 처리 방향 |
|------|------|---------|
| `src/api/backend_resources.py:32` | `RESOURCE_SESSION` 경로명 | **Backend 팀 협의 유지** (Plan #8 이관) |
| `src/db/s3_client.py:67` | `upload_prefix` 구조 | **AI 팀 내부 결정 가능** (S3 직접 운영 확정) — 별도 이슈로 분리 |
| `config/settings.yaml:163` | `upload_prefix` (동일 건) | s3_client.py 결정과 동기화 |

**→ PLAN_INDEX #8 재표기안**:
```markdown
| 8 | TODO(backend) 잔존 2건 | 백엔드 팀 1건 + AI 팀 1건 | backend_resources.py RESOURCE_SESSION(백엔드), s3_client.py upload_prefix(AI 팀 결정 가능) |
```

---

## 6. 검토 포인트

### 6.1 3인 합의 필요 안건

1. `config/settings.yaml` `storage.mode` 기본값 변경 (`proxy` → `local`)
2. `CLAUDE.md` 저장 모드 서술 변경 (공용 문서)
3. 단일 PR vs 2단계 PR 전략

> ~~`config/loader.py` `storage_mode` 프로퍼티 제거 여부~~ → **제거 불가 확정** (main.py, health.py 실제 사용 중). 안건에서 제거.

### 6.2 개발자3 단독 결정 가능 안건

1. Option C 단독 실행 (PLAN_INDEX 수치 정정만)
2. `tests/db/test_factory_vector.py` proxy 테스트 제거
3. `docs/architecture/*.md` proxy 서술 정리

### 6.3 Backend 팀 동의 불필요

- api_proxy.py 자체가 Backend 팀과 협의 없는 **AI 팀 추정 구현** 이므로 제거 역시 AI 팀 자체 결정 가능
- 제거 후 Backend 팀과의 계약 면적이 줄어들 뿐, 기존 실제 호출되는 API (`/greenroom/ingest/ai/{resource}` save/load) 는 변경 없음

---

## 7. 부록

### 7.1 TODO(backend) 실측 집계 (2026-04-15 19:00)

```
$ grep -rn "TODO(backend)" src/ | grep -v "^src/db/api_proxy.py:[78]:"
src/api/backend_resources.py:32:RESOURCE_SESSION = "sessions"  # TODO(backend): 경로명 확정
src/api/backend_resources.py:40:RESOURCE_VECTOR_SEARCH = "vector/search"  # TODO(backend): 엔드포인트 존재 여부 확인
src/api/backend_resources.py:41:RESOURCE_GRAPH_QUERY = "graph/query"  # TODO(backend): 그래프 쿼리 엔드포인트 확인
src/api/backend_resources.py:42:RESOURCE_STORAGE_UPLOAD = "storage/upload"  # TODO(backend): 이미지 업로드 엔드포인트 확인
src/api/backend_resources.py:43:RESOURCE_STORAGE_OBJECT = "storage/object"  # TODO(backend): S3 객체 조회 엔드포인트 확인
src/db/s3_client.py:67:        TODO(backend): 4-4 업로드 prefix 구조 확정 (현재: vis/{user_id}/{id}/)
src/db/api_proxy.py:45:        TODO(backend): 4-3 벡터 검색 엔드포인트 POST /api/vector/search 확인 필요
src/db/api_proxy.py:72:        TODO(backend): 4-3 벡터 upsert 엔드포인트 확인 필요
src/db/api_proxy.py:138:        TODO(backend): 4-2 resource 경로 + 쿼리 파라미터 매핑 확정 필요
src/db/api_proxy.py:139:        TODO(backend): 4-3 SQL 쿼리 프록시 vs REST resource 방식 결정
src/db/api_proxy.py:155:        TODO(backend): 4-3 쓰기 프록시 엔드포인트 확인 필요
src/db/api_proxy.py:182:        TODO(backend): 4-4 S3 객체 조회 엔드포인트 확인 필요
src/db/api_proxy.py:203:        TODO(backend): 4-4 이미지 업로드 엔드포인트 POST /api/storage/upload 확인
src/db/api_proxy.py:229:        TODO(backend): 4-4 객체 목록 조회 엔드포인트 확인 필요
src/db/api_proxy.py:246:        TODO(backend): 4-4 Presigned URL 생성 엔드포인트 확인 필요
```

총 **15줄** (api_proxy.py 9 + backend_resources.py 5 + s3_client.py 1)

### 7.2 삭제 대상 코드 규모

| 파일 | 현재 LOC | 제거 LOC | 남는 LOC |
|------|--------|---------|--------|
| `src/db/api_proxy.py` | 263 | 263 | 0 (파일 삭제) |
| `src/db/factory.py` | 99 | ~30 (proxy 분기) | ~69 |
| `src/api/backend_resources.py` | 59 | ~6 (4개 상수 + 섹션 주석) | ~53 |

### 7.3 연관 메모리 참조

- `project_neo4j_no_migration.md`: "AI 서버 직접 운영 확정, Backend 이관 안 함" — GraphProxyClient 제거 근거
- `project_excluded_roadmap_items.md`: 영구 제외 항목과 무관 (별도)
- `workflow_process_dev3.md`: `feature/validation-*` 브랜치 + PR 리뷰 대기 프로세스 준수

---

*작성자: 개발자3 (Mind-Log AI)*
*최종 수정: 2026-04-15 19:00*

# Neo4j 배포 분석 — "설치만 하면 되는가?"

> **작성일**: 2026-04-02
> **결론**: **아니오.** Neo4j 설치는 필요 조건이지 충분 조건이 아니다.
> 코드 통합, 스키마 초기화, 스토리지 모드 결정, 메모리 확보 등 추가 작업이 필요하다.

---

## 목차

1. [현재 상태 요약](#1-현재-상태-요약)
2. [설치만으로 해결되는 것](#2-설치만으로-해결되는-것)
3. [설치 외 추가 필요 작업](#3-설치-외-추가-필요-작업)
4. [STORAGE_MODE별 시나리오 분석](#4-storage_mode별-시나리오-분석)
5. [EC2 메모리 제약 분석](#5-ec2-메모리-제약-분석)
6. [작업 체크리스트](#6-작업-체크리스트)
7. [권장 배포 순서](#7-권장-배포-순서)

---

## 1. 현재 상태 요약

### 구현 완료 (준비된 것)

| 항목 | 파일 | 상태 |
|------|------|------|
| Neo4j 비동기 클라이언트 | `src/db/neo4j_client.py` | 완료 |
| 추상 인터페이스 | `src/db/base.py` (`BaseGraphClient`) | 완료 |
| 팩토리 패턴 | `src/db/factory.py` (`create_graph_client()`) | 완료 |
| Backend API 프록시 | `src/db/api_proxy.py` (`GraphProxyClient`) | 코드 완료, **Backend 엔드포인트 미구현** |
| 스키마 DDL | `dev/local_db/neo4j/init.cypher` | 완료 (제약 5개 + 인덱스 6개) |
| 통합 테스트 | `dev/local_db/test_neo4j_integration.py` | 완료 |
| 시드 데이터 | `dev/local_db/seed.py` | 완료 |
| 설정 | `config/settings.yaml` (databases.neo4j) | 완료 |
| 환경변수 템플릿 | `.env.example` (NEO4J_URL/USER/PASSWORD) | 완료 |
| 로컬 개발 Docker | `dev/local_db/docker-compose.db.yml` | 완료 |

### 미완료 / 비활성

| 항목 | 상태 | 비고 |
|------|------|------|
| 프로덕션 docker-compose.yml | Neo4j 서비스 **주석 처리** (L36~64) | `TODO: 구현 완료 후 주석 해제` |
| AI서버 depends_on | **주석 처리** (L19~21) | Neo4j 헬스체크 의존성 |
| Knowledge Agent | **Stub 사용 중** | `KnowledgeAgentStub` → 빈 결과 반환 |
| Backend graph/query 엔드포인트 | **미구현** | `TODO(backend): Cypher 쿼리 프록시 가능 여부 확인` |
| Neo4j 초기 데이터 | **미적재** | 프로덕션 시드 데이터 없음 |

---

## 2. 설치만으로 해결되는 것

AWS 인스턴스에 Neo4j를 설치하면 다음 **하나만** 해결된다:

> Neo4j Bolt 프로토콜 연결 가능 (`bolt://<host>:7687`)

즉, `Neo4jClient`가 드라이버를 생성하고 연결을 맺을 수 있게 된다:

```python
# src/db/neo4j_client.py — 이 부분만 동작
self._driver = AsyncGraphDatabase.driver(
    self._url,          # bolt://localhost:7687
    auth=(self._user, self._password),
)
```

**하지만 연결만 된다고 기능이 작동하지는 않는다.**

---

## 3. 설치 외 추가 필요 작업

### 3-1. 스키마 초기화 (필수)

Neo4j는 빈 데이터베이스로 시작한다. `init.cypher`를 실행하여 제약(Constraint)과 인덱스를 생성해야 한다.

```
# 필요한 제약 (5개)
User.user_id UNIQUE
Session.session_id UNIQUE
Emotion.emotion_key UNIQUE
Topic.topic_name UNIQUE
GoTNode.got_node_id UNIQUE

# 필요한 인덱스 (6개)
User.mysql_id, Session.mode, Emotion.category,
Topic.domain, GoTNode.episode_id, GoTNode.node_type
```

스키마 없이 쿼리하면 성능 저하 및 데이터 무결성 문제 발생.

### 3-2. STORAGE_MODE 결정 (필수)

현재 팩토리 패턴(`src/db/factory.py`)에서 `STORAGE_MODE` 환경변수로 클라이언트를 선택한다:

| 모드 | Neo4j 접근 방식 | 추가 요구사항 |
|------|----------------|-------------|
| `local` | AI서버 → Neo4j **직접 접속** | Neo4j가 AI서버와 같은 네트워크에 있어야 함 |
| `hybrid` | AI서버 → Neo4j **직접 접속** | `local`과 동일 (MySQL만 Backend 경유) |
| `proxy` (기본) | AI서버 → **Backend API** → Neo4j | Backend팀의 `POST /api/v1/graph/query` 구현 필요 |

**`proxy` 모드 문제점**: `GraphProxyClient`(`src/db/api_proxy.py:95~130`)는 코드가 있지만, Backend 서버(app-3)에 해당 엔드포인트가 **아직 없다** (`TODO(backend)` 상태).

### 3-3. Knowledge Agent 통합 (핵심 기능)

현재 `PodcastReasoningAgent`는 Knowledge Agent를 **Stub으로 호출**한다:

```python
# src/agents/shared/stubs.py
class KnowledgeAgentStub:
    async def search(self, query, domain="mental_health"):
        return {"articles": [], "guidelines": []}  # ← 항상 빈 결과
```

Neo4j가 설치되어도 Knowledge Agent가 Stub이면 **그래프 데이터를 전혀 활용하지 못한다.**

필요한 통합 작업:
- Knowledge Agent(개발자1 담당)에서 `create_graph_client()`를 사용하여 Cypher 쿼리 실행
- `PodcastReasoningAgent`에 실제 Knowledge Agent를 DI로 주입
- 워크플로우에서 Stub 대신 실제 에이전트를 연결

### 3-4. 초기 데이터 적재

빈 Neo4j에는 쿼리할 데이터가 없다. 다음 노드/관계가 필요하다:

```
노드 5종: User, Session, Emotion, Topic, GoTNode
관계 9종: HAS_SESSION, SHOWS_PATTERN, PRODUCED_EPISODE, COVERS,
         ADDRESSED, OFTEN_COOCCURS, RELATED_TO, LEADS_TO, REASONED_BY
```

초기 데이터 소스:
- **Emotion / Topic**: 미리 정의된 마스터 데이터 (정적)
- **User / Session**: MySQL과 동기화 필요 (mysql_id 참조)
- **GoTNode**: 파이프라인 실행 시 동적 생성

### 3-5. 환경변수 및 Docker 설정

```bash
# .env에 추가 필요
NEO4J_URL=bolt://<neo4j-host>:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secure-password>
```

`docker-compose.yml`에서 Neo4j 서비스 주석 해제 및 `depends_on` 활성화.

---

## 4. STORAGE_MODE별 시나리오 분석

### 시나리오 A: `local` / `hybrid` 모드 — AI서버에서 직접 접속

```
┌──────────────────────────────────────────────┐
│  app-2 (AI서버, EC2 t3.medium)               │
│  ┌─────────────┐    ┌──────────────────────┐ │
│  │ AI Service  │───▶│ Neo4j (같은 인스턴스) │ │
│  │ :8000       │bolt│ :7687                │ │
│  │ mem: 2GB    │    │ mem: ~1GB            │ │
│  └─────────────┘    └──────────────────────┘ │
│  총 메모리 요구: ~3GB+ (인스턴스 4GB)         │
└──────────────────────────────────────────────┘
```

**장점**: Backend팀 의존성 없음, 즉시 사용 가능
**단점**: 메모리 부족 위험 (섹션 5 참조), 보안(AI서버가 DB 직접 접근)

### 시나리오 B: `proxy` 모드 — Backend API 경유

```
┌─────────────┐  REST  ┌─────────────┐  bolt  ┌────────┐
│ AI Service  │───────▶│ Backend     │───────▶│ Neo4j  │
│ app-2:8000  │        │ app-3:8080  │        │ app-?  │
└─────────────┘        └─────────────┘        └────────┘
```

**장점**: DB 접근 중앙 관리, AI서버 메모리 부담 없음
**단점**: Backend팀의 `POST /api/v1/graph/query` 구현 필요, 레이턴시 증가

### 시나리오 C: 별도 인스턴스에 Neo4j 설치

```
┌─────────────┐  bolt  ┌──────────────────┐
│ AI Service  │───────▶│ Neo4j 전용 서버   │
│ app-2:8000  │        │ 별도 EC2 / AuraDB │
└─────────────┘        └──────────────────┘
```

**장점**: 메모리 격리, 확장 용이
**단점**: 추가 비용, 네트워크 설정 필요

---

## 5. EC2 메모리 제약 분석

현재 app-2 (AI서버): **EC2 t3.medium = 4GB RAM**

| 프로세스 | 메모리 |
|---------|--------|
| AI Service (FastAPI + LLM 파이프라인) | 2GB (docker-compose.yml `mem_limit`) |
| OS + Docker 오버헤드 | ~500MB |
| **남은 여유** | **~1.5GB** |

| Neo4j 설정 (docker-compose.yml 주석 내용) | 메모리 |
|------------------------------------------|--------|
| heap_initial_size | 256MB |
| heap_max_size | 512MB |
| pagecache_size | 256MB |
| OS 내 JVM 오버헤드 | ~200MB |
| **Neo4j 총 예상** | **~1GB ~ 1.2GB** |

**결론**: 같은 인스턴스에 설치하면 4GB 중 ~3.5GB+ 사용 → **OOM 위험 높음.**
현재 docker-compose.yml 주석에도 "EC2 t3.medium(4GB) OOM 방지 — Neo4j 비활성화 중"이라고 명시되어 있다.

### 메모리 해결 방안

| 방안 | 실현성 | 비고 |
|------|--------|------|
| 인스턴스 업그레이드 (t3.large = 8GB) | 비용 증가 | 가장 단순한 해결책 |
| Neo4j 전용 인스턴스 분리 | 비용 증가 | 운영 복잡도 증가 |
| Neo4j AuraDB (매니지드) | 월 비용 | 운영 부담 최소 |
| AI서버 메모리 줄이기 (2GB → 1.5GB) | 위험 | LLM 파이프라인 OOM 가능성 |
| `proxy` 모드로 app-3에 Neo4j 배치 | 추가 비용 없음 | Backend팀 구현 필요 + app-3 메모리 여유 확인 필요 |

---

## 6. 작업 체크리스트

### 인프라 (Neo4j 설치 관련)

- [ ] Neo4j 설치 위치 결정 (같은 인스턴스 / 별도 인스턴스 / AuraDB)
- [ ] 메모리 확보 방안 결정 (인스턴스 업그레이드 또는 분리)
- [ ] Neo4j 5 Community 설치 (Docker 또는 네이티브)
- [ ] 인증 비밀번호 설정 및 환경변수 등록
- [ ] 네트워크 접근 제어 (7687 포트, AI서버에서만 접근 허용)
- [ ] `docker-compose.yml` Neo4j 서비스 주석 해제

### 스키마 및 데이터

- [ ] `init.cypher` 실행 (제약 5개 + 인덱스 6개 생성)
- [ ] Emotion / Topic 마스터 데이터 적재
- [ ] MySQL ↔ Neo4j 사용자/세션 동기화 방안 결정

### 코드 통합

- [ ] `STORAGE_MODE` 결정 (`local`/`hybrid`/`proxy`)
- [ ] `proxy` 선택 시: Backend팀에 `POST /api/v1/graph/query` 엔드포인트 요청
- [ ] Knowledge Agent(개발자1) 실제 구현 — Neo4j Cypher 쿼리 포함
- [ ] `PodcastReasoningAgent`에 실제 Knowledge Agent DI 연결
- [ ] Stub 제거 또는 폴백 전환

### 검증

- [ ] `dev/local_db/test_neo4j_integration.py` 전체 통과 확인
- [ ] `dev/local_db/test_factory_crossdb.py` MySQL ↔ Neo4j 일관성 검증
- [ ] E2E 파이프라인에서 Knowledge Agent 결과가 Reasoning에 반영되는지 확인
- [ ] OOM 없이 안정 운영되는지 모니터링 (최소 24시간)

---

## 7. 권장 배포 순서

```
Phase 1 — 결정
  ├─ STORAGE_MODE 결정 (local vs proxy vs hybrid)
  ├─ Neo4j 배치 위치 결정 (같은 인스턴스 vs 분리)
  └─ 메모리 확보 방안 확정

Phase 2 — 인프라
  ├─ Neo4j 설치 + 인증 설정
  ├─ init.cypher 실행 (스키마 생성)
  ├─ 환경변수 등록 (.env)
  └─ docker-compose.yml 수정

Phase 3 — 코드 통합
  ├─ Knowledge Agent 실제 구현 (개발자1)
  ├─ PodcastReasoning에 DI 연결 (개발자3)
  ├─ (proxy 모드 시) Backend 엔드포인트 구현 요청
  └─ 마스터 데이터 적재

Phase 4 — 검증
  ├─ 통합 테스트 실행
  ├─ E2E 파이프라인 테스트
  └─ 메모리/안정성 모니터링
```

---

## 요약

| 질문 | 답변 |
|------|------|
| Neo4j 설치만 하면 되나? | **아니오** |
| 설치로 해결되는 것 | Bolt 연결 가능성만 확보 |
| 추가 필요: 인프라 | 메모리 확보, 스키마 초기화, 환경변수 |
| 추가 필요: 코드 | Knowledge Agent 실제 구현, Stub 교체, STORAGE_MODE 결정 |
| 추가 필요: 협의 | Backend팀 (proxy 모드 시), 인프라팀 (인스턴스 업그레이드 시) |
| 가장 큰 블로커 | EC2 메모리 부족 (4GB 중 여유 ~1.5GB, Neo4j 최소 ~1GB) |

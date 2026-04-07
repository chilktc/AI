# Neo4j 통합 명세서

> **작성일**: 2026-04-07
> **대상**: AI팀 · Backend팀 · 인프라팀
> **버전**: v1.3
> **담당**: 개발자3 (AI팀)

---

## 목차

1. [Neo4j가 이 프로젝트에서 하는 일](#1-neo4j가-이-프로젝트에서-하는-일)
2. [전체 워크플로우 — 데이터는 어디서 어디로 흐르는가](#2-전체-워크플로우--데이터는-어디서-어디로-흐르는가)
3. [그래프 데이터 모델 (Neo4j에 저장되는 것)](#3-그래프-데이터-모델-neo4j에-저장되는-것)
4. [DB 접근 구조](#4-db-접근-구조)
5. [현재 구현 현황](#5-현재-구현-현황)
6. [누적 데이터와 RDB — Backend팀 협업 포인트](#6-누적-데이터와-rdb--backend팀-협업-포인트)
7. [팀별 역할 및 담당 작업](#7-팀별-역할-및-담당-작업)
8. [협업 작업 순서 (Phase별)](#8-협업-작업-순서-phase별)
9. [차후 계획 — 조직 단위 분석 확장](#9-차후-계획--조직-단위-분석-확장)
10. [설정·환경변수·테스트](#10-설정환경변수테스트)
11. [부록: STORAGE_MODE 참고](#11-부록-storage_mode-참고)

---

## 1. Neo4j가 이 프로젝트에서 하는 일

### 1-1. 한 줄 요약

> 사용자가 상담을 하면, AI가 **"이 사람의 고민은 이런 것들이 서로 연결되어 있다"** 라는
> 추론 그래프(Graph of Thoughts, GoT)를 만든다. 이 그래프를 **Neo4j에 저장**하고,
> 시간이 지나면서 **누적된 패턴을 Backend의 MySQL(RDB)에도 쌓아** 프론트엔드에서 시각화한다.

### 1-2. 왜 Neo4j가 필요한가?

이 프로젝트에는 두 종류의 데이터베이스가 있다:

| DB | 역할 | 비유 |
|----|------|------|
| **MySQL (RDB)** | 사용자 정보, 에피소드 기록, 누적 통계 저장 | "가계부" — 모든 거래를 빠짐없이 기록 |
| **Neo4j (그래프 DB)** | 감정·주제 간의 **관계**를 저장하고 탐색 | "마인드맵" — 생각들이 어떻게 이어지는지 시각화 |

MySQL은 "A 사용자가 3월 5일에 번아웃 에피소드를 들었다"는 사실을 기록하기 좋지만,
"이 사람의 번아웃은 리더십 문제에서 시작해서 동료 갈등으로 이어지고, 결국 감정 소진에 도달한다"
같은 **관계의 흐름**을 표현하고 탐색하기에는 그래프 DB가 훨씬 적합하다.

### 1-3. 실제 예시 — 사용자의 상담이 그래프가 되기까지

```
사용자 입력: "요즘 팀장이 회의에서 자꾸 내 의견을 무시해서 출근하기 싫어요"

   ┌────────────────────────────────────────────────────┐
   │  AI 추론 (Graph of Thoughts)                       │
   │                                                    │
   │  [의견 무시] ──LEADS_TO──▶ [자존감 하락]            │
   │       │                        │                   │
   │       │                   LEADS_TO                 │
   │       │                        ▼                   │
   │  LEADS_TO              [출근 거부감]                │
   │       │                        │                   │
   │       ▼                   LEADS_TO                 │
   │  [리더십 불신] ──LEADS_TO──▶ [번아웃 위험]          │
   │                                                    │
   │  group: leadership     group: emotional_exhaustion │
   └────────────────────────────────────────────────────┘

이 그래프가 Neo4j에 저장되고,
"leadership" 카테고리와 "emotional_exhaustion" 카테고리의
연결 빈도가 RDB에 누적된다.
```

---

## 2. 전체 워크플로우 — 데이터는 어디서 어디로 흐르는가

### 2-1. 에피소드 생성 시 (쓰기 흐름)

사용자가 상담을 하면 아래 순서로 데이터가 흐른다:

```
사용자 입력 ("직장에서 번아웃이 심해요")
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  TIER 0: Intent Classifier                              │
│  → "이 사용자는 팟캐스트 모드로 상담을 원한다"           │
│  → complexity_score = 0.75 (복잡도 높음)                │
└──────────────────────┬──────────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────────┐
    │   TIER 1 (4개 에이전트가 동시에 실행)     │
    │                  │                       │
    │  ┌───────┐ ┌────────┐ ┌──────────────────────────────────────┐
    │  │Safety │ │Emotion │ │ Podcast Reasoning                    │
    │  │Agent  │ │Agent   │ │                                      │
    │  └───────┘ └────────┘ │  1단계: GoT (관계 그래프 구축)        │
    │                       │     "번아웃 ← 리더십 문제 ← 의견무시" │
    │                       │                                      │
    │                       │  2단계: ToT (대안 구조 탐색)          │
    │                       │     "이 문제를 어떤 각도에서 풀까?"   │
    │                       │                                      │
    │                       │  3단계: CoT (최종 상세화)             │
    │                       │     "에피소드 내러티브 구성"          │
    │                       └──────────────┬───────────────────────┘
    │                                      │
    └──────────────────────────────────────┘
                       │
                       │  GoT 추론 완료 후, 3곳에 저장:
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────────┐
    │ ① Neo4j  │ │ ② Backend│ │ ③ RDB 누적 저장   │
    │ 그래프   │ │ 그래프   │ │ (EMA 계산 후      │
    │ 직접 저장│ │ 데이터   │ │  Backend에 전송)  │
    │          │ │ 전송     │ │                   │
    └──────────┘ └──────────┘ └──────────────────┘
     GoTNode를     변환된 JSON    시간이 지나도
     노드/엣지로    프론트엔드     패턴이 유지되도록
     MERGE         시각화용       가중치를 EMA로 갱신
```

**① Neo4j 직접 저장** — GoT 노드와 연결 관계를 그래프 DB에 저장한다.
이후 "이 사용자의 전체 마인드맵"을 조회할 때 사용된다.

**② Backend 전송** — GoT 결과를 프론트엔드가 이해하는 형식 `{ nodes, links }` 으로
변환하여 Backend 서버에 보낸다. 프론트엔드에서 즉시 시각화에 사용된다.

**③ RDB 누적 저장** — 과거 에피소드의 패턴과 현재 에피소드의 패턴을 합산(EMA)하여
Backend의 MySQL에 저장한다. 누적 통계·카테고리 분포 등에 사용된다.

> **중요**: ①은 Neo4j가 없으면 실패하지만, **파이프라인은 계속 진행**된다.
> ②③은 Neo4j와 무관하게 항상 동작한다.

### 2-2. 누적 그래프 조회 시 (읽기 흐름)

프론트엔드에서 "이 사용자의 감정 패턴 그래프"를 보여줄 때:

```
프론트엔드 (app-4:3000)
    │
    │  "사용자 A의 감정 패턴 보여줘"
    │  GET /api/v1/graph/users/{user_id}/data
    ▼
Backend 서버 (app-3:8080)
    │
    │  MySQL(RDB)에 이미 누적 저장된 데이터를 조회
    │  → graph_nodes, graph_edges 테이블에서 SELECT
    ▼
{
  "nodes": [
    { "label": "의견 무시", "group": "leadership", "weight": 0.69, "mention_count": 3 },
    { "label": "번아웃",   "group": "emotional_exhaustion", "weight": 0.81, "mention_count": 5 }
  ],
  "edges": [
    { "source_label": "의견 무시", "target_label": "번아웃", "weight": 4 }
  ],
  "category_distribution": { "leadership": 15, "emotional_exhaustion": 23, ... }
}
```

**핵심: 프론트엔드 조회 시 AI서버(Neo4j)를 거치지 않는다.**

누적 데이터는 쓰기 흐름(2-1)의 ③단계에서 이미 Backend의 MySQL에 저장되었다.
프론트엔드는 **Backend의 RDB에서 바로 조회**하면 된다.
AI서버의 Neo4j는 파이프라인 실행(쓰기) 시에만 사용된다.

> **참고**: 현재 AI서버에 `src/api/routes/graph.py` 라우트가 있다.
> 이것은 Neo4j에서 직접 Cypher 쿼리를 실행하는 조회 API인데,
> 누적 데이터가 RDB에 저장되는 구조에서는 **불필요**하다.
> Backend팀이 RDB 조회 API를 구현하면 이 라우트는 삭제 대상이다.
> (코드에도 "Neo4j를 Backend로 이관 시 이 라우터 전체를 삭제한다"라는 주석이 있다.)

---

## 3. 그래프 데이터 모델 (Neo4j에 저장되는 것)

### 3-1. 노드 (Node) — 5종류

노드란 그래프에서 **점(동그라미)** 에 해당하는 것이다.
각 노드는 고유한 ID를 가지며, 여러 속성(이름, 분류 등)을 담고 있다.

| 레이블 | 뜻 | 고유 키 | 주요 속성 | 예시 |
|--------|-----|---------|----------|------|
| **:User** | 사용자 | `user_id` | `mysql_id`, `display_name` | `{user_id: "u_001", display_name: "김철수"}` |
| **:Session** | 상담 세션 | `session_id` | `mysql_id`, `mode` | `{session_id: "sess_abc", mode: "podcast"}` |
| **:Emotion** | 감정 | `emotion_key` | `emotion_kr`, `category` | `{emotion_key: "burnout", emotion_kr: "번아웃", category: "negative"}` |
| **:Topic** | 주제 | `topic_name` | `domain` | `{topic_name: "leadership", domain: "work"}` |
| **:GoTNode** | AI 추론 노드 | `got_node_id` | `label`, `weight`, `group`, `episode_id` | `{label: "의견 무시", group: "leadership", weight: 0.8}` |

> **mysql_id**: 모든 노드에는 `mysql_id`라는 속성이 있다.
> 이것은 MySQL에 저장된 같은 데이터의 Primary Key를 가리킨다.
> **MySQL이 원본**이고, Neo4j는 관계 탐색용 복사본이다.

### 3-2. 관계 (Relationship) — 9종류

관계란 그래프에서 **선(화살표)** 에 해당하는 것이다.
"A → B" 처럼 방향이 있으며, 선 위에 추가 정보(weight, count 등)를 달 수 있다.

| 관계 이름 | 방향 | 뜻 | 속성 | 예시 |
|----------|-----|-----|------|------|
| **HAS_SESSION** | User → Session | "이 사용자가 이 세션을 가짐" | — | `(김철수)-[:HAS_SESSION]->(3월5일_세션)` |
| **SHOWS_PATTERN** | User → EmotionPattern | "이 사용자가 이런 감정 패턴을 보임" | — | |
| **PRODUCED_EPISODE** | Session → Episode | "이 세션에서 이 에피소드가 생성됨" | — | |
| **COVERS** | Episode → Topic | "이 에피소드가 이 주제를 다룸" | — | `(ep_001)-[:COVERS]->(leadership)` |
| **ADDRESSED** | Episode → Emotion | "이 에피소드가 이 감정을 다룸" | — | `(ep_001)-[:ADDRESSED]->(burnout)` |
| **OFTEN_COOCCURS** | Emotion → Emotion | "이 두 감정이 자주 같이 나타남" | `count` | `(불안)-[:OFTEN_COOCCURS {count: 7}]->(번아웃)` |
| **RELATED_TO** | Topic → Topic | "이 두 주제가 연관됨" | `weight` | `(leadership)-[:RELATED_TO {weight: 0.9}]->(peer_relations)` |
| **LEADS_TO** | GoTNode → GoTNode | "이 생각이 저 생각으로 이어짐" | `weight`, `relation_type` | `(의견무시)-[:LEADS_TO]->(자존감하락)` |
| **REASONED_BY** | Session → GoTNode | "이 세션의 추론 그래프" | — | `(sess_abc)-[:REASONED_BY]->(의견무시)` |

### 3-3. GoT 노드의 group 분류 — 6개 카테고리

GoTNode의 `group` 속성은 아래 6개 중 하나여야 한다.
이 값이 프론트엔드에서 **그래프 노드의 색상 구분**과 **카테고리별 통계**에 직접 사용된다.

| group 값 | 뜻 | 대표 키워드 |
|----------|-----|-----------|
| `work_structure` | 업무 구조 문제 | 과부하, 야근, 병목, 독박 |
| `leadership` | 리더십/상사 문제 | 상사, 압박, 과잉간섭, 권위 |
| `peer_relations` | 동료 관계 문제 | 신뢰, 갈등, 소통단절, 뒷담화 |
| `career_growth` | 커리어 성장 고민 | 성장정체, 가면증후군, 역량불안 |
| `culture_system` | 조직문화/시스템 | 보상, 불공정, 복지, 연차 |
| `emotional_exhaustion` | 감정 소진 (기본값) | 번아웃, 우울, 고립, 불안 |

> LLM이 잘못된 group 값을 출력하면, 코드가 **label 텍스트에서 키워드를 찾아 자동 보정**한다.
> 어디에도 해당하지 않으면 `emotional_exhaustion` (감정 소진)으로 분류한다.
> 관련 코드: `src/api/graph_transformer.py` — `validate_group()`

### 3-4. 스키마 DDL (데이터베이스 초기 설정)

Neo4j를 처음 실행한 후 반드시 아래 DDL을 실행해야 한다.
이 DDL은 **고유 키 제약(Constraint)** 과 **검색 인덱스** 를 생성한다.

**파일 위치**: `dev/local_db/neo4j/init.cypher`

```cypher
-- 제약(Constraint) 5개: 같은 ID의 노드가 중복 생성되지 않도록 보장
CREATE CONSTRAINT user_id_unique    FOR (u:User)    REQUIRE u.user_id IS UNIQUE;
CREATE CONSTRAINT session_id_unique FOR (s:Session) REQUIRE s.session_id IS UNIQUE;
CREATE CONSTRAINT emotion_key_unique FOR (e:Emotion) REQUIRE e.emotion_key IS UNIQUE;
CREATE CONSTRAINT topic_name_unique FOR (t:Topic)   REQUIRE t.topic_name IS UNIQUE;
CREATE CONSTRAINT got_node_id_unique FOR (g:GoTNode) REQUIRE g.got_node_id IS UNIQUE;

-- 인덱스(Index) 7개: 검색 속도를 높이기 위한 색인
CREATE INDEX user_mysql_id  FOR (u:User)    ON (u.mysql_id);
CREATE INDEX session_mode   FOR (s:Session) ON (s.mode);
CREATE INDEX emotion_category FOR (e:Emotion) ON (e.category);
CREATE INDEX topic_domain   FOR (t:Topic)   ON (t.domain);
CREATE INDEX got_episode    FOR (g:GoTNode) ON (g.episode_id);
CREATE INDEX got_node_type  FOR (g:GoTNode) ON (g.node_type);
CREATE INDEX got_group      FOR (g:GoTNode) ON (g.group);
```

---

## 4. DB 접근 구조

AI서버(app-2)가 각 데이터베이스에 접근하는 방식은 다음과 같다:

```
AI 서버 (app-2)
├──bolt──▶ Neo4j      (직접 접속)
├──https─▶ Pinecone   (직접 접속)
├──https─▶ S3         (직접 접속)
│
└──REST──▶ Backend 서버 (app-3)
           └──▶ MySQL  (Backend가 관리)
```

| DB | 접근 방식 | 이유 |
|----|---------|------|
| **Neo4j** | AI서버가 **직접** Bolt 연결 | 파이프라인에서 Cypher 쿼리를 직접 실행해야 함 |
| **Pinecone** | AI서버가 **직접** 접속 | 벡터 검색은 AI 파이프라인의 핵심 기능 |
| **S3** | AI서버가 **직접** 접속 | 이미지 업로드 |
| **MySQL** | **Backend API** 경유 | 사용자/에피소드 등 핵심 데이터는 Backend가 관리. AI서버가 직접 쓰면 안 됨 |
| **누적 데이터** | AI서버가 EMA 계산 후 **Backend API로 전송** | MySQL에 직접 쓰지 않고 Backend를 거침 |

### 4-1. Neo4j 접속에 필요한 환경변수

```bash
NEO4J_URL=bolt://<neo4j-host>:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
```

### 4-2. 코드에서 Neo4j 클라이언트를 사용하는 방법

```python
# src/db/factory.py — Neo4j 클라이언트 생성
from src.db.neo4j_client import Neo4jClient

async with create_graph_client() as client:
    # Cypher 쿼리를 직접 실행
    result = await client.execute_query(
        "MATCH (g:GoTNode {episode_id: $eid}) RETURN g",
        params={"eid": "ep_001"}
    )
```

> **참고**: 코드 내부에 `STORAGE_MODE` 환경변수에 따라 클라이언트를 선택하는
> 팩토리 패턴(`src/db/factory.py`)이 있다. 모드별 상세는 [부록](#11-부록-storage_mode-참고)을 참고.

---

## 5. 현재 구현 현황

### 5-1. 완료된 것

| 구분 | 항목 | 파일 | 설명 |
|------|------|------|------|
| **DB 접속** | Neo4j 비동기 클라이언트 | `src/db/neo4j_client.py` | Bolt 프로토콜로 Neo4j에 직접 접속 |
| **DB 접속** | 추상 인터페이스 | `src/db/base.py` | 모든 클라이언트의 공통 규격 |
| **DB 접속** | 팩토리 패턴 | `src/db/factory.py` | STORAGE_MODE에 따라 클라이언트 자동 선택 |
| **DB 접속** | Backend 프록시 | `src/db/api_proxy.py` | 미사용 ([부록](#11-부록-storage_mode-참고) 참고) |
| **스키마** | DDL 스크립트 | `dev/local_db/neo4j/init.cypher` | 제약 5개 + 인덱스 7개 |
| **저장** | GoT → Neo4j 저장 | `podcast_reasoning.py` | GoTNode MERGE + LEADS_TO 관계 생성 |
| **저장** | GoT → Backend 전송 | `podcast_reasoning.py` | 변환된 JSON을 Backend에 POST |
| **저장** | GoT → Backend 에피소드 전송 | `src/api/graph_cumulative.py` | group 검증 후 POST (EMA는 Backend가 수행) |
| **변환** | GoT → 프론트엔드 JSON | `src/api/graph_transformer.py` | group 검증 + intensity → val 변환 |
| **조회** | 사용자 그래프 조회 API | `src/api/routes/graph.py` | Cypher 쿼리 3개 실행 **(이관 후 삭제 예정)** |
| **테스트** | 통합 테스트 | `dev/local_db/test_neo4j_integration.py` | Neo4j 연결 + 쿼리 검증 |
| **테스트** | 누적 그래프 단위 테스트 | `tests/api/test_graph_cumulative.py` | EMA 계산, 노드 병합 로직 |
| **테스트** | 조회 API 테스트 | `tests/api/test_graph_routes.py` | 응답 형식 검증 |
| **설정** | Neo4j 설정 | `config/settings.yaml` | URI, upsert_mode, ema_alpha |
| **로컬** | 개발용 Docker | `dev/local_db/docker-compose.db.yml` | Neo4j 5 Community 컨테이너 |

### 5-2. 미완료 / 차후 작업

| 항목 | 현재 상태 | 필요 작업 | 누가 |
|------|---------|---------|------|
| **프로덕션 Neo4j** | 주석 처리 (docker-compose.yml) | 인스턴스 배포 + 주석 해제 | 인프라팀 |
| **Knowledge Agent** | Stub (항상 빈 결과) | 실제 Neo4j 쿼리 구현 | 개발자3 (Pinecone 연동과 함께 차후) |
| **Emotion/Topic 초기 데이터** | ✅ seed_data.json에 포함 (Emotion 4개, Topic 3개) | 프로덕션 적재 시 실행 | 개발자3 |
| **GoTNode 시드 데이터 group 필드** | ✅ seed_data.json 3개 노드에 추가 완료 | — | — |
| **Backend 누적 데이터 조회 API** | 미구현 | 프론트엔드 그래프 시각화용 | Backend팀 |
| **MySQL ↔ Neo4j 동기화** | 미구현 | mysql_id 기반 MERGE 로직 | 개발자3 + Backend팀 |

### 5-3. 파일 구조

```
src/db/                          ← Neo4j 접속 계층
├── base.py                      ← 추상 인터페이스 (BaseGraphClient)
├── neo4j_client.py              ← Neo4j 직접 접속
├── api_proxy.py                 ← 미사용 (부록 참고)
└── factory.py                   ← 클라이언트 생성 팩토리

src/api/                         ← Neo4j 데이터 가공/전송
├── graph_cumulative.py          ← 누적 그래프 EMA 계산 + RDB 저장
├── graph_transformer.py         ← GoT → 프론트엔드 JSON 변환
├── routes/graph.py              ← 그래프 조회 API (이관 후 삭제 예정)
├── backend_resources.py         ← 리소스 경로 상수
└── external_schemas.py          ← Pydantic 스키마

src/agents/podcast/              ← GoT 생성 + 저장 에이전트
└── podcast_reasoning.py         ← _save_got_to_neo4j() + _publish_graph_to_backend()

dev/local_db/                    ← 로컬 개발 환경
├── neo4j/init.cypher            ← 스키마 DDL
├── docker-compose.db.yml        ← 개발용 Neo4j + MySQL
├── seed.py                      ← 시드 데이터 적재
└── test_neo4j_integration.py    ← 통합 테스트
```

---

## 6. 누적 데이터와 RDB — Backend팀 협업 포인트

### 6-1. 누적 데이터란?

사용자가 상담을 여러 번 하면, 매번 새로운 GoT 그래프가 생긴다.
이 그래프들을 **합산(누적)** 하면 "이 사용자가 반복적으로 겪는 패턴"이 드러난다.

```
에피소드 1: [리더십 문제] → [번아웃]              (leadership: 0.8)
에피소드 2: [동료 갈등] → [고립감]                (peer_relations: 0.7)
에피소드 3: [리더십 문제] → [자존감 하락] → [번아웃] (leadership: 0.9)
                                   ↓
                            ┌─────────────────────┐
                            │  누적 데이터 (RDB)   │
                            │                     │
                            │  leadership: 0.87   │ ← 반복 출현 → 가중치 높음
                            │  emotional_exhaust: 0.6 │
                            │  peer_relations: 0.5│
                            └─────────────────────┘
```

### 6-2. EMA (지수이동평균) — 가중치 계산 방법

누적할 때 단순 평균 대신 **EMA(Exponential Moving Average)** 를 사용한다.
EMA는 **최근 값에 더 큰 비중**을 주는 계산 방식이다.

```
공식:   새 가중치 = α × 최근값 + (1 - α) × 기존값

α(alpha) = 0.3 (config/settings.yaml에서 설정)

예시:
  기존 leadership 가중치: 0.6
  이번 에피소드의 leadership 강도: 0.9

  새 가중치 = 0.3 × 0.9 + 0.7 × 0.6
           = 0.27 + 0.42
           = 0.69

  → 기존 0.6에서 0.69로 올라감. 단순히 0.9로 덮어쓰지 않고,
    과거와 현재를 적절히 섞어서 급격한 변화를 방지함.
```

### 6-3. RDB 누적 저장 흐름

AI 서버는 GoT 결과를 group 검증 후 Backend에 POST한다.
EMA 계산과 UPSERT는 Backend가 수행한다.

```
AI 서버 (app-2)                            Backend (app-3)
┌──────────────────────────────────┐       ┌──────────────────────┐
│ 1. group 검증                    │       │ 1. 기존 누적 데이터 조회 │
│    (VALID_GROUPS 6개 체크)        │──POST─▶│ 2. EMA 계산           │
│ 2. GoT 결과를 그대로 전송         │       │    α=0.3 (설정 가능)  │
│    (계산 없음)                    │       │ 3. MySQL UPSERT       │
└──────────────────────────────────┘       └──────────────────────┘
```

AI서버 참조 코드: `src/api/graph_cumulative.py` — `publish_graph_to_rdb()`

### 6-4. RDB 테이블 스키마 (Backend팀 구현 대상)

현재 `dev/local_db/mysql/init.sql`에는 그래프 누적 테이블이 **없다**.
Backend팀이 아래 2개 테이블을 생성해야 한다.

#### `user_graph_nodes` — 누적 노드

사용자별로 반복 등장하는 개념(label)과 카테고리(grp)를 누적 저장한다.
같은 사용자 + 같은 label + 같은 grp 조합은 **하나의 행**이다 (UPSERT).

```sql
CREATE TABLE user_graph_nodes (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(36)  NOT NULL,

    -- 노드 식별 (label + grp 조합이 사용자 내에서 유니크)
    label           VARCHAR(200) NOT NULL,   -- GoT 노드 텍스트 (예: "업무과부하", "번아웃")
    grp             VARCHAR(50)  NOT NULL,   -- 6개 카테고리 중 하나 (예: "work_structure")

    -- 누적 통계
    weight          FLOAT        NOT NULL DEFAULT 0.5,   -- EMA 가중치 (0.0~1.0)
    mention_count   INT          NOT NULL DEFAULT 1,     -- 등장 횟수
    trend           VARCHAR(20)  NOT NULL DEFAULT 'stable', -- increasing / stable / decreasing

    -- 시간 추적
    first_seen      DATETIME     NOT NULL,   -- 최초 등장 시각
    last_seen       DATETIME     NOT NULL,   -- 최근 등장 시각

    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_user_label_grp (user_id, label, grp),
    INDEX idx_user_id (user_id),
    INDEX idx_user_grp (user_id, grp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**grp 허용값** (6개):
`work_structure`, `leadership`, `peer_relations`, `career_growth`, `culture_system`, `emotional_exhaustion`

#### `user_graph_edges` — 누적 엣지

사용자별로 개념 간 연결(A→B)이 반복 등장한 횟수를 누적한다.

```sql
CREATE TABLE user_graph_edges (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(36)  NOT NULL,

    -- 엣지 식별
    source_label    VARCHAR(200) NOT NULL,   -- 출발 노드 label
    source_grp      VARCHAR(50)  NOT NULL,   -- 출발 노드 grp
    target_label    VARCHAR(200) NOT NULL,   -- 도착 노드 label
    target_grp      VARCHAR(50)  NOT NULL,   -- 도착 노드 grp

    -- 누적 통계
    weight          INT          NOT NULL DEFAULT 1,     -- 연결 반복 횟수
    relationship    VARCHAR(100) NOT NULL DEFAULT 'related',

    -- 시간 추적
    first_seen      DATETIME     NOT NULL,
    last_seen       DATETIME     NOT NULL,

    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_user_edge (user_id, source_label, source_grp, target_label, target_grp),
    INDEX idx_user_id (user_id),
    CONSTRAINT chk_not_self_loop CHECK (
        NOT (source_label = target_label AND source_grp = target_grp)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **self-loop 방지**: "번아웃 → 번아웃" 같은 자기 자신 연결은 CHECK 제약으로 차단한다.
> AI서버에서도 group 검증 시 self-loop를 필터링하지만, DB에서도 이중 방어한다.

#### Backend 구현 가이드

AI서버가 GoT 결과를 **원본 그대로** 보낸다.
Backend가 **EMA 계산 + UPSERT를 모두 수행**해야 한다.

**엔드포인트**: `POST /api/v1/graph_nodes/episodes`

**AI서버가 보내는 요청 body:**

```json
{
  "user_id": "u_001",
  "type": "graph_episode",
  "data": {
    "episode_id": "ep_20260407_001",
    "got_result": {
      "nodes": [
        {
          "id": "1",
          "label": "업무과부하",
          "group": "work_structure",
          "intensity": 0.9
        },
        {
          "id": "2",
          "label": "번아웃",
          "group": "emotional_exhaustion",
          "intensity": 0.85
        }
      ],
      "edges": [
        {
          "from": "1",
          "to": "2",
          "relationship": "causes"
        }
      ]
    }
  }
}
```

> AI서버의 노드: `group`, `intensity` (이번 에피소드의 원본 값). EMA 계산은 Backend가 수행한다.

---

**Step 1 — 노드 처리: EMA 계산 + UPSERT**

`data.got_result.nodes` 배열의 각 노드에 대해 아래 쿼리를 실행한다.

```sql
-- 1-1. 기존 행 조회
SELECT weight, mention_count
FROM user_graph_nodes
WHERE user_id = :user_id AND label = :label AND grp = :grp
FOR UPDATE;
```

결과가 **있으면 (기존 노드)** — EMA 계산 후 UPDATE:

```sql
-- 1-2a. EMA 계산 (애플리케이션에서 수행)
--
--   alpha = 0.3
--   new_weight = alpha * intensity + (1 - alpha) * old_weight
--   new_weight = LEAST(1.0, GREATEST(0.0, new_weight))   -- 0.0~1.0 클램핑
--
--   trend 판정:
--     (new_weight - old_weight) >  0.05 → 'increasing'
--     (new_weight - old_weight) < -0.05 → 'decreasing'
--     그 외                              → 'stable'
--
-- 예시: old_weight=0.6, intensity=0.9
--   new_weight = 0.3 * 0.9 + 0.7 * 0.6 = 0.69
--   diff = 0.69 - 0.6 = 0.09 > 0.05 → trend = 'increasing'

UPDATE user_graph_nodes
SET weight        = :new_weight,       -- EMA 계산 결과
    mention_count = mention_count + 1,
    trend         = :trend,            -- 'increasing' / 'stable' / 'decreasing'
    last_seen     = NOW()
WHERE user_id = :user_id AND label = :label AND grp = :grp;
```

결과가 **없으면 (신규 노드)** — INSERT:

```sql
-- 1-2b. 최초 등장 시 intensity를 weight로 그대로 사용
INSERT INTO user_graph_nodes (user_id, label, grp, weight, mention_count, trend, first_seen, last_seen)
VALUES (:user_id, :label, :grp, :intensity, 1, 'stable', NOW(), NOW());
```

> 위 3개 쿼리를 하나의 트랜잭션으로 묶는 것을 권장한다.
> 또는 아래처럼 단일 UPSERT 쿼리로도 가능하다:

```sql
-- 1-3. 단일 UPSERT (EMA를 SQL에서 직접 계산하는 방식)
INSERT INTO user_graph_nodes (user_id, label, grp, weight, mention_count, trend, first_seen, last_seen)
VALUES (:user_id, :label, :grp, :intensity, 1, 'stable', NOW(), NOW())
ON DUPLICATE KEY UPDATE
    weight        = LEAST(1.0, GREATEST(0.0,
                      0.3 * :intensity + 0.7 * weight
                    )),
    mention_count = mention_count + 1,
    trend         = CASE
                      WHEN (0.3 * :intensity + 0.7 * weight) - weight >  0.05 THEN 'increasing'
                      WHEN (0.3 * :intensity + 0.7 * weight) - weight < -0.05 THEN 'decreasing'
                      ELSE 'stable'
                    END,
    last_seen     = NOW();
```

---

**Step 2 — 엣지 처리: ID → label 변환 + UPSERT**

`data.got_result.edges` 배열의 각 엣지를 처리한다.
엣지의 `from`/`to`는 노드의 `id`이므로, **먼저 nodes 배열에서 label과 group을 찾아야 한다.**

```
엣지 예시: { "from": "1", "to": "2", "relationship": "causes" }

nodes 배열에서:
  id "1" → label: "업무과부하", group: "work_structure"
  id "2" → label: "번아웃",    group: "emotional_exhaustion"

→ source_label = "업무과부하", source_grp = "work_structure"
  target_label = "번아웃",    target_grp = "emotional_exhaustion"
```

**self-loop 확인** — `source_label = target_label AND source_grp = target_grp` 이면 건너뛴다.

```sql
-- 2-1. 엣지 UPSERT
INSERT INTO user_graph_edges (user_id, source_label, source_grp, target_label, target_grp, weight, relationship, first_seen, last_seen)
VALUES (:user_id, :source_label, :source_grp, :target_label, :target_grp, 1, :relationship, NOW(), NOW())
AS new
ON DUPLICATE KEY UPDATE
    weight       = weight + 1,
    relationship = new.relationship,
    last_seen    = NOW();
```

---

**grp 검증 규칙:**

AI서버에서 group 검증을 수행한 후 전송하지만, Backend에서도 이중 검증을 권장한다.
허용값 6개 외의 값이 들어오면 `emotional_exhaustion`으로 치환한다.

```sql
-- 허용값 확인용 (애플리케이션 코드에서 검증)
SET @valid_groups = 'work_structure,leadership,peer_relations,career_growth,culture_system,emotional_exhaustion';

-- 유효하지 않으면 기본값으로 치환
IF FIND_IN_SET(:grp, @valid_groups) = 0 THEN
    SET :grp = 'emotional_exhaustion';
END IF;
```

---

**Mode B 전체 처리 흐름 요약:**

```
POST /api/v1/graph_nodes/episodes 수신
    │
    ├─ body에서 user_id, got_result.nodes, got_result.edges 추출
    │
    ├─ nodes 배열로부터 id → (label, group) 매핑 테이블 생성
    │
    ├─ [트랜잭션 시작]
    │
    ├─ 각 node에 대해:
    │   ├─ grp 검증 (6개 허용값 외 → emotional_exhaustion)
    │   └─ INSERT ... ON DUPLICATE KEY UPDATE (EMA + trend + mention_count)
    │
    ├─ 각 edge에 대해:
    │   ├─ from/to → label, group 변환 (매핑 테이블 참조)
    │   ├─ self-loop 확인 → 같으면 건너뜀
    │   └─ INSERT ... ON DUPLICATE KEY UPDATE (weight + 1)
    │
    ├─ [트랜잭션 커밋]
    │
    └─ 응답: { "success": true, "id": "<generated_id>" }
```

> AI서버 참조 코드: `src/api/graph_cumulative.py` — `publish_graph_to_rdb()`

---

### 6-5. Backend팀에 필요한 API 엔드포인트

| 순서 | 엔드포인트 | 메서드 | 용도 |
|------|-----------|--------|------|
| **①** | `/api/v1/graph_nodes/episodes` | POST | AI서버 → GoT 에피소드 원본 수신 + EMA 계산 + UPSERT |
| **②** | `/api/v1/graph/users/{id}/data` | GET | **프론트엔드용** — MySQL 누적 데이터 직접 서빙 |

> **②번은 프론트엔드가 호출하는 엔드포인트**다.
> Backend가 MySQL의 `user_graph_nodes`, `user_graph_edges` 테이블에서 직접 조회하여 반환한다.
> AI서버(Neo4j)를 거치지 않는다.

### 6-6. RDB에서 누적 데이터 활용 — 쿼리 예시

Backend팀이 MySQL에 누적 데이터를 저장하면, 아래와 같은 조회가 가능해진다.

#### 예시 1: 특정 사용자의 상위 5개 카테고리 조회

> "사용자 A가 가장 자주 겪는 문제 영역은?"

```sql
-- 사용자별 가장 많이 연결된 카테고리 상위 5개
SELECT
    gn.grp,
    COUNT(*)               AS node_count,
    ROUND(AVG(gn.weight), 3) AS avg_weight
FROM user_graph_nodes gn
WHERE gn.user_id = 'u_001'
GROUP BY gn.grp
ORDER BY node_count DESC
LIMIT 5;

-- 예상 결과:
-- +----------------------+------------+------------+
-- | grp                  | node_count | avg_weight |
-- +----------------------+------------+------------+
-- | emotional_exhaustion |         23 |      0.721 |
-- | leadership           |         15 |      0.684 |
-- | work_structure       |         12 |      0.553 |
-- | peer_relations       |          8 |      0.492 |
-- | career_growth        |          5 |      0.410 |
-- +----------------------+------------+------------+
```

#### 예시 2: 카테고리 간 연결 빈도 상위 5개 (어떤 문제가 어떤 문제로 이어지나?)

> "리더십 문제가 번아웃으로 이어지는 빈도가 얼마나 되나?"

```sql
-- 카테고리 간 연결 빈도 상위 5개
-- edges 테이블에 source_grp, target_grp이 이미 저장되어 있어 JOIN 불필요
SELECT
    ge.source_grp  AS from_grp,
    ge.target_grp  AS to_grp,
    COUNT(*)              AS link_count,
    ROUND(AVG(ge.weight), 3) AS avg_link_weight
FROM user_graph_edges ge
WHERE ge.user_id = 'u_001'
  AND ge.source_grp != ge.target_grp   -- 같은 카테고리 내 연결 제외
GROUP BY ge.source_grp, ge.target_grp
ORDER BY link_count DESC
LIMIT 5;

-- 예상 결과:
-- +----------------------+----------------------+------------+-----------------+
-- | from_grp             | to_grp               | link_count | avg_link_weight |
-- +----------------------+----------------------+------------+-----------------+
-- | leadership           | emotional_exhaustion |         12 |           0.813 |
-- | work_structure       | emotional_exhaustion |          9 |           0.687 |
-- | peer_relations       | career_growth        |          6 |           0.542 |
-- | leadership           | peer_relations       |          5 |           0.498 |
-- | culture_system       | work_structure       |          4 |           0.451 |
-- +----------------------+----------------------+------------+-----------------+
```

#### 예시 3: 시간에 따른 카테고리 가중치 추이

> "사용자 A의 리더십 문제가 시간이 지나면서 심해지고 있는지?"

```sql
-- 특정 카테고리의 weight 변화 추이 (최근 10개 에피소드)
SELECT
    gn.label,
    gn.grp,
    ROUND(gn.weight, 3)  AS weight,
    gn.mention_count,
    gn.trend,            -- 'increasing' / 'decreasing' / 'stable'
    gn.last_seen
FROM user_graph_nodes gn
WHERE gn.user_id = 'u_001'
  AND gn.grp = 'leadership'
ORDER BY gn.last_seen DESC
LIMIT 10;
```

---

## 7. 팀별 역할 및 담당 작업

### 개발자3 (AI팀) — 전체 Neo4j 구현 담당

개발자3이 Neo4j 관련 **모든 구현과 유지보수를 담당**한다.

**이미 완료한 것:**
- Neo4j DB 접속 레이어 (`src/db/` 전체)
- GoT → Neo4j 저장 로직 (`podcast_reasoning.py`)
- GoT → Backend 전송 (`graph_cumulative.py` — `publish_graph_to_rdb()`)
- GoT → 프론트엔드 JSON 변환 (`graph_transformer.py`)
- 사용자 그래프 조회 API (`routes/graph.py`, 이관 후 삭제 예정)
- 스키마 DDL, 로컬 Docker, 통합 테스트

**차후 작업:**
- Knowledge Agent 실제 구현 (Stub → Neo4j 쿼리, Pinecone과 함께)
- Emotion/Topic 마스터 데이터 시드
- MySQL ↔ Neo4j 동기화 로직
- 조직 단위 분석 확장 (섹션 9 참고)

---

### Backend팀

**요청 사항 (우선순위순):**

| 순서 | 엔드포인트 | 용도 |
|------|----------|------|
| 1 | `POST /api/v1/graph_nodes/episodes` | GoT 에피소드 수신 + EMA 계산 + UPSERT |
| 2 | `GET /api/v1/graph/users/{id}/data` | **프론트엔드용 — MySQL에서 직접 서빙** |

> `user_graph_nodes`, `user_graph_edges` 테이블이 필요하다.
> DDL은 섹션 6-4, EMA 계산 로직은 섹션 6-3, 쿼리 예시는 섹션 6-6을 참고.

---

### 인프라팀

**요청 사항:**

| 순서 | 작업 | 비고 |
|------|------|------|
| 1 | Neo4j 인스턴스 배포 | app-2와 같은 서버 또는 별도 인스턴스 (아래 참고) |
| 2 | 포트 개방 | 7687(Bolt), 7474(HTTP UI - 필요 시) |
| 3 | 환경변수 등록 | NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD |
| 4 | `init.cypher` 실행 | Neo4j 배포 직후 DDL 실행 |
| 5 | `docker-compose.yml` 수정 | Neo4j 서비스 주석 해제 |

**인스턴스 메모리 제약 사항:**

현재 app-2(AI서버)는 EC2 `t3.medium` (RAM 4GB)이다.
Neo4j는 최소 ~1GB RAM이 필요하고, AI서버가 이미 ~2.5GB를 사용 중이라 **같은 인스턴스에서 OOM(메모리 부족) 위험**이 있다.

| 해결 방안 | 비용 | 비고 |
|---------|------|------|
| app-2를 `t3.large`(8GB)로 업그레이드 | 월 +$30 | 가장 단순 |
| Neo4j 전용 인스턴스 분리 | 월 +$15~30 | 운영 복잡도 증가 |
| Neo4j AuraDB (매니지드) | 월 $65~ | 운영 부담 최소 |

---

## 8. 협업 작업 순서 (Phase별)

### 전체 타임라인

```
Phase 1 ─── 의사결정 (전체 팀, ~1일)
    │
    ▼
Phase 2 ─── 인프라 준비 (인프라팀, ~2일)
    │
    ▼
Phase 3 ─── 병렬 구현 (개발자3 + Backend팀)
    │         ├─ 3-A: 개발자3 — Neo4j 초기 데이터 적재 + 저장 검증
    │         └─ 3-B: Backend팀 — RDB 누적 API 구현
    │
    ▼
Phase 4 ─── 통합 검증 (전체 팀, ~2일)
    │
    ▼
Phase 5 ─── 프로덕션 배포 (인프라팀 주도)
```

---

### Phase 1 — 의사결정 (전체 팀)

| # | 결정 사항 | 참여자 |
|---|---------|--------|
| 1 | Neo4j 배포 위치 (같은 서버 vs 별도 인스턴스) | 인프라팀 + 팀 리드 |
| 2 | 인스턴스 업그레이드 여부 (4GB → 8GB) | 인프라팀 |
| 3 | RDB 누적 테이블 스키마 합의 (`user_graph_nodes`, `user_graph_edges`) | 개발자3 + Backend팀 |

---

### Phase 2 — 인프라 준비 (인프라팀)

> **선행**: Phase 1 완료

| # | 작업 |
|---|------|
| 2-1 | Neo4j 5 Community 인스턴스 배포 (Docker 또는 네이티브) |
| 2-2 | 인증 비밀번호 설정 |
| 2-3 | 7687(Bolt) 포트 네트워크 접근 제어 — AI서버에서만 접근 허용 |
| 2-4 | 환경변수 등록 (NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD) |
| 2-5 | `dev/local_db/neo4j/init.cypher` 실행 → 제약 5개 + 인덱스 7개 생성 |
| 2-6 | `docker-compose.yml` Neo4j 서비스 주석 해제 + depends_on 활성화 |

**완료 기준**: `bolt://<host>:7687` 로 연결 성공 + 스키마 생성 확인

---

### Phase 3-A — 개발자3 작업 (인프라 완료 후)

| # | 작업 | 파일 |
|---|------|------|
| 3-A-1 | Emotion / Topic 마스터 데이터 시드 스크립트 작성 + 실행 | `dev/local_db/seed.py` 확장 |
| 3-A-2 | 프로덕션 환경에서 GoT → Neo4j 저장 E2E 검증 | `podcast_reasoning.py` |
| 3-A-3 | Neo4j → RDB 누적 저장 E2E 검증 | `graph_cumulative.py` |

### Phase 3-B — Backend팀 작업 (Phase 3-A와 병렬 진행 가능)

| # | 작업 | 엔드포인트 |
|---|------|----------|
| 3-B-1 | `user_graph_nodes`, `user_graph_edges` 테이블 생성 (섹션 6-4 DDL 참고) | MySQL DDL |
| 3-B-2 | GoT 에피소드 수신 + EMA 계산 + UPSERT API | `POST /api/v1/graph_nodes/episodes` |
| 3-B-3 | 프론트엔드용 누적 그래프 조회 API | `GET /api/v1/graph/users/{id}/data` |

---

### Phase 4 — 통합 검증 (전체 팀)

| # | 검증 항목 | 담당 |
|---|---------|------|
| 4-1 | Neo4j 통합 테스트 | 개발자3 — `pytest dev/local_db/test_neo4j_integration.py -v` |
| 4-2 | GoT 저장 → Neo4j 조회 일치 확인 | 개발자3 |
| 4-3 | RDB 누적 저장 API 통합 테스트 | 개발자3 + Backend팀 |
| 4-4 | 프론트엔드 그래프 시각화 연동 확인 | 개발자3 + Backend팀 + 프론트팀 |
| 4-5 | 메모리 모니터링 (24시간 OOM 없이 안정) | 인프라팀 |

---

### Phase 5 — 프로덕션 배포

| # | 작업 | 담당 |
|---|------|------|
| 5-1 | 프로덕션 환경 최종 확인 | 인프라팀 |
| 5-2 | 전체 파이프라인 E2E 테스트 | 전체 팀 |
| 5-3 | 롤아웃 + 모니터링 | 인프라팀 |

---

## 9. 차후 계획 — 조직 단위 분석 확장

### 9-1. 현재: 개인 사용자 단위

지금은 GoTNode가 **개인 사용자(user_id) 기준**으로 저장된다.
한 사용자의 감정 패턴만 볼 수 있다.

```
User A ─→ Session 1 ─→ GoTNode (leadership, 0.8)
       ─→ Session 2 ─→ GoTNode (emotional_exhaustion, 0.9)
       ─→ Session 3 ─→ GoTNode (leadership, 0.7)

→ "User A는 리더십 문제와 감정 소진이 주요 패턴이다"
```

### 9-2. 차후: 조직(팀/부서/회사) 단위

사용자가 소속된 **조직(organization)** 기준으로 데이터를 종합하면,
"이 팀에서 가장 많이 발생하는 문제 유형"을 파악할 수 있다.

```
조직 X (마케팅팀)
  ├─ User A: leadership(0.8), emotional_exhaustion(0.9)
  ├─ User B: peer_relations(0.7), work_structure(0.6)
  └─ User C: leadership(0.9), career_growth(0.5)
                       ↓
          ┌──────────────────────────────────┐
          │  조직 X 종합 분석                 │
          │                                  │
          │  1위: leadership (3명 중 2명)     │
          │  2위: emotional_exhaustion (1명)  │
          │  3위: peer_relations (1명)        │
          │  4위: work_structure (1명)        │
          │  5위: career_growth (1명)         │
          └──────────────────────────────────┘
```

이를 위해 필요한 변경:

**Neo4j 스키마 확장:**
```cypher
-- 조직 노드 추가
CREATE CONSTRAINT org_id_unique FOR (o:Organization) REQUIRE o.org_id IS UNIQUE;

-- User → Organization 관계
MERGE (u:User {user_id: $uid})-[:BELONGS_TO]->(o:Organization {org_id: $oid})
```

**RDB 조직 단위 집계 쿼리 예시:**

```sql
-- 조직 내 가장 많이 나타나는 카테고리 상위 5개
SELECT
    gn.grp,
    COUNT(DISTINCT gn.user_id) AS affected_users,
    COUNT(*)                   AS total_nodes,
    ROUND(AVG(gn.weight), 3)   AS avg_weight
FROM user_graph_nodes gn
JOIN users u ON gn.user_id = u.user_id
WHERE u.organization_id = 'org_marketing'
GROUP BY gn.grp
ORDER BY affected_users DESC, total_nodes DESC
LIMIT 5;

-- 예상 결과:
-- +----------------------+----------------+-------------+------------+
-- | grp                  | affected_users | total_nodes | avg_weight |
-- +----------------------+----------------+-------------+------------+
-- | leadership           |              2 |          18 |      0.756 |
-- | emotional_exhaustion |              1 |          12 |      0.692 |
-- | peer_relations       |              1 |           8 |      0.534 |
-- | work_structure       |              1 |           6 |      0.498 |
-- | career_growth        |              1 |           5 |      0.410 |
-- +----------------------+----------------+-------------+------------+
```

**Neo4j 조직 단위 탐색 쿼리 예시:**

```cypher
-- 조직 내 모든 사용자의 GoTNode를 종합하여 카테고리 분포 조회
MATCH (o:Organization {org_id: $org_id})<-[:BELONGS_TO]-(u:User)
      -[:HAS_SESSION]->(s:Session)-[:REASONED_BY]->(g:GoTNode)
RETURN g.group AS category,
       count(DISTINCT u.user_id) AS affected_users,
       count(*) AS total_nodes,
       avg(g.weight) AS avg_weight
ORDER BY affected_users DESC
LIMIT 5
```

### 9-3. 단계별 확장 로드맵

| 단계 | 내용 | 필요 작업 |
|------|------|---------|
| **1단계 (현재)** | 개인 사용자 GoT 저장 + RDB 누적 | Phase 2~5 완료 |
| **2단계** | Knowledge Agent 실제 구현 | Pinecone 연동 후 Stub 교체 |
| **3단계** | Emotion 패턴 자동 갱신 | OFTEN_COOCCURS 관계 자동 생성 |
| **4단계** | 조직(Organization) 노드 도입 | Neo4j 스키마 확장 + RDB 집계 쿼리 |
| **5단계** | 조직 대시보드 | 프론트팀 + Backend팀 — 조직별 통계 화면 |
| **6단계** | Neo4j AuraDB 전환 검토 | 데이터 규모에 따라 매니지드 서비스 전환 |

---

## 10. 설정·환경변수·테스트

### 10-1. config/settings.yaml 관련 설정

```yaml
# 데이터베이스 접속 정보
databases:
  neo4j:
    uri: "bolt://localhost:7687"   # NEO4J_URI 환경변수로 오버라이드 가능
```

### 10-2. 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `NEO4J_URL` | Neo4j Bolt URI | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 사용자명 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | (없음) — **필수** |

### 10-3. 테스트 실행 방법

```bash
# 1. 단위 테스트 (Neo4j 없이 실행 가능)
pytest tests/api/test_graph_cumulative.py -v   # GoT → Backend 전송 로직
pytest tests/api/test_graph_routes.py -v       # 그래프 조회 API 응답 형식

# 2. 통합 테스트 (로컬 Neo4j 필요)
#    먼저 Neo4j 컨테이너를 띄운다:
docker compose -f dev/local_db/docker-compose.db.yml up -d

#    그 다음 테스트 실행:
pytest dev/local_db/test_neo4j_integration.py -v
```

---

## 부록: 주요 코드 참조

| 기능 | 파일 | 핵심 함수/클래스 |
|------|------|----------------|
| Neo4j 직접 접속 | `src/db/neo4j_client.py` | `Neo4jClient.execute_query()` |
| 클라이언트 생성 | `src/db/factory.py` | `create_graph_client()` |
| GoT → Neo4j 저장 | `src/agents/podcast/podcast_reasoning.py` | `_save_got_to_neo4j()` |
| GoT → Backend 전송 | `src/agents/podcast/podcast_reasoning.py` | `_publish_graph_to_backend()` |
| GoT 에피소드 전송 | `src/api/graph_cumulative.py` | `publish_graph_to_rdb()` |
| group 검증 | `src/api/graph_transformer.py` | `validate_group()` |
| 카테고리 분포 계산 | `src/api/graph_transformer.py` | `calc_category_distribution()` |
| GoT → 프론트엔드 JSON | `src/api/graph_transformer.py` | `transform_got_to_graph_data()` |
| 스키마 초기화 | `dev/local_db/neo4j/init.cypher` | 제약 5개 + 인덱스 7개 |

---

## 11. 부록: STORAGE_MODE 참고

> 이 섹션은 코드 내부의 `STORAGE_MODE` 분기 로직에 대한 참고 자료다.
> 현재 프로젝트의 배포 방향은 섹션 4에 기술된 구조(Neo4j 직접 + MySQL은 Backend 경유)로 확정되어 있다.

### STORAGE_MODE란?

`src/db/factory.py`에는 환경변수 `STORAGE_MODE`에 따라 DB 클라이언트를 선택하는 팩토리 패턴이 있다.
코드에 정의된 3가지 모드는 다음과 같다:

| 모드 | Neo4j | MySQL | Pinecone | S3 |
|------|-------|-------|----------|-----|
| `local` | 직접 | 직접 | 직접 | 직접 |
| `proxy` | Backend 경유 | Backend 경유 | Backend 경유 | Backend 경유 |
| `hybrid` | 직접 | Backend 경유 | 직접 | 직접 |

### 팩토리 코드 (src/db/factory.py)

```python
# Neo4j 클라이언트:
def create_graph_client():
    mode = get_settings().storage_mode
    if mode == "proxy":
        return GraphProxyClient(BackendClient())  # Backend 경유
    else:  # "local" 또는 "hybrid"
        return Neo4jClient()                      # 직접 접속

# MySQL 클라이언트:
def create_rdb_client():
    mode = get_settings().storage_mode
    if mode == "local":
        return MySQLClient()                      # 직접 접속
    else:  # "proxy" 또는 "hybrid"
        return RDBProxyClient(BackendClient())    # Backend 경유
```

### 모드 결정 순서

1. 환경변수 `STORAGE_MODE`가 있으면 그 값 사용
2. 없으면 `config/settings.yaml`의 `storage.mode` 값 사용 (기본값: `proxy`)
3. 그것도 없으면 `local`

### 참고 사항

- `proxy` 모드의 `GraphProxyClient`(`src/db/api_proxy.py`)는 코드만 있고 Backend 엔드포인트가 미구현이라 **동작하지 않는다**.
- `config/settings.yaml`의 기본값은 `proxy`이지만, 로컬 개발 시 `.env`에서 오버라이드하여 사용한다.

---

*마지막 업데이트: 2026-04-07*
*관련 문서: `docs/guides/NEO4J_DEPLOYMENT_ANALYSIS.md`, `docs/architecture/DATA_SCHEMA.md`*

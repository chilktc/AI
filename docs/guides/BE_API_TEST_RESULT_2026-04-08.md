# AI ↔ BE API 호출 테스트 결과

> 작성일: 2026-04-08
> 환경: AWS SSM (Instance: i-02631e0888c49b0b7, t7-mindlog-prod-app-2)
> 대상: AI 서버 → BE 서버 graph API 3종 수동 검증

---

## 테스트 환경

| 항목 | 값 |
|------|-----|
| AI 서버 포트 | 8000 |
| BE 서버 URL | `http://10.7.10.20:8080/api/v1` |
| STORAGE_MODE | `proxy` |
| Neo4j URL | `bolt://neo4j:7687` |
| 테스트 방식 | AWS SSM Session Manager → curl / Python urllib |

### 테스트용 유저

| 유저 | user_id | 데이터 |
|------|---------|--------|
| user1 | `9f3b9560-331d-11f1-b83f-02c91128bc03` | 더미 데이터 있음 |
| user2 | `9f3b9c5e-331d-11f1-b83f-02c91128bc03` | 빈 응답 |

---

## 테스트 결과 요약

| # | API | 메서드 | 결과 |
|---|-----|--------|------|
| 1 | `/api/v1/graph_nodes` | GET | ✅ 성공 |
| 2 | `/api/v1/graph_nodes` | PUT | ✅ 성공 |
| 3 | `/api/v1/graph_analyses` | POST | ✅ 성공 |

---

## Test 1 — 기존 누적 그래프 조회

**용도:** AI 서버가 EMA 계산 등을 위해 특정 사용자의 기존 누적 그래프 데이터를 조회할 때 사용

### 요청

```
GET http://10.7.10.20:8080/api/v1/graph_nodes?user_id=9f3b9560-331d-11f1-b83f-02c91128bc03
```

### 응답 (성공)

```json
{
  "code": "ok",
  "message": "성공",
  "data": {
    "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
    "type": "graph_cumulative",
    "data": {
      "nodes": [
        {
          "label": "번아웃",
          "grp": "EMOTIONAL_EXHAUSTION",
          "weight": 0.86,
          "mention_count": 5,
          "trend": "increasing",
          "first_seen": "2026-04-01T00:10:00",
          "last_seen": "2026-04-08T00:35:00"
        },
        {
          "label": "업무 과부하",
          "grp": "WORK_STRUCTURE",
          "weight": 0.91,
          "mention_count": 7,
          "trend": "increasing",
          "first_seen": "2026-04-01T00:00:00",
          "last_seen": "2026-04-08T00:30:00"
        }
      ],
      "links": [
        {
          "source_label": "업무 과부하",
          "source_grp": "WORK_STRUCTURE",
          "target_label": "번아웃",
          "target_grp": "EMOTIONAL_EXHAUSTION",
          "weight": 6,
          "relationship": "causes",
          "first_seen": "2026-04-01T00:30:00",
          "last_seen": "2026-04-08T00:45:00"
        }
      ]
    }
  }
}
```

**결과:** ✅ 정상 — nodes/links 데이터 반환 확인

---

## Test 2 — 누적 그래프 백엔드로 전달

**용도:** AI 서버가 계산한 누적 그래프 결과를 백엔드에 저장할 때 사용

### 요청

```
PUT http://10.7.10.20:8080/api/v1/graph_nodes
Content-Type: application/json
```

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "type": "graph_cumulative",
  "data": {
    "nodes": [
      {
        "label": "업무과부하",
        "grp": "work_structure",
        "weight": 0.81,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-08T10:30:00"
      }
    ],
    "links": [
      {
        "source_label": "업무과부하",
        "source_grp": "work_structure",
        "target_label": "번아웃",
        "target_grp": "emotional_exhaustion",
        "weight": 3,
        "relationship": "causes",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-08T10:30:00"
      }
    ]
  }
}
```

### 응답 (성공)

```json
{
  "code": "ok",
  "message": "성공"
}
```

**결과:** ✅ 정상 — 저장 성공

---

## Test 3 — 그래프 분석 원본 저장

**용도:** 에피소드 단위 그래프 분석 원본 payload를 백엔드에 저장할 때 사용

### 요청

```
POST http://10.7.10.20:8080/api/v1/graph_analyses
Content-Type: application/json
```

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "episode_id": "ep_001",
  "session_id": "sess_001",
  "analysis_type": "got_analysis",
  "payload": {
    "summary": "업무과부하와 번아웃의 연결성이 높게 관찰됨",
    "nodes": [
      { "label": "업무과부하", "grp": "work_structure", "score": 0.81 },
      { "label": "번아웃", "grp": "emotional_exhaustion", "score": 0.76 }
    ],
    "links": [
      {
        "source_label": "업무과부하",
        "target_label": "번아웃",
        "relationship": "causes",
        "score": 0.88
      }
    ]
  }
}
```

### 응답 (성공)

```json
{
  "code": "ok",
  "message": "성공"
}
```

**결과:** ✅ 정상 — 저장 성공

---

---

## 내부 스키마 기준 추가 테스트 (2차)

> AI 코드가 실제로 백엔드에 전송하는 SaveRequest 포맷 기준으로 재테스트.
> 1차 테스트는 백엔드팀 노션 문서 기준 스키마를 사용해 전부 성공했으나,
> 실제 코드 경로(`AgentDataPublisher.publish()`, `publish_graph_to_rdb()`)에서 전송하는 포맷과 다름.

### 내부 스키마 구조 (SaveRequest)

```json
{
  "user_id": "...",
  "session_id": "...",
  "type": "<resource 또는 TYPE 상수>",
  "data": { ... },
  "timestamp": "2026-04-08T..."
}
```

### 추가 테스트 결과 요약

| # | API | 메서드 | 스키마 출처 | 결과 |
|---|-----|--------|------------|------|
| 4 | `/api/v1/graph_analyses` | POST | SaveRequest (내부 스키마) | ❌ 400 |
| 5 | `/api/v1/graph_nodes/episodes` | POST | SaveRequest (내부 스키마) | ❌ 404 |

---

### Test 4 — graph_analyses (내부 SaveRequest 스키마)

**코드 경로**: `src/agents/podcast/podcast_reasoning.py` → `_publish_graph_to_backend()` → `AgentDataPublisher.publish(resource=RESOURCE_GRAPH_ANALYSIS, data_type=None)` → `SaveRequest(type="graph_analyses", ...)`

> 주의: `data_type=None`일 때 `publisher.py`가 `type = resource` 값(`"graph_analyses"`)을 사용.
> TYPE_GRAPH_ANALYSIS 상수(`"graph_analysis"`)와 다름.

#### 요청

```
POST http://10.7.10.20:8080/api/v1/graph_analyses
Content-Type: application/json
```

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "session_id": "sess_test_001",
  "type": "graph_analyses",
  "data": {
    "got_result": {
      "nodes": [
        {"label": "\uc5c5\ubb34\uacfc\ubd80\ud558", "grp": "WORK_STRUCTURE", "intensity": 0.81},
        {"label": "\ubc88\uc544\uc6c3", "grp": "EMOTIONAL_EXHAUSTION", "intensity": 0.76}
      ],
      "edges": [
        {"source": "\uc5c5\ubb34\uacfc\ubd80\ud558", "target": "\ubc88\uc544\uc6c3", "relationship": "causes", "weight": 0.88}
      ]
    },
    "graph_data": {
      "nodes": [
        {"label": "\uc5c5\ubb34\uacfc\ubd80\ud558", "grp": "WORK_STRUCTURE", "weight": 0.81}
      ],
      "links": []
    },
    "category_distribution": {"WORK_STRUCTURE": 0.6, "EMOTIONAL_EXHAUSTION": 0.4}
  },
  "timestamp": "2026-04-08T10:00:00"
}
```

#### 응답

```json
{
  "status": 400,
  "error": "GRAPH_REQUEST_SCHEMA_MISMATCH",
  "message": "AI \uc11c\ubc84\uac00 \ubcf4\ub0b8 \uadf8\ub798\ud504 \uc694\uccad \ub370\uc774\ud130 \uad6c\uc870\uac00 \ubc31\uc5d4\ub4dc \uc2a4\ud399\uacfc \ub2e4\ub985\ub2c8\ub2e4."
}
```

**결과:** ❌ 400 GRAPH_REQUEST_SCHEMA_MISMATCH

**원인 분석:**
- BE 기대 스키마: `{user_id, episode_id, session_id, analysis_type, payload:{summary,nodes,links}}`
- AI 실제 전송: `{user_id, session_id, type:"graph_analyses", data:{got_result, graph_data, category_distribution}, timestamp}`
- 필드명/구조 전부 불일치

---

### Test 5 — graph_nodes/episodes (Mode B 엔드포인트)

**코드 경로**: `src/api/graph_cumulative.py` → `publish_graph_to_rdb()` → `SaveRequest(type="graph_episode", data={episode_id, got_result:{nodes,edges}})`

**리소스 경로**: `RESOURCE_GRAPH_EPISODES = "graph_nodes/episodes"` (`src/api/backend_resources.py`)

#### 요청

```
POST http://10.7.10.20:8080/api/v1/graph_nodes/episodes
Content-Type: application/json
```

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "session_id": "sess_test_001",
  "type": "graph_episode",
  "data": {
    "episode_id": "ep_test_001",
    "got_result": {
      "nodes": [
        {"label": "\uc5c5\ubb34\uacfc\ubd80\ud558", "grp": "WORK_STRUCTURE", "intensity": 0.81},
        {"label": "\ubc88\uc544\uc6c3", "grp": "EMOTIONAL_EXHAUSTION", "intensity": 0.76}
      ],
      "edges": [
        {"source": "\uc5c5\ubb34\uacfc\ubd80\ud558", "target": "\ubc88\uc544\uc6c3", "relationship": "causes", "weight": 0.88}
      ]
    }
  },
  "timestamp": "2026-04-08T10:00:00"
}
```

#### 응답

```
HTTP 404 Not Found
```

**결과:** ❌ 404 Not Found — 엔드포인트 미구현

**원인 분석:**
- `POST /api/v1/graph_nodes/episodes`는 Mode B 설계 기준 엔드포인트
- 백엔드팀은 Mode A (`GET/PUT /api/v1/graph_nodes`) 기준으로 구현
- Mode B 엔드포인트는 백엔드에 존재하지 않음

---

### 1차(노션 기준) vs 2차(내부 스키마) 비교

| 테스트 | API | 스키마 | 결과 |
|--------|-----|--------|------|
| 1차 Test 3 | POST /graph_analyses | 노션 schema (`analysis_type`, `payload`) | ✅ 200 |
| 2차 Test 4 | POST /graph_analyses | 내부 SaveRequest (`type`, `data`) | ❌ 400 |
| 2차 Test 5 | POST /graph_nodes/episodes | 내부 SaveRequest | ❌ 404 |

### 결론

AI 코드가 실제로 백엔드에 전송하는 포맷이 백엔드 구현과 불일치한다.
AI 쪽 스키마는 GoT 원본 데이터 구조 보존을 위해 변경 불가. BE 쪽 수정 또는 Mode B 신규 구현이 필요하다.

| 항목 | 현재 상태 | 필요 조치 |
|------|---------|---------|
| graph_analyses 스키마 | BE가 노션 형식만 수용 (400) | BE에서 SaveRequest 포맷 수용 필요 |
| graph_nodes/episodes | 미구현 (404) | BE에서 Mode B 엔드포인트 신규 구현 필요 |

---

## 백엔드팀 질문 (2026-04-08)

> AI팀 → 백엔드팀 확인 요청. 오류 발견 후 방향 조율을 위해 작성.

---

안녕하세요, AI팀입니다.
오늘 API 연동 테스트를 진행하다가 스키마 불일치 및 미구현 엔드포인트 두 건을 발견해서 확인 요청드립니다.

---

**[질문 1] `POST /api/v1/graph_analyses` 스키마 불일치**

노션에 공유해주신 스키마로 테스트하면 200이 나오는데, AI 코드가 실제로 전송하는 포맷으로 테스트하면 400 (`GRAPH_REQUEST_SCHEMA_MISMATCH`)이 발생합니다.

**AI 코드 실제 전송 포맷** (변경 불가):
```json
{
  "user_id": "...",
  "session_id": "...",
  "type": "graph_analyses",
  "data": {
    "got_result": { "nodes": [...], "edges": [...] },
    "graph_data": { "nodes": [...], "links": [...] },
    "category_distribution": { ... }
  },
  "timestamp": "..."
}
```

AI 쪽 스키마는 GoT(Graph of Thoughts) 원본 데이터 구조를 보존하기 위해 변경이 불가합니다.
**BE 쪽에서 위 포맷을 수용하도록 수정이 가능한지** 확인 부탁드립니다.

---

**[질문 2] `POST /api/v1/graph_nodes/episodes` 404**

AI 코드(`src/api/graph_cumulative.py`)가 GoT 분석 결과를 아래 엔드포인트로 전송하도록 되어 있는데, 현재 404가 발생합니다.

**AI 코드 실제 전송 포맷** (변경 불가):
```json
{
  "user_id": "...",
  "session_id": "...",
  "type": "graph_episode",
  "data": {
    "episode_id": "ep_001",
    "got_result": {
      "nodes": [{ "label": "...", "grp": "...", "intensity": 0.81 }],
      "edges": [{ "source": "...", "target": "...", "relationship": "causes", "weight": 0.88 }]
    }
  },
  "timestamp": "..."
}
```

이 엔드포인트는 EMA 계산을 BE가 담당하는 구조(Mode B)입니다. AI는 GoT 원본만 전송하고, BE가 기존 누적 데이터를 조회해 EMA를 계산한 뒤 저장합니다.

현재 BE에 구현된 `GET/PUT /api/v1/graph_nodes`는 AI가 EMA를 계산해서 전송하는 방식(Mode A)으로 보이는데, 이 경우 AI 코드 변경이 필요합니다.

두 가지 방향 중 BE팀 일정에 맞는 방향을 선택해 주시면 AI팀이 대응하겠습니다:

- **Mode B 유지** (AI팀 선호): `POST /api/v1/graph_nodes/episodes` 엔드포인트를 BE에서 신규 구현. AI 코드 변경 없음.
- **Mode A 전환**: AI팀이 코드 수정 필요. BE 추가 작업 없음.

빠른 확인 부탁드립니다.

---

---

## 3차 테스트 — Mode A 실제 AI 코드 포맷 기준 (2026-04-09)

> Mode A 구현 완료 및 PR 머지 후, AI 코드가 실제로 전송·수신하는 포맷으로 재테스트.
> `BackendClient.load_graph_cumulative()` / `put_graph_cumulative()` 실제 직렬화 포맷 기준.

### 결과 요약

| # | API | 메서드 | 검증 포인트 | 결과 |
|---|-----|--------|-----------|------|
| Test 6 | /api/v1/graph_nodes | GET (신규 유저) | 200 + 빈 nodes/links = 신규유저 정상 응답 | ✅ 200 |
| Test 7 | /api/v1/graph_nodes | GET (기존 유저) | `data.data` 중첩 구조 + 전체 필드 일치 | ✅ 200 |
| Test 8 | /api/v1/graph_nodes | PUT | SaveRequest 전체 포맷 수용 여부 | ✅ 200 |

---

### Test 6 — GET /graph_nodes (신규 유저)

**요청**:
```
GET http://10.7.10.20:8080/api/v1/graph_nodes?user_id=00000000-0000-0000-0000-000000000099
```

**응답**:
```json
{
  "code": "ok",
  "message": "성공",
  "data": {
    "user_id": "00000000-0000-0000-0000-000000000099",
    "type": "graph_cumulative",
    "data": {
      "nodes": [],
      "links": []
    }
  }
}
```

**결과**: ✅ HTTP 200 (BE 정상 설계) — 2026-04-09 재확인

**분석**:
- **BE 설계 의도 확인**: 404는 에러 코드 그 자체. 신규 유저 = "연결됐으나 데이터 없음" → 200 + 빈 nodes/links가 올바른 응답
- AI 코드(`client.py`)의 404 분기는 dead code → 제거 완료
- 200 경로에서 `inner = body.get("data", {}).get("data") or {}` → `{nodes:[], links:[]}` → `GraphCumulativeData(nodes=[], links=[])` — 정상 처리

---

### Test 7 — GET /graph_nodes (기존 유저)

**요청**:
```
GET http://10.7.10.20:8080/api/v1/graph_nodes?user_id=9f3b9560-331d-11f1-b83f-02c91128bc03
```

**결과**: ✅ HTTP 200

**필드 검증**:
| 검증 항목 | 결과 |
|---------|------|
| `data.data` 이중 중첩 구조 | ✅ OK |
| `nodes[].label`, `grp`, `weight`, `mention_count`, `trend` | ✅ OK |
| `nodes[].first_seen`, `last_seen` | ✅ OK |
| `links[].source_grp`, `target_grp` | ✅ OK |
| `links[].first_seen`, `last_seen` | ✅ OK |

확인된 `nodes[0]` 키: `['label', 'grp', 'weight', 'mention_count', 'trend', 'first_seen', 'last_seen']`
확인된 `links[0]` 키: `['source_label', 'source_grp', 'target_label', 'target_grp', 'weight', 'relationship', 'first_seen', 'last_seen']`
nodes count: 5, links count: 4 (2026-04-09 재확인)

→ **AI 코드 파싱 로직과 완전 일치. 추가 수정 불필요.**

---

### Test 8 — PUT /graph_nodes (확정 포맷, 2026-04-09 재확인)

**배경**: 최초 테스트에서 `session_id` + `timestamp` 포함 시 400 (`GRAPH_REQUEST_SCHEMA_MISMATCH`).
AI 코드 수정 후 (`put_graph_cumulative()`: `session_id`/`timestamp` 제거) 재테스트하여 ✅ 확인.

**최초 실패 포맷 (session_id/timestamp 포함)**:
```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "session_id": "sess_test_mode_a_001",
  "type": "graph_cumulative",
  "data": { "nodes": [...], "links": [...] },
  "timestamp": "2026-04-09T10:00:00+00:00"
}
```
→ HTTP 400 `GRAPH_REQUEST_SCHEMA_MISMATCH`

**확정 성공 포맷 (session_id/timestamp 제외)**:
```
PUT http://10.7.10.20:8080/api/v1/graph_nodes
Content-Type: application/json
```

```json
{
  "user_id": "9f3b9560-331d-11f1-b83f-02c91128bc03",
  "type": "graph_cumulative",
  "data": {
    "nodes": [
      {
        "label": "업무과부하",
        "grp": "work_structure",
        "weight": 0.81,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-08T10:30:00"
      }
    ],
    "links": [
      {
        "source_label": "업무과부하",
        "source_grp": "work_structure",
        "target_label": "번아웃",
        "target_grp": "emotional_exhaustion",
        "weight": 3,
        "relationship": "causes",
        "first_seen": "2026-04-08T10:00:00",
        "last_seen": "2026-04-08T10:30:00"
      }
    ]
  }
}
```

**응답**:
```json
{ "code": "ok", "message": "성공" }
```

**결과**: ✅ HTTP 200 OK

**필드별 BE 수용 여부 (최종 확인)**:

| 필드 위치 | 필드 | 수용 여부 | 비고 |
|----------|------|----------|------|
| root | `session_id` | ❌ 거부 | `GRAPH_REQUEST_SCHEMA_MISMATCH` 원인 |
| root | `timestamp` | ❌ 거부 | `GRAPH_REQUEST_SCHEMA_MISMATCH` 원인 |
| `nodes[]` | `first_seen`, `last_seen` | ✅ 필수 | 없으면 `GRAPH_INVALID_GROUP` 발생 |
| `links[]` | `source_grp`, `target_grp` | ✅ 필수 | 없으면 `GRAPH_INVALID_GROUP` 발생 |
| `links[]` | `first_seen`, `last_seen` | ✅ 필수 | 없으면 `GRAPH_INVALID_GROUP` 발생 |

**AI 코드 조치**: `src/api/client.py:put_graph_cumulative()` 수정 완료 — `session_id`/`timestamp` 제거, `data.data` 그대로 전달.

---

### 3차 종합 결론

| 항목 | 상태 | 비고 |
|------|------|------|
| GET (신규유저) | ✅ | BE 설계 정상 (200+빈데이터). AI 코드 내 404 분기 제거 완료 |
| GET (기존유저) | ✅ | 모든 필드 완전 일치 |
| PUT (확정 포맷) | ✅ | `session_id`/`timestamp` 제거 후 200 확인. `first_seen`/`last_seen`/`source_grp`/`target_grp`는 필수 포함 |

---

## 참고 사항

### SSM 터미널 한국어 입력 문제

SSM 터미널에서 한국어 직접 입력 시 문자가 누락됨. BE API에 한국어 값을 전달할 때는 Python Unicode escape 방식으로 우회한다.

```python
# 직접 입력 X (누락 발생)
"label": "업무과부하"

# Python unicode escape 사용 O
"label": "\uc5c5\ubb34\uacfc\ubd80\ud558"
```

실제 AI 서버 코드(`src/api/graph_cumulative.py`)는 Python에서 문자열을 직접 생성하므로 이 문제는 운영 환경에서 발생하지 않는다.

### AI 서버 환경 변수 확인 결과

| 변수 | 값 |
|------|-----|
| `BACKEND_API_URL` | `http://10.7.10.20:8080/api/v1` |
| `STORAGE_MODE` | `proxy` |
| `NEO4J_URL` | `bolt://neo4j:7687` |
| `NEO4J_USER` | `Mind_Log` |

### 포트 상태 (AI 서버 기준)

| 포트 | 서비스 | 상태 |
|------|--------|------|
| 7474 | Neo4j HTTP | LISTEN |
| 7687 | Neo4j Bolt | LISTEN |
| 8000 | AI 서버 (uvicorn) | LISTEN |

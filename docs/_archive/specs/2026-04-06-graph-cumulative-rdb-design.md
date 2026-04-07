# GoT 그래프 데이터 누적 저장 및 프론트엔드 서빙 설계서

> **작성일**: 2026-04-06
> **상태**: 완료 (Mode B 채택 — PR #69)
> **관련 PR**: #51 (Neo4j Deployment + Frontend Graph), #69 (Mode A 삭제, Mode B 단일화)
> **대상 독자**: 개발자 1·2·3 + 백엔드 팀
>
> **⚠️ 이력 주의**: 이 문서는 Mode A/B 설계 검토 당시의 원본이다. PR #69에서 Mode A가 삭제되어
> `upsert_mode`, `ema_alpha` 설정은 `config/settings.yaml`에서 제거되었다.
> Mode A 관련 코드 섹션은 역사적 참고용으로만 보존한다.

---

## 1. 배경 및 문제 정의

### 1.1 현재 상태 (AS-IS)

사용자의 GoT(Graph of Thoughts) 데이터가 두 곳에 저장된다:

| 저장소 | 형태 | 용도 |
|--------|------|------|
| **Neo4j** | 에피소드별 개별 노드 (`ep1_1`, `ep5_3`) | 추론 이력 원본 |
| **RDB** | 에피소드별 JSON 블럽 (`graph_analyses` 테이블) | 현재 프론트에서 미사용 |

프론트엔드 그래프는 `/internal/graph` 엔드포인트가 **Neo4j를 직접 쿼리**하여 서빙한다.

### 1.2 문제점

**P1. 노드 중복**: 같은 개념("업무과부하")이 에피소드마다 별도 노드로 생성된다.
사용할수록 노드가 무한 증가하며, 프론트엔드 그래프에 동일 개념이 분산 표시된다.

```
에피소드 1: ep1_1 "업무과부하" (weight=0.8)
에피소드 5: ep5_3 "업무과부하" (weight=0.9)
→ 프론트엔드에 "업무과부하" 노드 2개 표시
```

**P2. 에피소드 간 연결 단절**: `ep1_1 → ep1_3` (에피소드 1 내부)과
`ep5_1 → ep5_2` (에피소드 5 내부)는 연결되지만, 에피소드 간 연결은 없다.

**P3. RDB만으로 누적 그래프 불가**: RDB의 `graph_analyses` 테이블은 에피소드별
JSON 블럽이므로, Neo4j 없이는 사용자 전체 그래프를 재구성할 수 없다.

**P4. Weight 변화 미추적**: 동일 개념의 중요도가 시간에 따라 변하지만,
현재는 각 에피소드의 스냅샷만 존재하여 추세를 파악할 수 없다.

### 1.3 목표 (TO-BE)

- RDB에 **사용자별 누적 그래프 테이블**을 추가한다
- 매 에피소드마다 **label+group 기준으로 노드를 통합**하여 UPSERT한다
- Weight는 **지수이동평균(EMA)**으로 갱신하여 최근 상태를 반영한다
- Neo4j는 **추론 이력 원본**으로 기존 그대로 유지한다
- 프론트엔드는 RDB 누적 데이터를 Backend API로 조회한다

---

## 2. 아키텍처 개요

### 2.1 전체 데이터 흐름

```
GoT 생성 (Podcast Reasoning)
    ↓ got_result { nodes[], edges[] }
    │
    ├─ [기존 유지] Neo4j 저장
    │   └─ 에피소드별 개별 노드 (추론 이력 원본)
    │      MERGE GoTNode {got_node_id: "ep5_1", label: "업무과부하", weight: 0.9}
    │
    └─ [신규] RDB 누적 저장 ─────────────────────────────────────────
        │
        └─ Mode B: Backend가 UPSERT (PR #69에서 Mode A 삭제, Mode B 단일화 확정)
            1. 에피소드별 raw 데이터만 전송 (POST)
            2. Backend가 수신 시 EMA 계산 + UPSERT
```

### 2.2 DB별 역할 분담

| DB | 저장 형태 | 식별자 | 용도 |
|----|----------|--------|------|
| **Neo4j** | 에피소드별 개별 노드 | `{episode_id}_{node_id}` | 추론 이력 원본, Episode Memory 참조 |
| **RDB** | label+group 기준 통합 노드 | `user_id + label + group` | 프론트엔드 누적 그래프 서빙 |

**이유**:
- Neo4j는 "에피소드 3에서 업무과부하→번아웃 연결이 처음 나왔다" 같은 시점별 분석에 필요
- RDB는 "업무과부하가 3번 나왔고 점점 강해지고 있다"는 현재 상태 서빙에 필요
- 역할이 다르므로 데이터 형태가 달라야 한다

### 2.3 UPSERT 주체 모드 (Mode A / Mode B)

> **결정 완료**: Mode B 채택. Mode A는 PR #69에서 삭제되었다.
> `graph.upsert_mode` 설정은 `config/settings.yaml`에서 제거되었다.

~~두 모드 모두 구현하되, 설정으로 전환한다. 확정 후 미사용 모드의 코드를 제거하면 된다.~~

| 항목 | ~~Mode A (AI 서버 UPSERT)~~ | **Mode B (Backend UPSERT) ← 채택** |
|------|------------------------|------------------------|
| **UPSERT 주체** | ~~AI 서버~~ | Backend 서버 |
| **AI 서버 역할** | ~~기존 조회 → EMA 계산 → 갱신 전송~~ | 에피소드별 raw 데이터만 전송 |
| **Backend 역할** | ~~단순 저장/조회 (CRUD)~~ | 수신 시 EMA 계산 + UPSERT |
| **장점** | ~~도메인 로직이 AI 서버에 집중~~ | AI 서버 부담 감소 |
| **단점** | ~~조회→계산→저장 3단계 (네트워크 2회)~~ | 도메인 로직을 Backend에 인계 필요 |
| **사용 함수** | ~~`publish_graph_cumulative_mode_a()`~~ | `publish_graph_raw_mode_b()` |
| **설정값** | ~~`graph.upsert_mode: "ai_server"`~~ | ~~`graph.upsert_mode: "backend"`~~ (설정 삭제됨) |

---

## 3. RDB 스키마 설계

### 3.1 누적 노드 테이블: `user_graph_nodes`

사용자별로 label+group 조합이 유니크한 통합 노드를 저장한다.

```sql
CREATE TABLE user_graph_nodes (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id     VARCHAR(36)  NOT NULL,

    -- 노드 식별 (label + group 조합이 사용자 내에서 유니크)
    label       VARCHAR(200) NOT NULL,   -- 노드 텍스트 ("업무과부하", "번아웃")
    grp         VARCHAR(50)  NOT NULL,   -- 카테고리 (work_structure 등 6종)

    -- 누적 통계
    weight      FLOAT        NOT NULL DEFAULT 0.5,  -- EMA 가중치 (0.0~1.0)
    mention_count INT        NOT NULL DEFAULT 1,    -- 누적 언급 횟수
    trend       VARCHAR(20)  NOT NULL DEFAULT 'stable',  -- increasing/stable/decreasing

    -- 시간 추적
    first_seen  DATETIME     NOT NULL,   -- 최초 등장 에피소드 시각
    last_seen   DATETIME     NOT NULL,   -- 최근 등장 에피소드 시각

    -- 메타데이터
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 유니크 제약: 사용자별 label+group 조합은 하나만 존재
    UNIQUE KEY uq_user_label_group (user_id, label, grp),
    INDEX idx_user_id (user_id),
    INDEX idx_user_group (user_id, grp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**컬럼 설명**:

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `label` | VARCHAR(200) | GoT 노드의 텍스트. 통합 키로 사용 |
| `grp` | VARCHAR(50) | 6개 카테고리 중 하나. `group`은 MySQL 예약어이므로 `grp` 사용 |
| `weight` | FLOAT | EMA로 갱신되는 누적 가중치. 프론트엔드에서 노드 크기 결정에 사용 |
| `mention_count` | INT | 해당 개념이 몇 번 등장했는지. 빈도 분석에 사용 |
| `trend` | VARCHAR(20) | 최근 3회 weight 변화 방향. 프론트엔드 추세 표시에 사용 |
| `first_seen` | DATETIME | 최초 등장 시점. "언제부터 이 고민이 시작됐는지" |
| `last_seen` | DATETIME | 최근 등장 시점. "얼마나 최근까지 이 고민이 있는지" |

### 3.2 누적 엣지 테이블: `user_graph_edges`

노드 간 연결을 누적으로 저장한다. 같은 연결이 반복될수록 `weight`가 증가한다.

```sql
CREATE TABLE user_graph_edges (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id       VARCHAR(36)  NOT NULL,

    -- 엣지 식별 (source + target 조합이 사용자 내에서 유니크)
    source_label  VARCHAR(200) NOT NULL,  -- 출발 노드 label
    source_group  VARCHAR(50)  NOT NULL,  -- 출발 노드 group
    target_label  VARCHAR(200) NOT NULL,  -- 도착 노드 label
    target_group  VARCHAR(50)  NOT NULL,  -- 도착 노드 group

    -- 누적 통계
    weight        INT          NOT NULL DEFAULT 1,    -- 연결 누적 횟수
    relationship  VARCHAR(100) NOT NULL DEFAULT 'related',  -- 최근 관계 유형

    -- 시간 추적
    first_seen    DATETIME     NOT NULL,
    last_seen     DATETIME     NOT NULL,

    -- 메타데이터
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_user_edge (user_id, source_label, source_group, target_label, target_group),
    INDEX idx_user_id (user_id),

    -- 참조 무결성은 label+group 기반 (FK 대신 애플리케이션 레벨에서 보장)
    -- 이유: user_graph_nodes의 UNIQUE KEY와 직접 FK를 걸면 복잡도 증가
    CONSTRAINT chk_not_self_loop CHECK (
        NOT (source_label = target_label AND source_group = target_group)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**설계 근거**:
- FK를 걸지 않는 이유: 노드와 엣지가 동시에 UPSERT되므로 순서 보장이 어렵다.
  애플리케이션 레벨에서 노드 존재를 보장한다.
- `source_group`/`target_group` 포함 이유: 같은 label이 다른 group에 존재할 수 있다.
  (예: "불안" → `emotional_exhaustion`, "불안" → `career_growth`)
- `weight`는 연결 횟수(INT): 노드의 weight(EMA)와 다르게, 엣지는 단순 횟수로 충분하다.

### 3.3 grp 유효값 (6종)

```
work_structure       — 업무 구조/과부하
leadership           — 리더십/상사 관계
peer_relations       — 동료 관계
career_growth        — 커리어 성장
culture_system       — 조직 문화/제도
emotional_exhaustion — 감정 소진/번아웃
```

---

## 4. EMA (지수이동평균) 가중치 계산

### 4.1 공식

```
새 weight = α × 신규값 + (1 - α) × 기존 weight

α = 0.3 (PR #69 이후 Backend 책임 — AI 서버 config에서 제거됨)
```

### 4.2 계산 예시

사용자가 "업무과부하"를 3회 언급한 경우:

```
에피소드 1: intensity=0.8 (최초)        → weight = 0.80
에피소드 2: intensity=0.7               → weight = 0.3×0.7 + 0.7×0.80 = 0.77
에피소드 5: intensity=0.9               → weight = 0.3×0.9 + 0.7×0.77 = 0.81
```

### 4.3 α 값에 따른 특성

| α 값 | 특성 | 적합 상황 |
|-------|------|----------|
| 0.2 | 보수적, 과거 중시 | 장기 패턴 분석 |
| **0.3** | **균형 (기본값)** | **멘탈케어 일반** |
| 0.5 | 최근 중시 | 급성 상태 추적 |

멘탈케어에서 α=0.3을 기본값으로 선택한 이유:
- 최근 상태를 반영하면서도 급격한 변동을 방지한다
- 3~4회 이상 언급된 패턴은 쉽게 사라지지 않아 장기 추세를 유지한다
- 설정에서 변경 가능하므로 튜닝 가능하다

### 4.4 Trend 계산

```python
def calc_trend(old_weight: float, new_weight: float) -> str:
    """weight 변화량으로 trend를 결정한다.

    임계값 0.05: 이보다 작은 변화는 'stable'로 간주.
    """
    diff = new_weight - old_weight
    if diff > 0.05:
        return "increasing"
    if diff < -0.05:
        return "decreasing"
    return "stable"
```

### 4.5 최초 등장 시 처리

노드가 처음 등장하면 EMA 계산 없이 그대로 저장한다:
- `weight = intensity` (LLM이 생성한 값)
- `mention_count = 1`
- `trend = "stable"`
- `first_seen = last_seen = 현재 시각`

---

## 5. Backend API 스펙 (제안)

### 5.1 누적 그래프 노드 조회 (사용자 단위)

**사용자 단위**로 누적된 전체 그래프를 조회한다. 에피소드 단위가 아님.
프론트엔드가 사용자의 심리 지도를 표시하기 위해 호출한다.
Mode A에서는 AI 서버가 EMA 계산 전 기존 데이터를 조회할 때도 사용한다.

**주의**: 기존 `LoadResponse` 스키마(`data: list[dict]`)를 준수한다.
`data[0]`에 `nodes`/`edges`/`category_distribution` dict를 담는 형태.
이는 `BackendClient.load()`의 반환 타입과 호환된다.

```
GET /api/v1/graph_nodes?user_id={uuid}&limit={n}

Query Parameters:
  user_id  (필수) — 사용자 ID
  limit    (선택) — 최대 노드 수 (기본 100, 최대 500)

Response 200 (LoadResponse 호환):
{
  "success": true,
  "data": [
    {
      "nodes": [
        {
          "label": "업무과부하",
          "grp": "work_structure",
          "weight": 0.81,
          "mention_count": 3,
          "trend": "increasing",
          "first_seen": "2026-03-20T12:00:00Z",
          "last_seen": "2026-04-05T14:30:00Z"
        }
      ],
      "edges": [
        {
          "source_label": "업무과부하",
          "source_group": "work_structure",
          "target_label": "번아웃",
          "target_group": "emotional_exhaustion",
          "weight": 3,
          "relationship": "causes"
        }
      ],
      "category_distribution": {
        "work_structure": 3,
        "emotional_exhaustion": 2,
        "leadership": 1
      }
    }
  ],
  "total": 6,
  "page": 1
}
```

### 5.2 누적 그래프 갱신 (Mode A 전용)

AI 서버가 EMA 계산 후 갱신된 데이터를 전송한다.

```
PUT /api/v1/graph_nodes

Request Body:
{
  "user_id": "uuid",
  "session_id": "uuid",
  "timestamp": "2026-04-05T14:30:00Z",
  "nodes": [
    {
      "label": "업무과부하",
      "grp": "work_structure",
      "weight": 0.81,
      "mention_count": 3,
      "trend": "increasing",
      "first_seen": "2026-03-20T12:00:00Z",
      "last_seen": "2026-04-05T14:30:00Z"
    }
  ],
  "edges": [
    {
      "source_label": "업무과부하",
      "source_group": "work_structure",
      "target_label": "번아웃",
      "target_group": "emotional_exhaustion",
      "weight": 3,
      "relationship": "causes"
    }
  ]
}

Response 200:
{
  "success": true,
  "message": "graph_nodes updated",
  "updated_nodes": 3,
  "updated_edges": 2
}
```

### 5.3 에피소드별 Raw 데이터 전송 (Mode B 전용)

AI 서버는 변환 없이 에피소드 GoT 결과를 그대로 보낸다.
Backend가 수신 시 EMA 계산 + UPSERT를 수행한다.

```
POST /api/v1/graph_nodes/episodes

Request Body:
{
  "user_id": "uuid",
  "session_id": "uuid",
  "episode_id": "uuid",
  "timestamp": "2026-04-05T14:30:00Z",
  "got_result": {
    "nodes": [
      { "id": "1", "label": "업무과부하", "group": "work_structure", "intensity": 0.9 },
      { "id": "2", "label": "번아웃", "group": "emotional_exhaustion", "intensity": 0.95 }
    ],
    "edges": [
      { "from": "1", "to": "2", "relationship": "causes" }
    ]
  }
}

Response 200:
{
  "success": true,
  "message": "episode graph processed",
  "upserted_nodes": 2,
  "upserted_edges": 1
}
```

### 5.4 프론트엔드 서빙 API (사용자/조직 단위)

프론트엔드가 **사용자 단위** 또는 향후 **조직 단위**의 누적 그래프를 표시할 때 호출한다.
에피소드 단위 조회가 아니며, 해당 사용자의 전체 사용 이력이 통합된 그래프를 반환한다.
**5.1의 GET과 동일한 엔드포인트**를 프론트엔드가 Backend를 통해 호출한다.

```
[프론트엔드] → GET /api/v1/graph_nodes?user_id=xxx
           → [Backend 서버] → RDB user_graph_nodes/edges 조회 (사용자 전체 누적)
           → [Backend 서버] → 응답 반환
           → [프론트엔드] → Force-directed 그래프 렌더링
```

프론트엔드가 받는 최종 JSON (ID 변환 포함):

**주의**: `val`(20/50/100) 필드는 사용하지 않는다. 프론트엔드가 `weight` 원본값(0.0~1.0)을
직접 받아 노드 크기를 결정한다. 이는 3단계 이산화보다 더 세밀한 시각화를 가능하게 한다.

```json
{
  "success": true,
  "data": {
    "nodes": [
      {
        "id": "b1",
        "name": "업무과부하",
        "group": "work_structure",
        "weight": 0.81,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-03-20",
        "last_seen": "2026-04-05"
      },
      {
        "id": "br1",
        "name": "번아웃",
        "group": "emotional_exhaustion",
        "weight": 0.83,
        "mention_count": 3,
        "trend": "increasing",
        "first_seen": "2026-03-20",
        "last_seen": "2026-04-05"
      },
      {
        "id": "p1",
        "name": "상사 압박",
        "group": "leadership",
        "weight": 0.70,
        "mention_count": 2,
        "trend": "increasing",
        "first_seen": "2026-03-20",
        "last_seen": "2026-04-01"
      }
    ],
    "links": [
      { "source": "b1", "target": "br1", "weight": 3, "relationship": "causes" },
      { "source": "p1", "target": "b1",  "weight": 2, "relationship": "triggers" }
    ],
    "frequent_keywords": [
      { "tags": ["업무과부하", "번아웃"], "count": 3 },
      { "tags": ["상사 압박", "업무과부하"], "count": 2 }
    ],
    "category_distribution": {
      "work_structure": 3,
      "emotional_exhaustion": 3,
      "leadership": 2,
      "peer_relations": 1,
      "career_growth": 1
    }
  }
}
```

**조회 단위**: 에피소드가 아닌 **사용자 단위**로 조회한다.
`user_id`로 해당 사용자의 전체 누적 그래프를 반환한다.
향후 조직 단위 조회가 필요하면 `org_id` 파라미터를 추가하여 확장한다.

**ID 변환 위치**: Mode에 따라 다르다.
- Mode A: AI 서버의 `transform_cumulative_to_frontend()` 함수가 변환
- Mode B: Backend가 RDB 조회 후 자체 변환 (graph_transformer 로직 인계 필요)

---

## 6. 함수 설계 (AI 서버)

### 6.1 파일 구조

```
src/api/
├── graph_transformer.py       # [기존] GoT→프론트 변환 + [신규] EMA 계산
├── graph_cumulative.py        # [신규] 누적 그래프 UPSERT 로직 (Mode A/B)
├── publisher.py               # [기존] AgentDataPublisher
├── backend_resources.py       # [기존] + 신규 리소스 상수 추가
└── client.py                  # [기존] BackendClient (load/save/update)

src/agents/podcast/
└── podcast_reasoning.py       # [수정] _save_graph_data() 분기 추가
```

### 6.2 신규 파일: `src/api/graph_cumulative.py`

> **PR #69 반영**: Mode A 삭제, Mode B 단일화. 아래는 설계 당시 원본 (역사적 참고).

핵심 로직을 담는 신규 모듈이다. ~~Mode A / Mode B 함수를 모두 포함한다.~~ → Mode B 단일 함수.

```python
"""
GoT 그래프 데이터 누적 저장 모듈.

에피소드별 GoT 결과를 사용자별 누적 그래프로 통합하여 RDB에 저장한다.
Mode B(Backend UPSERT) 단일 방식으로 확정 (PR #69에서 Mode A 삭제).

사용 방법:
    - Mode B (Backend가 UPSERT):
        await publish_graph_raw_mode_b(got_result, state)

(이하 설계 원본 — upsert_mode/ema_alpha 설정은 PR #69에서 삭제됨)

확정 후:
    사용하지 않는 모드의 함수를 삭제하거나 주석 처리해도 다른 모드에 영향 없음.
    각 함수는 독립적이며 서로를 호출하지 않는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config.loader import get_settings
from src.api.graph_transformer import validate_group
from src.models.agent_state import AgentState

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# EMA 계산 유틸리티 — Mode A, Mode B 공통
# ═══════════════════════════════════════════════════════════════════════


def calc_ema(old_weight: float, new_intensity: float, alpha: float = 0.3) -> float:
    """지수이동평균(EMA)으로 weight를 갱신한다.

    Args:
        old_weight: 기존 누적 weight (0.0~1.0)
        new_intensity: 신규 에피소드의 intensity (0.0~1.0)
        alpha: 최근 반영 비율 (기본 0.3, settings.yaml에서 오버라이드 가능)

    Returns:
        갱신된 weight (0.0~1.0)

    예시:
        calc_ema(0.80, 0.7) → 0.77   # 0.3*0.7 + 0.7*0.80
        calc_ema(0.77, 0.9) → 0.81   # 0.3*0.9 + 0.7*0.77
    """
    return alpha * new_intensity + (1 - alpha) * old_weight


def calc_trend(old_weight: float, new_weight: float) -> str:
    """weight 변화량으로 trend를 결정한다.

    임계값 0.05: 이보다 작은 변화는 'stable'로 간주.

    Args:
        old_weight: EMA 계산 전 weight
        new_weight: EMA 계산 후 weight

    Returns:
        "increasing" | "stable" | "decreasing"
    """
    diff = new_weight - old_weight
    if diff > 0.05:
        return "increasing"
    if diff < -0.05:
        return "decreasing"
    return "stable"


def merge_nodes_from_got(
    got_result: dict[str, Any],
    existing_nodes: list[dict[str, Any]],
    alpha: float = 0.3,
) -> list[dict[str, Any]]:
    """GoT 노드를 기존 누적 노드와 병합한다.

    기존에 있는 노드 → EMA로 weight 갱신 + mention_count 증가
    새로운 노드 → 그대로 추가 (weight = intensity, mention_count = 1)

    Args:
        got_result: LLM이 생성한 GoT JSON (nodes, edges 포함)
        existing_nodes: Backend에서 조회한 기존 누적 노드 목록
        alpha: EMA 알파값

    Returns:
        갱신된 누적 노드 목록 (신규 + 업데이트)
    """
    # 기존 노드를 (label, group) → node로 인덱싱
    existing_map: dict[tuple[str, str], dict] = {}
    for node in existing_nodes:
        key = (node["label"], node["grp"])
        existing_map[key] = node

    now = datetime.now(timezone.utc).isoformat()
    updated_nodes: list[dict[str, Any]] = []

    for got_node in got_result.get("nodes", []):
        label = got_node.get("label", "")
        group = validate_group(got_node)
        intensity = got_node.get("intensity", 0.5)
        key = (label, group)

        if key in existing_map:
            # --- 기존 노드: EMA 갱신 ---
            existing = existing_map[key]
            old_weight = existing.get("weight", 0.5)
            new_weight = calc_ema(old_weight, intensity, alpha)
            updated_nodes.append({
                "label": label,
                "grp": group,
                "weight": round(new_weight, 4),
                "mention_count": existing.get("mention_count", 1) + 1,
                "trend": calc_trend(old_weight, new_weight),
                "first_seen": existing.get("first_seen", now),
                "last_seen": now,
            })
            # 처리 완료 표시
            del existing_map[key]
        else:
            # --- 신규 노드: 최초 등장 ---
            updated_nodes.append({
                "label": label,
                "grp": group,
                "weight": round(intensity, 4),
                "mention_count": 1,
                "trend": "stable",
                "first_seen": now,
                "last_seen": now,
            })

    # 이번 에피소드에 등장하지 않은 기존 노드는 변경 없이 유지
    # (PUT 요청 시 포함하지 않으면 Backend가 기존 값을 유지해야 함)

    return updated_nodes


def merge_edges_from_got(
    got_result: dict[str, Any],
    existing_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """GoT 엣지를 기존 누적 엣지와 병합한다.

    기존에 있는 엣지 → weight(횟수) 증가 + relationship 갱신
    새로운 엣지 → 추가 (weight=1)

    Args:
        got_result: LLM이 생성한 GoT JSON
        existing_edges: Backend에서 조회한 기존 누적 엣지 목록

    Returns:
        갱신된 누적 엣지 목록
    """
    # 노드 id → (label, group) 매핑 생성
    node_map: dict[str, tuple[str, str]] = {}
    for node in got_result.get("nodes", []):
        node_id = str(node.get("id", ""))
        label = node.get("label", "")
        group = validate_group(node)
        node_map[node_id] = (label, group)

    # 기존 엣지 인덱싱
    existing_map: dict[tuple, dict] = {}
    for edge in existing_edges:
        key = (
            edge["source_label"], edge["source_group"],
            edge["target_label"], edge["target_group"],
        )
        existing_map[key] = edge

    now = datetime.now(timezone.utc).isoformat()
    updated_edges: list[dict[str, Any]] = []

    for got_edge in got_result.get("edges", []):
        from_id = str(got_edge.get("from", ""))
        to_id = str(got_edge.get("to", ""))

        source = node_map.get(from_id)
        target = node_map.get(to_id)
        if not source or not target:
            continue  # 매핑 불가 엣지 건너뜀

        # self-loop 방지
        if source == target:
            continue

        key = (source[0], source[1], target[0], target[1])
        relationship = got_edge.get("relationship", "related")

        if key in existing_map:
            existing = existing_map[key]
            updated_edges.append({
                "source_label": source[0],
                "source_group": source[1],
                "target_label": target[0],
                "target_group": target[1],
                "weight": existing.get("weight", 1) + 1,
                "relationship": relationship,  # 최신 관계 유형으로 갱신
                "first_seen": existing.get("first_seen", now),
                "last_seen": now,
            })
            del existing_map[key]
        else:
            updated_edges.append({
                "source_label": source[0],
                "source_group": source[1],
                "target_label": target[0],
                "target_group": target[1],
                "weight": 1,
                "relationship": relationship,
                "first_seen": now,
                "last_seen": now,
            })

    return updated_edges


# ═══════════════════════════════════════════════════════════════════════
# Mode A: AI 서버가 UPSERT
#
# 사용 조건: config/settings.yaml → graph.upsert_mode: "ai_server"
# 호출 위치: podcast_reasoning.py → _save_graph_data()
#
# 흐름:
#   1. Backend에서 기존 누적 노드/엣지 조회 (GET /api/v1/graph_nodes)
#   2. merge_nodes_from_got() / merge_edges_from_got()로 EMA 계산
#   3. 갱신된 데이터를 Backend에 전송 (PUT /api/v1/graph_nodes)
#
# 장점: 도메인 로직(EMA, group 검증)이 AI 서버에 집중
# 단점: 네트워크 왕복 2회 (GET + PUT)
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_cumulative_mode_a(
    got_result: dict[str, Any],
    state: AgentState,
) -> bool:
    """[Mode A] AI 서버가 EMA 계산 후 누적 데이터를 Backend에 전송한다.

    1. 기존 누적 데이터 조회
    2. EMA 계산으로 노드/엣지 병합
    3. 갱신된 데이터 PUT 전송

    Args:
        got_result: LLM이 생성한 GoT JSON
        state: 파이프라인 상태 (user_id, session_id 포함)

    Returns:
        성공 시 True, 실패 시 False (예외 미전파)
    """
    try:
        from src.api.backend_resources import RESOURCE_GRAPH_NODES
        from src.api.main import backend_client

        if backend_client is None:
            raise RuntimeError("BackendClient가 초기화되지 않았습니다.")

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        settings = get_settings()
        alpha = getattr(settings, "graph_ema_alpha", 0.3)

        # 1단계: 기존 누적 데이터 조회
        load_response = await backend_client.load(
            RESOURCE_GRAPH_NODES,
            user_id=user_id,
        )

        existing_data = load_response.data[0] if load_response.data else {}
        existing_nodes = existing_data.get("nodes", [])
        existing_edges = existing_data.get("edges", [])

        # 2단계: EMA 계산으로 병합
        updated_nodes = merge_nodes_from_got(got_result, existing_nodes, alpha)
        updated_edges = merge_edges_from_got(got_result, existing_edges)

        # 3단계: 갱신된 데이터 전송 (PUT)
        await backend_client.update(
            RESOURCE_GRAPH_NODES,
            data={
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nodes": updated_nodes,
                "edges": updated_edges,
            },
        )

        logger.info(
            "Mode A 누적 그래프 갱신 완료 (user=%s, nodes=%d, edges=%d)",
            user_id, len(updated_nodes), len(updated_edges),
        )
        return True

    except Exception as e:
        logger.warning("Mode A 누적 그래프 갱신 실패 (파이프라인 계속): %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════
# Mode B: Backend가 UPSERT
#
# 사용 조건: config/settings.yaml → graph.upsert_mode: "backend"
# 호출 위치: podcast_reasoning.py → _save_graph_data()
#
# 흐름:
#   1. 에피소드별 GoT raw 데이터를 Backend에 전송 (POST)
#   2. Backend가 수신 시 EMA 계산 + user_graph_nodes/edges UPSERT
#
# 장점: AI 서버 부담 감소, 네트워크 1회
# 단점: Backend에 EMA/group 검증 도메인 로직 인계 필요
#
# Backend 인계 항목:
#   - calc_ema() 함수 로직
#   - calc_trend() 함수 로직
#   - validate_group() 함수 로직 + KEYWORD_MAP 사전
#   - merge_nodes_from_got() / merge_edges_from_got() 병합 로직
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_raw_mode_b(
    got_result: dict[str, Any],
    state: AgentState,
) -> bool:
    """[Mode B] 에피소드별 raw GoT 데이터를 Backend에 전송한다.

    Backend가 수신 시 자체적으로 EMA 계산 + UPSERT를 수행한다.
    AI 서버는 group 검증만 수행하고, 계산은 하지 않는다.

    Args:
        got_result: LLM이 생성한 GoT JSON
        state: 파이프라인 상태 (user_id, session_id 포함)

    Returns:
        성공 시 True, 실패 시 False (예외 미전파)
    """
    try:
        from src.api.backend_resources import RESOURCE_GRAPH_EPISODES
        from src.api.contracts import SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            raise RuntimeError("BackendClient가 초기화되지 않았습니다.")

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")

        # group 검증만 수행 (Backend가 모를 수 있는 도메인 지식)
        validated_nodes = []
        for node in got_result.get("nodes", []):
            validated_nodes.append({
                **node,
                "group": validate_group(node),
            })

        validated_got = {
            **got_result,
            "nodes": validated_nodes,
        }

        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type="graph_episode",
            data={
                "episode_id": state.get("episode_id", ""),
                "got_result": validated_got,
            },
            timestamp=datetime.now(timezone.utc),
        )

        await backend_client.save(RESOURCE_GRAPH_EPISODES, request)

        logger.info(
            "Mode B raw 그래프 전송 완료 (user=%s, nodes=%d, edges=%d)",
            user_id,
            len(validated_nodes),
            len(got_result.get("edges", [])),
        )
        return True

    except Exception as e:
        logger.warning("Mode B raw 그래프 전송 실패 (파이프라인 계속): %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════════
# 모드 디스패처 (PR #69 이후: Mode B 직접 호출로 단순화됨)
#
# podcast_reasoning.py에서 이 함수 하나만 호출한다.
# graph.upsert_mode 분기 로직은 PR #69에서 제거됨.
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_to_rdb(
    got_result: dict[str, Any],
    state: AgentState,
) -> bool:
    """누적 그래프를 RDB에 저장한다 (Mode B — Backend UPSERT).

    PR #69에서 graph.upsert_mode 분기 제거. Mode B 직접 호출.
        - "ai_server" → publish_graph_cumulative_mode_a()
        - "backend"   → publish_graph_raw_mode_b()

    확정 후 사용하지 않는 모드의 함수를 삭제해도 이 함수만 수정하면 된다.

    Args:
        got_result: LLM이 생성한 GoT JSON
        state: 파이프라인 상태

    Returns:
        성공 시 True, 실패 시 False
    """
    settings = get_settings()
    mode = getattr(settings, "graph_upsert_mode", "ai_server")

    if mode == "backend":
        return await publish_graph_raw_mode_b(got_result, state)
    else:
        # 기본값: ai_server (Mode A)
        return await publish_graph_cumulative_mode_a(got_result, state)
```

### 6.3 수정 파일: `src/api/graph_transformer.py` — 신규 함수 추가

기존 함수는 그대로 두고, 누적 데이터→프론트엔드 변환 함수를 추가한다.

```python
# ═══════════════════════════════════════════════════════════════════════
# [신규] 누적 데이터 → 프론트엔드 변환
#
# 기존 transform_got_to_graph_data()는 에피소드별 GoT JSON → 프론트 변환.
# 아래 함수는 RDB 누적 데이터 → 프론트엔드 변환.
# 두 함수는 독립적이며 서로를 호출하지 않는다.
# ═══════════════════════════════════════════════════════════════════════


def transform_cumulative_to_frontend(
    nodes: list[dict],
    edges: list[dict],
) -> dict:
    """RDB 누적 노드/엣지 → 프론트엔드 Force-directed 그래프 형식.

    기존 transform_got_to_graph_data()와 동일한 ID 생성 규칙
    (GROUP_PREFIXES + 순번)을 사용한다.

    차이점:
        - 입력: RDB 누적 데이터 (label, grp, weight, mention_count, trend)
        - 출력: 프론트엔드용 (id, name, group, weight, mention_count, trend)
        - 엣지: label 기반 매핑 (GoT id 기반이 아님)
        - val 필드 미사용: 프론트엔드가 weight 원본값으로 노드 크기를 직접 결정

    Args:
        nodes: RDB user_graph_nodes 목록 (사용자 단위 누적 데이터)
        edges: RDB user_graph_edges 목록 (사용자 단위 누적 데이터)

    Returns:
        {"nodes": [...], "links": [...]} 프론트엔드 형식
    """
    group_counters: dict[str, int] = {}
    label_to_id: dict[tuple[str, str], str] = {}  # (label, grp) → frontend_id

    frontend_nodes: list[dict] = []
    for node in nodes:
        grp = node.get("grp", "emotional_exhaustion")
        if grp not in VALID_GROUPS:
            grp = "emotional_exhaustion"

        prefix = GROUP_PREFIXES[grp]
        group_counters[grp] = group_counters.get(grp, 0) + 1
        frontend_id = f"{prefix}{group_counters[grp]}"

        label = node.get("label", "")
        label_to_id[(label, grp)] = frontend_id

        frontend_nodes.append({
            "id": frontend_id,
            "name": label,
            "group": grp,
            "weight": node.get("weight", 0.5),
            "mention_count": node.get("mention_count", 1),
            "trend": node.get("trend", "stable"),
            "first_seen": node.get("first_seen", ""),
            "last_seen": node.get("last_seen", ""),
        })

    frontend_links: list[dict] = []
    for edge in edges:
        source_key = (edge.get("source_label", ""), edge.get("source_group", ""))
        target_key = (edge.get("target_label", ""), edge.get("target_group", ""))
        source_id = label_to_id.get(source_key)
        target_id = label_to_id.get(target_key)

        if source_id and target_id:
            frontend_links.append({
                "source": source_id,
                "target": target_id,
                "weight": edge.get("weight", 1),
                "relationship": edge.get("relationship", "related"),
            })

    return {"nodes": frontend_nodes, "links": frontend_links}
```

### 6.4 수정 파일: `src/api/backend_resources.py` — 상수 추가

```python
# --- 누적 그래프 리소스 (신규) ---
# [Mode A] AI 서버가 누적 데이터를 조회/갱신할 때 사용
RESOURCE_GRAPH_NODES = "graph_nodes"

# [Mode B] AI 서버가 에피소드별 raw 데이터를 전송할 때 사용
RESOURCE_GRAPH_EPISODES = "graph_nodes/episodes"

# Save 타입 상수
TYPE_GRAPH_EPISODE = "graph_episode"       # Mode B 전송 시 사용
TYPE_GRAPH_CUMULATIVE = "graph_cumulative"  # Mode A 전송 시 사용
```

### 6.5 수정 파일: `src/api/client.py` — update 메서드 추가

Mode A에서 PUT 요청을 보내기 위해 `BackendClient`에 `update()` 메서드를 추가한다.

```python
@with_retry(max_retries=3, base_delay=1.0)
async def update(
    self,
    resource: str,
    data: dict[str, Any],
) -> SaveResponse:
    """데이터를 백엔드에 갱신한다 (PUT).

    Mode A(AI 서버 UPSERT)에서 누적 그래프 데이터 갱신에 사용.

    Args:
        resource: 리소스 경로 (예: "graph_nodes")
        data: 갱신할 데이터 dict

    Returns:
        갱신 결과 (SaveResponse)

    Raises:
        httpx.HTTPStatusError: HTTP 에러 응답 시
    """
    response = await self._client.put(
        f"{self._base_url}/{resource}",
        json=data,
    )
    response.raise_for_status()
    return SaveResponse.model_validate(response.json())
```

### 6.6 수정 파일: `src/agents/podcast/podcast_reasoning.py` — 분기 추가

기존 `_save_graph_data()` 메서드를 수정하여 누적 저장을 추가한다.

```python
async def _save_graph_data(
    self,
    got_result: dict[str, Any],
    session_id: str,
    episode_id: str,
    state: AgentState,
) -> None:
    """GoT 결과를 Neo4j + RDB에 저장한다.

    저장 대상:
        1. Neo4j: 에피소드별 개별 노드 (추론 이력 원본, 기존 그대로)
        2. RDB 에피소드 스냅샷: 기존 graph_analyses 전송 (하위 호환)
        3. RDB 누적 그래프: 신규 — label+group 기준 통합 노드/엣지

    세 작업 모두 실패해도 파이프라인은 계속 진행한다.
    """
    # [기존 유지] Neo4j 저장 — 에피소드별 개별 노드
    # [이관 주석] Neo4j를 Backend로 이관 시 이 호출을 삭제한다.
    await self._save_got_to_neo4j(got_result, session_id, episode_id)

    # [기존 유지] RDB 에피소드 스냅샷 — 하위 호환
    # 기존 graph_analyses 테이블에 에피소드별 JSON 블럽 저장.
    # 누적 테이블이 안정화되면 이 호출을 삭제할 수 있다.
    await self._publish_graph_to_backend(got_result, state)

    # [신규] RDB 누적 그래프 — label+group 기준 통합 UPSERT
    # PR #69: graph.upsert_mode 분기 제거, Mode B(Backend UPSERT) 단일 호출.
    from src.api.graph_cumulative import publish_graph_to_rdb
    await publish_graph_to_rdb(got_result, state)
```

---

## 7. 전체 워크플로우

### 7.1 Mode A: AI 서버가 UPSERT

```
사용자 입력
    ↓
TIER 0~1: Intent → Safety/Emotion/Content/Reasoning (병렬)
    ↓
Podcast Reasoning Agent
    ↓ GoT 생성 (LLM)
    ↓ got_result = { nodes: [...], edges: [...] }
    ↓
_save_graph_data() ─────────────────────────────────────────
    │
    ├─ [1] _save_got_to_neo4j()
    │   └─ Neo4j MERGE: GoTNode {got_node_id: "ep5_1", weight: 0.9}
    │      (에피소드별 개별 노드, 기존 그대로)
    │
    ├─ [2] _publish_graph_to_backend()
    │   └─ POST /api/v1/graph_analyses (에피소드 스냅샷, 하위 호환)
    │
    └─ [3] publish_graph_to_rdb() → publish_graph_cumulative_mode_a()
        │
        ├─ GET /api/v1/graph_nodes?user_id=xxx
        │   └─ Backend 응답: 기존 누적 노드/엣지
        │      { nodes: [{label:"업무과부하", weight:0.77, mention_count:2}], edges: [...] }
        │
        ├─ merge_nodes_from_got()
        │   └─ EMA 계산: 0.3×0.9 + 0.7×0.77 = 0.81
        │      mention_count: 2 → 3, trend: "increasing"
        │
        ├─ merge_edges_from_got()
        │   └─ (업무과부하→번아웃) weight: 2 → 3
        │
        └─ PUT /api/v1/graph_nodes
            └─ { nodes: [{label:"업무과부하", weight:0.81, mention_count:3, ...}],
                 edges: [{source_label:"업무과부하", target_label:"번아웃", weight:3}] }

    ↓ (TIER 2~4 계속)

프론트엔드 그래프 조회:
    GET /api/v1/graph_nodes?user_id=xxx
        ↓ Backend: RDB 조회 → 응답
        ↓ AI 서버 또는 Backend: transform_cumulative_to_frontend()
        ↓ 프론트엔드: Force-directed 그래프 렌더링
```

### 7.2 Mode B: Backend가 UPSERT

```
사용자 입력
    ↓
TIER 0~1 → Podcast Reasoning Agent → GoT 생성
    ↓
_save_graph_data() ─────────────────────────────────────────
    │
    ├─ [1] _save_got_to_neo4j() (기존 그대로)
    │
    ├─ [2] _publish_graph_to_backend() (하위 호환)
    │
    └─ [3] publish_graph_to_rdb() → publish_graph_raw_mode_b()
        │
        └─ POST /api/v1/graph_nodes/episodes
            └─ { user_id, session_id, episode_id,
                 got_result: {
                   nodes: [{id:"1", label:"업무과부하", group:"work_structure", intensity:0.9}],
                   edges: [{from:"1", to:"2", relationship:"causes"}]
                 }}
            ↓
        Backend 서버 (내부 처리):
            ├─ 기존 user_graph_nodes에서 (user_id, label, grp) 조회
            ├─ EMA 계산: calc_ema(old_weight, intensity)
            ├─ UPSERT user_graph_nodes
            └─ UPSERT user_graph_edges

프론트엔드 그래프 조회:
    GET /api/v1/graph_nodes?user_id=xxx
        ↓ (Mode A와 동일)
```

### 7.3 Neo4j 이관 시 변경 사항

Neo4j를 Backend로 이관하면 AI 서버에서 변경할 부분:

```python
async def _save_graph_data(self, got_result, session_id, episode_id, state):
    # [삭제] Neo4j 저장
    # await self._save_got_to_neo4j(got_result, session_id, episode_id)

    # [삭제 가능] 에피소드 스냅샷 (누적 테이블이 대체)
    # await self._publish_graph_to_backend(got_result, state)

    # [유지] RDB 누적 그래프
    from src.api.graph_cumulative import publish_graph_to_rdb
    await publish_graph_to_rdb(got_result, state)
```

삭제 대상:
- `_save_got_to_neo4j()` 메서드 전체
- `_publish_graph_to_backend()` 메서드 (선택: 누적 테이블 안정화 후)
- `routes/graph.py` 라우터 전체 (Backend가 직접 RDB 조회)
- Neo4j Cypher 상수 (`CYPHER_USER_GRAPH` 등)

유지 대상:
- `graph_cumulative.py` 전체
- `graph_transformer.py`의 `transform_cumulative_to_frontend()`, `validate_group()`
- `backend_resources.py`의 `RESOURCE_GRAPH_NODES`

---

## 8. 설정 (config/settings.yaml)

> **PR #69 반영**: `graph.upsert_mode` 및 `graph.ema_alpha` 설정은 삭제됨.
> EMA 계산은 Backend 책임으로 이관. 아래는 설계 당시 원본 (역사적 참고).

```yaml
# === 그래프 누적 저장 설정 (삭제됨 — PR #69) ===
# graph:
#   upsert_mode: "backend"  # Mode B 확정, 설정 자체 불필요로 제거
#   ema_alpha: 0.3           # Backend 책임으로 이관, AI 서버 config에서 제거
```

---

## 9. 에러 처리 및 복원력

### 9.1 Graceful Degradation

모든 RDB 누적 저장은 실패해도 파이프라인을 중단하지 않는다.

| 실패 지점 | 영향 | 복구 |
|-----------|------|------|
| Mode A: GET 조회 실패 | 누적 갱신 안 됨 | 다음 에피소드에서 재시도 |
| Mode A: PUT 전송 실패 | 계산은 됐지만 저장 안 됨 | 다음 에피소드에서 재시도 |
| Mode B: POST 전송 실패 | Backend가 이번 에피소드를 모름 | 다음 에피소드에서 재시도 |
| Neo4j 저장 실패 | 추론 이력만 누락 | RDB 누적 데이터에 영향 없음 |

### 9.2 데이터 정합성

- Neo4j와 RDB는 **독립적**이다. 한쪽 실패가 다른 쪽에 영향을 주지 않는다.
- Mode A에서 GET 성공 후 PUT 실패 시, 다음 에피소드의 GET에서 이전 상태를 다시 받으므로 데이터가 유실되지 않는다. 단, 해당 에피소드의 intensity가 누적에 반영되지 않는다.
- 최악의 경우에도 Neo4j에 에피소드별 원본이 있으므로, 필요 시 누적 테이블을 Neo4j로부터 재구축할 수 있다.

---

## 10. 기존 코드와의 호환성

### 10.1 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `src/agents/shared/base_agent.py` | 공용 인프라, 수정 불가 |
| `src/models/agent_state.py` | Protected File |
| `src/models/message.py` | Protected File |
| `src/api/contracts.py` | Protected File (SaveRequest/LoadResponse 그대로 사용) |
| `src/db/neo4j_client.py` | Neo4j 저장 로직 변경 없음 |

### 10.2 수정 파일 요약

| 파일 | 변경 내용 | 영향 범위 |
|------|----------|----------|
| `src/api/graph_cumulative.py` | **신규 생성** — 누적 UPSERT 로직 | 독립 모듈 |
| `src/api/graph_transformer.py` | `transform_cumulative_to_frontend()` 추가 | 기존 함수 미변경 |
| `src/api/backend_resources.py` | 리소스 상수 3개 추가 | 추가만, 기존 미변경 |
| `src/api/client.py` | `update()` 메서드 추가 | 추가만, 기존 미변경 |
| `src/agents/podcast/podcast_reasoning.py` | `_save_graph_data()`에 1줄 추가 | 기존 흐름 유지 |
| `config/settings.yaml` | `graph` 섹션 추가 | 기존 설정 미변경 |

### 10.3 함수 사용 가이드

```
┌─────────────────────────────────────────────────────────┐
│ 확정된 모드에 따라 사용할 함수:                              │
│                                                         │
│ ■ AI 서버가 UPSERT (Mode A):                             │
│   publish_graph_cumulative_mode_a()                     │
│   → 내부에서 merge_nodes_from_got(), calc_ema() 사용     │
│   → Backend API: GET + PUT /api/v1/graph_nodes          │
│                                                         │
│ ■ Backend가 UPSERT (Mode B):                             │
│   publish_graph_raw_mode_b()                            │
│   → group 검증만 수행, EMA 미계산                         │
│   → Backend API: POST /api/v1/graph_nodes/episodes      │
│   → Backend에 인계: calc_ema(), calc_trend(),            │
│     validate_group(), KEYWORD_MAP                       │
│                                                         │
│ ■ 디스패처 (PR #69 이후: Mode B 직접 호출):                │
│   publish_graph_to_rdb()                                │
│   → Mode B 직접 호출 (upsert_mode 분기 제거됨)            │
│                                                         │
│ ■ 프론트엔드 변환:                                        │
│   transform_cumulative_to_frontend()                    │
│   → RDB 누적 데이터 → 프론트엔드 {nodes, links} 변환     │
└─────────────────────────────────────────────────────────┘
```

---

## 11. 백엔드 팀 협의 사항

### 11.1 필수 협의

| 항목 | 내용 | 긴급도 |
|------|------|--------|
| `user_graph_nodes` 테이블 생성 | 섹션 3.1 DDL 검토 및 마이그레이션 | 높음 |
| `user_graph_edges` 테이블 생성 | 섹션 3.2 DDL 검토 및 마이그레이션 | 높음 |
| GET `/api/v1/graph_nodes` 엔드포인트 | 섹션 5.1 스펙 기반 구현 | 높음 |
| Mode 확정 (A or B) | 어느 쪽이 UPSERT를 담당할지 | 높음 |

### 11.2 Mode별 추가 협의

**Mode A 확정 시:**
| 항목 | 내용 |
|------|------|
| PUT `/api/v1/graph_nodes` | 섹션 5.2 스펙 기반 구현 |
| 기존 행 유지 로직 | PUT에 포함되지 않은 기존 노드는 삭제하지 않고 유지 |

**Mode B 확정 시:**
| 항목 | 내용 |
|------|------|
| POST `/api/v1/graph_nodes/episodes` | 섹션 5.3 스펙 기반 구현 |
| EMA 로직 인계 | 섹션 11.4 인계 파일 참조 |
| UPSERT 구현 | Backend가 수신 시 `user_graph_nodes`/`user_graph_edges` UPSERT |

### 11.3 프론트엔드 ID 변환 위치

| Mode | ID 변환 위치 | 함수 |
|------|-------------|------|
| A | AI 서버 (routes/graph.py 또는 별도 엔드포인트) | `transform_cumulative_to_frontend()` |
| B | Backend 서버 | `transform_cumulative_to_frontend()` 로직 인계 |

### 11.4 Mode B 인계 파일 상세

Mode B 확정 시, AI 서버의 두 파일에 흩어진 함수를 **Backend가 필요한 것만
추출하여 독립 파일 1개로 전달**한다.

#### 추출 대상 판단 기준

AI 서버의 `graph_transformer.py`와 `graph_cumulative.py`에는 Backend에 불필요한
AI 서버 전용 함수가 섞여 있다. 파일 전체를 넘기면 사용하지 않는 코드까지
포함되어 유지보수 혼란이 생기므로, 필요한 것만 골라서 전달한다.

```
graph_transformer.py (AI 서버)
├── VALID_GROUPS                          → 인계 대상 ✓
├── KEYWORD_MAP                           → 인계 대상 ✓
├── GROUP_PREFIXES                        → 인계 대상 ✓ (프론트 ID 변환용)
├── validate_group()                      → 인계 대상 ✓
├── intensity_to_val()                    → 불필요 ✗ (프론트가 weight 원본값 사용)
├── calc_category_distribution()          → 인계 대상 ✓
├── transform_got_to_graph_data()         → 불필요 ✗ (에피소드별 변환, AI 서버 전용)
└── transform_neo4j_rows_to_graph_data()  → 불필요 ✗ (Neo4j 직접 쿼리용)

graph_cumulative.py (설계서)
├── calc_ema()                            → 인계 대상 ✓
├── calc_trend()                          → 인계 대상 ✓
├── merge_nodes_from_got()                → 인계 대상 ✓ (UPSERT 핵심 로직)
├── merge_edges_from_got()                → 인계 대상 ✓
├── publish_graph_cumulative_mode_a()     → 불필요 ✗ (Mode A 전용, AI 서버 내부)
├── publish_graph_raw_mode_b()            → 불필요 ✗ (AI 서버 → Backend 전송)
└── publish_graph_to_rdb()                → 불필요 ✗ (Mode 디스패처, AI 서버 내부)
```

#### 이식 가능 여부

인계 대상 함수/상수는 모두 **순수 함수 또는 순수 상수**이다.

| 함수/상수 | 외부 import | AI 서버 모듈 의존 | Python 표준 라이브러리만 사용 |
|-----------|------------|------------------|---------------------------|
| `VALID_GROUPS` | 없음 | 없음 | O (frozenset) |
| `KEYWORD_MAP` | 없음 | 없음 | O (dict) |
| `GROUP_PREFIXES` | 없음 | 없음 | O (dict) |
| `validate_group()` | 위 상수만 참조 | 없음 | O |
| `calc_ema()` | 없음 | 없음 | O (산술) |
| `calc_trend()` | 없음 | 없음 | O (비교) |
| `merge_nodes_from_got()` | `datetime` (표준) | 없음 | O |
| `merge_edges_from_got()` | `datetime` (표준) | 없음 | O |
| `calc_category_distribution()` | 없음 | 없음 | O |
| `transform_cumulative_to_frontend()` | 위 함수만 참조 | 없음 | O |

AI 서버의 `config.loader`, `src.agents`, `src.db`, `src.models` 등
**어떤 내부 모듈에도 의존하지 않으므로** Backend가 그대로 복사하여 사용할 수 있다.

Backend가 Java/Spring이면 로직만 동일하게 재구현하면 된다.
Backend가 Python이면 파일 그대로 사용 가능하다.

#### 인계 파일 구성

Backend 팀에 전달할 파일은 **1개**로, 아래 구조를 따른다:

```
graph_domain_logic.py (인계 파일명은 Backend 팀 컨벤션에 맞춤)
│
├── 상수 (3개)
│   ├── VALID_GROUPS       — grp 컬럼 유효값 6종
│   ├── KEYWORD_MAP        — group 보정용 키워드 28개
│   └── GROUP_PREFIXES     — 프론트엔드 노드 ID prefix 규칙
│
├── 검증 함수 (1개)
│   └── validate_group()   — LLM group 검증 + keyword fallback
│
├── EMA 함수 (2개)
│   ├── calc_ema()         — 지수이동평균 계산
│   └── calc_trend()       — weight 변화 방향 판정
│
├── UPSERT 병합 함수 (2개) — POST 수신 시 호출
│   ├── merge_nodes_from_got()  — GoT 노드 + 기존 노드 → 갱신 목록
│   └── merge_edges_from_got()  — GoT 엣지 + 기존 엣지 → 갱신 목록
│
├── 집계 함수 (1개)
│   └── calc_category_distribution() — group별 노드 수 집계
│
└── 프론트엔드 변환 함수 (1개) — GET 응답 시 호출
    └── transform_cumulative_to_frontend() — RDB 데이터 → 프론트 JSON
```

#### Backend 사용 흐름

```
POST /api/v1/graph_nodes/episodes 수신
    ↓
1. got_result에서 각 노드의 group 검증
   → validate_group(node)  [AI 서버에서 이미 검증하지만 이중 안전장치]
    ↓
2. RDB에서 기존 누적 노드/엣지 SELECT
   → SELECT * FROM user_graph_nodes WHERE user_id = ?
   → SELECT * FROM user_graph_edges WHERE user_id = ?
    ↓
3. 병합 함수 호출
   → updated_nodes = merge_nodes_from_got(got_result, existing_nodes)
   → updated_edges = merge_edges_from_got(got_result, existing_edges)
    ↓
4. UPSERT 실행
   → INSERT ... ON DUPLICATE KEY UPDATE (updated_nodes 기반)
   → INSERT ... ON DUPLICATE KEY UPDATE (updated_edges 기반)
```

```
GET /api/v1/graph_nodes?user_id=xxx 수신
    ↓
1. RDB에서 해당 사용자의 누적 노드/엣지 SELECT
   → SELECT * FROM user_graph_nodes WHERE user_id = ?
   → SELECT * FROM user_graph_edges WHERE user_id = ?
   (에피소드 단위가 아닌, 사용자의 전체 누적 그래프를 조회)
    ↓
2. 프론트엔드 변환 (val 미사용, weight 원본값 전달)
   → result = transform_cumulative_to_frontend(nodes, edges)
   → dist = calc_category_distribution(nodes)
    ↓
3. JSON 응답 반환
   → {"success": true, "data": [{"nodes": result["nodes"], "links": result["links"],
       "category_distribution": dist}], "total": len(nodes), "page": 1}

향후 조직 단위 조회 확장:
   GET /api/v1/graph_nodes?org_id=xxx
   → SELECT * FROM user_graph_nodes WHERE user_id IN (SELECT user_id FROM org_members WHERE org_id = ?)
```

#### 동기화 규칙

인계 후 AI 서버와 Backend 양쪽에 같은 로직이 존재하게 된다.
변경 시 반드시 양쪽을 동기화해야 한다:

| 변경 사항 | AI 서버 수정 위치 | Backend 수정 위치 | 비고 |
|-----------|------------------|------------------|------|
| 새 group 추가 | `VALID_GROUPS`, `GROUP_PREFIXES` | 인계 파일 동일 상수 | RDB DDL도 변경 |
| 키워드 추가 | `KEYWORD_MAP` | 인계 파일 동일 상수 | |
| EMA α 변경 | `config/settings.yaml` | Backend 설정 | 양쪽 같은 값 유지 |
| Trend 임계값 변경 | `calc_trend()` | 인계 파일 동일 함수 | |

---

*마지막 업데이트: 2026-04-06*

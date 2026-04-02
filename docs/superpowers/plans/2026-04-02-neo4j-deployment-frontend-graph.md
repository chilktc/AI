# Neo4j 배포 + 프론트엔드 그래프 데이터 서빙 계획 (v3)

> **v3 업데이트**: 이관 시 삭제 코드 명시, Sonnet 모델 변경 테스트 계획, 구현 근거 상세화, 과거 모델 테스트 오류 재발 방지

---

## Context

Neo4j를 AI서버(app-2)에 Docker로 배포하되, 향후 Backend(app-3)로 이관 가능하도록 설계한다.
파이프라인 실행 후 GoT 데이터가 Neo4j에 저장되는지 검증하고, 프론트엔드 그래프 시각화 데이터를 제공한다.

### 현재 아키텍처

```
Frontend(app-4:3000) → Backend(app-3:8080) ↔ AI서버(app-2:8000) ↔ Neo4j(로컬 Docker)
                                    ↓
                                   MySQL
```

### 프론트엔드 요구 데이터 (3가지)

1. **Force-directed 그래프**: `{ nodes: [{id, name, group, val}], links: [{source, target}] }`
2. **자주 연결된 키워드**: `[{ tags: string[], count: number }]` — 다중 에피소드 누적
3. **카테고리 분포 도넛차트**: 6개 group별 count

### 핵심 갭 분석

| 항목 | 현재 상태 | 갭 | 근본 원인 |
|------|----------|-----|----------|
| GoT 노드 type | `emotion\|action\|concept\|experience` (4개) | 프론트엔드 6개 group과 **직교** | type=인지 유형, group=직장 도메인. 서로 다른 분류 축 |
| GoT `group` 필드 | 없음 | 추가 필요 | 프롬프트에 정의 없음 |
| GoT → Neo4j | AgentState JSON에만 존재 | Neo4j 미저장 | `_save_got_to_neo4j()` 미구현 |
| 자주 연결된 키워드 | 단일 에피소드만 | count 불가 | GoT edges는 고유 관계만, 중복 미기록 |
| 모델 정확도 | Haiku (composite 0.667) | group 오분류 5-10% | Haiku는 다중 분류 정확도 낮음 |

---

## Phase 1: Neo4j Docker 배포 + 스키마 생성

### 1-1. docker-compose.yml Neo4j 서비스 활성화

**파일**: `docker-compose.yml`
**근거**: Neo4j 코드(neo4j_client.py, init.cypher, 통합 테스트)가 이미 완성되어 있으나 docker-compose에서 주석 처리 상태. 활성화만 하면 즉시 사용 가능.

변경사항:
- L36-64: Neo4j 서비스 블록 주석 해제
- L19-21: `depends_on.neo4j` 주석 해제
- AI서버 `mem_limit`: `2000m` → `1500m`

```yaml
# [이관 주석] Neo4j를 Backend(app-3)로 이관 시:
# 1. 아래 neo4j 서비스 블록 전체 삭제
# 2. ai-server의 depends_on.neo4j 삭제
# 3. ai-server mem_limit를 2000m으로 복원
# 4. .env에서 STORAGE_MODE=proxy로 변경
```

> **메모리**: AI(1.5GB) + Neo4j(1GB) + OS(0.5GB) = 3GB / 4GB. 여유 1GB.
> t3.large(8GB) 업그레이드 권장. OOM 시 AI서버 `mem_limit`를 우선 복원.

### 1-2. 환경변수 설정

**파일**: `.env`

```bash
NEO4J_URL=bolt://neo4j:7687      # Docker 내부 네트워크
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secure-password>
STORAGE_MODE=local                 # AI서버 직접 접속

# [이관 주석] Backend 이관 시:
# STORAGE_MODE=proxy 로 변경
# NEO4J_* 변수 3개 삭제 (Backend가 관리)
```

### 1-3. 스키마 초기화 + group 인덱스 추가

**파일**: `dev/local_db/neo4j/init.cypher`

기존 스키마(제약 5개 + 인덱스 6개) 실행 후, 프론트엔드 카테고리 쿼리용 인덱스 추가:

```cypher
CREATE INDEX got_group IF NOT EXISTS
  FOR (g:GoTNode) ON (g.group);
```

**근거**: 카테고리 분포 쿼리(`RETURN g.group, count(*)`)에서 group 인덱스 없으면 전체 스캔 발생.

### 1-4. 시드 데이터 적재 + 검증

```bash
docker compose up -d
docker exec -i mindlog-neo4j cypher-shell -u neo4j -p <pw> < dev/local_db/neo4j/init.cypher
python -m dev.local_db.seed --neo4j
# 검증
docker exec -i mindlog-neo4j cypher-shell -u neo4j -p <pw> "MATCH (n) RETURN labels(n), count(n)"
```

---

## Phase 2: 모델 변경 (Haiku → Sonnet) + 테스트

### 2-0. 모델 변경이 필요한 이유

**현재**: `podcast_reasoning`은 **Haiku** (composite score 0.667)
**문제**: GoT 프롬프트에 `group` 필드(6개 카테고리 분류)를 추가하면:
- Haiku 오분류율 5-10% 예상 (경량 모델의 다중 분류 한계)
- 후처리 보정으로 완화 가능하나, 1차 분류 정확도가 낮으면 보정 부담 증가

**과거 교훈**: Round 4 프롬프트 최적화에서 모델 해상도 버그(`llm_client.py` agent_config.model_id 우선 → provider별 getter 직접 호출)로 시간 허비. 이번에는 설정 변경 → 단위 검증 → 통합 테스트 순서를 엄격히 따른다.

### 2-1. 설정 변경

**파일**: `config/settings.yaml` (L113-118)

```yaml
# 변경 전
podcast_reasoning:
  model: haiku
  max_tokens: 4096    # Haiku 최대 출력 한계
  temperature: 0.3

# 변경 후
podcast_reasoning:
  model: sonnet_37              # haiku → sonnet_37
  max_tokens: 6000              # 4096 → 6000 (group 필드 추가로 출력 증가 대비)
  temperature: 0.3              # 유지 (추론 특성상 낮은 값 적절)
  full_threshold: 0.0           # 유지
  standard_threshold: 0.0       # 유지
```

**변경 근거**:

| 설정 | 변경 | 근거 |
|------|------|------|
| `model` | `haiku` → `sonnet_37` | 6개 카테고리 분류 정확도 향상 (0.667 → 0.8+). safety, intent_classifier도 sonnet_37 사용 중 |
| `max_tokens` | `4096` → `6000` | 현재 GoT+ToT+CoT 출력 ~3100토큰. group/name 필드 추가 시 ~3500-4000. 4096은 여유 부족(6%). 6000으로 40%+ 마진 확보 |
| `temperature` | `0.3` 유지 | 추론 에이전트는 일관성이 중요. Sonnet 에이전트 중 가장 낮은 temperature 설정이며, 이는 의도적 |

**영향 범위**: `podcast_reasoning`만 변경. 다른 에이전트는 무관.

**Sonnet 모델 ID 확인** (settings.yaml L14-35에 이미 정의됨):
```yaml
models:
  sonnet_37: "claude-3-7-sonnet-20250219"
bedrock_models:
  sonnet_37: "apac.anthropic.claude-3-7-sonnet-20250219-v1:0"
```

### 2-2. 모델 변경 단위 검증 (과거 오류 재발 방지) ★

**과거 문제**: `llm_client.py`에서 모델 해상도 시 `agent_config.model_id`가 우선되어 provider별 getter가 무시되는 버그. 이미 수정 완료이나, 변경 후 반드시 검증.

```bash
# Step 1: 모델 ID 해상도 검증 (가장 먼저 확인)
python -c "
from config.loader import get_settings
s = get_settings()
cfg = s.get_agent_config('podcast_reasoning')
print('model key:', cfg.get('model'))
print('max_tokens:', cfg.get('max_tokens'))
print('anthropic:', s.get_model_id(cfg['model']))
print('bedrock:', s.get_bedrock_model_id(cfg['model']))
"
# 기대 출력:
# model key: sonnet_37
# max_tokens: 6000
# anthropic: claude-3-7-sonnet-20250219
# bedrock: apac.anthropic.claude-3-7-sonnet-20250219-v1:0
```

```bash
# Step 2: LLMClient 초기화 검증
python -c "
from src.agents.shared.llm_client import LLMClient
client = LLMClient(agent_name='podcast_reasoning')
print('model_id:', client._model_id)
print('max_tokens:', client._max_tokens)
print('temperature:', client._temperature)
print('provider:', client._provider)
"
```

```bash
# Step 3: 기존 단위 테스트 통과 확인
pytest tests/agents/test_podcast_reasoning.py -v
```

**실패 시 조치**:
- model_id가 `haiku`로 출력되면: settings.yaml 변경이 반영 안 된 것. `_settings_instance = None` 리셋 필요
- Bedrock model_id가 잘못된 경우: `bedrock_models.sonnet_37` 키 확인

### 2-3. 성능 비교 테스트 (Haiku vs Sonnet)

```bash
# Haiku 베이스라인 (변경 전 5회)
python -m dev.live_tests.run_prompt_iteration \
  --ca-version 2.1.0 --pr-version 3.0.0 --bv-version 2.3.0 \
  --iteration 70 --round 5 --repeat 5

# Sonnet 테스트 (변경 후 5회)
python -m dev.live_tests.run_prompt_iteration \
  --ca-version 2.1.0 --pr-version 3.0.0 --bv-version 2.3.0 \
  --iteration 75 --round 5 --repeat 5
```

**수집 메트릭 + 합격 기준**:

| 메트릭 | Haiku 베이스라인 | Sonnet 합격 기준 | 롤백 기준 |
|--------|----------------|-----------------|----------|
| bv_score | 0.84-0.86 | ≥ 0.82 | < 0.78 (2회 연속) |
| confidence | 0.85 | ≥ 0.83 | < 0.75 |
| 실행 시간 | ~77초 (Bedrock) | ≤ 90초 | > 120초 |
| JSON 파싱 오류 | 0% | ≤ 5% | > 10% |
| GoT 노드 수 | 5-8개 | 5-8개 | < 3개 or > 12개 |

**테스트 순서가 중요한 이유**: Round 4에서 28회 반복에 ~2시간 소요. 이번에는 Haiku 5회 → Sonnet 5회 → 비교 → 판단. 총 10회(~15분)로 최소 검증.

### 2-4. Bedrock 서울 리전 주의사항

- **프롬프트 캐싱**: 서울(ap-northeast-2)에서 Bedrock cachePoint **미지원** → 캐싱 관련 설정 무시
- **APAC CRIS**: Sonnet 3.7은 Cross-Region Inference Profile 필수. `bedrock_models.sonnet_37`에 `apac.` prefix 이미 설정됨
- **레이턴시**: CRIS 경유 시 ~50ms 추가. 전체 파이프라인에 미미한 영향

### 2-5. 롤백 계획

```yaml
# 롤백: settings.yaml을 원래 값으로 복원
podcast_reasoning:
  model: haiku
  max_tokens: 4096
  temperature: 0.3
```

롤백 조건:
1. bv_score 2회 연속 < 0.78
2. JSON 파싱 오류율 > 10%
3. 실행 시간 > 120초 (현재 77초 대비 55%+ 증가)

---

## Phase 3: GoT 프롬프트 확장 + 데이터 변환

### 3-1. GoT 프롬프트에 `group` 필드 추가

**파일**: `prompts/podcast/podcast_reasoning.yaml`
**담당**: 개발자3
**버전**: v3.1.0 (새 버전)

**변경 전** (v3.0.0):
```json
{"id": "1", "type": "emotion", "label": "배신감", "intensity": 0.9}
```

**변경 후** (v3.1.0):
```json
{"id": "1", "type": "emotion", "label": "배신감", "intensity": 0.9, "group": "peer_relations"}
```

프롬프트 추가 지시문:
```
각 노드에 group 필드를 추가하세요. 반드시 다음 6개 중 하나:
- work_structure: 업무 구조 문제 (과부하, 모호성, 병목, 독박책임, 목표상실)
- leadership: 리더십 문제 (상하압박, 과잉배려, 과잉간섭, 책임회피, 권위실추)
- peer_relations: 동료 관계 문제 (신뢰균열, 성과다툼, 소통단절, 세대갈등, 갈라치기)
- career_growth: 커리어 성장 문제 (성장정체, 전문성고갈, 가면증후군, 도구화, 방향상실)
- culture_system: 조직문화/제도 문제 (보상결핍, 불공정성, 사일로현상, 형식주의, 사내정치)
- emotional_exhaustion: 정서적 소진 (번아웃, 가면우울, 고립감, 만성불안, 회의감)
```

**근거**: 프롬프트에 6개 enum + 각 5개 예시를 명시하면 Sonnet 3.7은 95%+ 정확도 기대. Haiku(85-90%)보다 현저히 높음. 이것이 Phase 2에서 모델을 먼저 변경하는 이유.

**설정 반영** (settings.yaml의 prompts.versions):
```yaml
prompts:
  versions:
    podcast_reasoning: "3.1.0"  # 3.0.0 → 3.1.0
```

### 3-2. 후처리 검증/보정 레이어

**신규 파일**: `src/api/graph_transformer.py`
**근거**: LLM이 group을 잘못 생성할 수 있으므로(Sonnet도 5% 미만이지만 0%는 아님), 규칙 기반 보정이 필수. 또한 GoT의 id/label/intensity/edges 형식을 프론트엔드의 id/name/group/val/links로 변환하는 레이어 필요.

```python
"""
GoT 출력 → 프론트엔드 그래프 데이터 변환 + group 검증.

[이관 주석] 이 파일은 Neo4j 위치와 무관하게 항상 필요.
GoT JSON → 프론트엔드 형식 변환은 AI서버의 책임.
"""

VALID_GROUPS = frozenset({
    "work_structure", "leadership", "peer_relations",
    "career_growth", "culture_system", "emotional_exhaustion",
})

# 키워드 → group 매핑 사전 (30개 대표 키워드)
# GoT의 label에 포함된 키워드로 group을 유추한다.
KEYWORD_MAP: dict[str, str] = {
    # work_structure
    "과부하": "work_structure", "업무과중": "work_structure",
    "야근": "work_structure", "리소스부족": "work_structure",
    "모호": "work_structure", "병목": "work_structure",
    "독박": "work_structure", "목표상실": "work_structure",
    # leadership
    "상사": "leadership", "압박": "leadership",
    "과잉간섭": "leadership", "책임회피": "leadership",
    "권위": "leadership", "피드백부족": "leadership",
    # peer_relations
    "신뢰": "peer_relations", "갈등": "peer_relations",
    "소통단절": "peer_relations", "뒷담화": "peer_relations",
    "배신": "peer_relations", "책임전가": "peer_relations",
    # career_growth
    "성장정체": "career_growth", "전문성": "career_growth",
    "가면증후군": "career_growth", "역량불안": "career_growth",
    # culture_system
    "보상": "culture_system", "불공정": "culture_system",
    "복지": "culture_system", "연차": "culture_system",
    # emotional_exhaustion
    "번아웃": "emotional_exhaustion", "우울": "emotional_exhaustion",
    "고립": "emotional_exhaustion", "불안": "emotional_exhaustion",
    "무기력": "emotional_exhaustion",
}

# 프론트엔드 더미 데이터의 ID prefix 규칙과 동일
GROUP_PREFIXES: dict[str, str] = {
    "work_structure": "b",
    "leadership": "p",
    "peer_relations": "y",
    "career_growth": "g",
    "culture_system": "pk",
    "emotional_exhaustion": "br",
}


def validate_group(node: dict) -> str:
    """LLM이 생성한 group을 검증. 실패 시 label 키워드로 재분류."""
    group = node.get("group", "")
    if group in VALID_GROUPS:
        return group
    # fallback: label에서 키워드 매칭
    label = node.get("label", "")
    for keyword, mapped_group in KEYWORD_MAP.items():
        if keyword in label:
            return mapped_group
    return "emotional_exhaustion"  # 최종 기본값


def intensity_to_val(intensity: float) -> int:
    """intensity(0.0~1.0) → 프론트엔드 val(20/50/100).
    프론트엔드가 val을 100/50/20으로 분류하므로 3단계 매핑."""
    if intensity >= 0.75:
        return 100
    if intensity >= 0.45:
        return 50
    return 20


def transform_got_to_graph_data(got_result: dict) -> dict:
    """GoT JSON → 프론트엔드 { nodes, links } 변환.

    변환 규칙:
    - id: "1","2" → "b1","p1" (group prefix + 순번)
    - label → name
    - type은 유지하지 않음 (프론트엔드 미사용)
    - intensity → val (100/50/20 3단계)
    - edges.from/to → links.source/target (키 변환 + ID 재매핑)
    """
    group_counters: dict[str, int] = {}
    id_map: dict[str, str] = {}  # GoT id → frontend id

    nodes = []
    for node in got_result.get("nodes", []):
        group = validate_group(node)
        prefix = GROUP_PREFIXES[group]
        group_counters[group] = group_counters.get(group, 0) + 1
        new_id = f"{prefix}{group_counters[group]}"
        id_map[str(node["id"])] = new_id
        nodes.append({
            "id": new_id,
            "name": node.get("label", ""),
            "group": group,
            "val": intensity_to_val(node.get("intensity", 0.5)),
        })

    links = []
    for edge in got_result.get("edges", []):
        source = id_map.get(str(edge.get("from", "")))
        target = id_map.get(str(edge.get("to", "")))
        if source and target:
            links.append({"source": source, "target": target})

    return {"nodes": nodes, "links": links}


def calc_category_distribution(nodes: list[dict]) -> dict[str, int]:
    """group별 노드 수 집계 (단일 에피소드에서도 계산 가능)."""
    dist: dict[str, int] = {}
    for node in nodes:
        g = node.get("group", "emotional_exhaustion")
        dist[g] = dist.get(g, 0) + 1
    return dist
```

### 3-3. GoT 프롬프트 v3.1.0 전용 테스트

Phase 2에서 Sonnet 모델 검증 완료 후, v3.1.0 프롬프트로 추가 테스트:

```bash
# v3.1.0 프롬프트 테스트 (5회)
python -m dev.live_tests.run_prompt_iteration \
  --ca-version 2.1.0 --pr-version 3.1.0 --bv-version 2.3.0 \
  --iteration 80 --round 5 --repeat 5
```

**추가 검증 항목**:

| 항목 | 합격 기준 |
|------|----------|
| group 유효성 (6개 enum 내) | ≥ 90% 노드 |
| group 보정 후 유효성 | 100% |
| bv_score (기존 대비) | ≥ 0.80 (v3.0.0 대비 -0.04 이내) |
| 출력 토큰 증가 | ≤ 20% 증가 (max_tokens 6000 이내) |

---

## Phase 4: 파이프라인 → Neo4j 저장 + Backend 전송

### 4-1. `_save_got_to_neo4j()` 구현

**파일**: `src/agents/podcast/podcast_reasoning.py`
**담당**: 개발자3

```python
async def _save_got_to_neo4j(
    self,
    got_result: dict[str, Any],
    session_id: str,
    episode_id: str,
) -> None:
    """GoT 노드/엣지를 Neo4j에 저장한다.

    실패해도 파이프라인은 계속 진행한다 (graceful degradation).

    [이관 주석] Neo4j를 Backend로 이관 시:
    - 이 메서드는 삭제한다.
    - 대신 Phase 4-2의 Backend 전송만 유지한다.
    - factory.create_graph_client()가 GraphProxyClient를 반환하므로
      STORAGE_MODE=proxy로 변경하면 이 메서드가 자동으로 Backend를 경유하지만,
      성능상 직접 SaveRequest로 전송하는 4-2 방식이 더 효율적이다.
    """
    try:
        from src.db.factory import create_graph_client
        async with create_graph_client() as client:
            for node in got_result.get("nodes", []):
                await client.execute_query(
                    "MERGE (g:GoTNode {got_node_id: $id}) "
                    "SET g.node_type = $type, g.label = $label, "
                    "g.weight = $intensity, g.episode_id = $episode_id, "
                    "g.group = $group",
                    params={
                        "id": f"{episode_id}_{node['id']}",
                        "type": node.get("type", "concept"),
                        "label": node.get("label", ""),
                        "intensity": node.get("intensity", 0.5),
                        "episode_id": episode_id,
                        "group": node.get("group", "emotional_exhaustion"),
                    },
                )
            for edge in got_result.get("edges", []):
                await client.execute_query(
                    "MATCH (a:GoTNode {got_node_id: $from_id}), "
                    "(b:GoTNode {got_node_id: $to_id}) "
                    "MERGE (a)-[:LEADS_TO {relationship: $rel}]->(b)",
                    params={
                        "from_id": f"{episode_id}_{edge['from']}",
                        "to_id": f"{episode_id}_{edge['to']}",
                        "rel": edge.get("relationship", "related"),
                    },
                )
            # Session → GoTNode 관계
            await client.execute_query(
                "MATCH (s:Session {session_id: $sid}), (g:GoTNode) "
                "WHERE g.episode_id = $eid "
                "MERGE (s)-[:REASONED_BY]->(g)",
                params={"sid": session_id, "eid": episode_id},
            )
    except Exception as e:
        self.logger.warning("Neo4j 저장 실패 (파이프라인 계속): %s", e)
```

**근거**: GoT 주석(L253-254)에 "향후 Neo4j 통합 시 그대로 사용 가능"이라 명시. 이미 Neo4j 호환 JSON으로 설계됨.

### 4-2. Backend에도 전송 (이관 대비 이중 저장) ★

**근거**: 프론트엔드는 Backend에서만 데이터를 조회한다. Neo4j가 어디에 있든 Backend에 데이터가 있어야 한다. 기존 Emotion/ContentAnalyzer와 동일한 `AgentDataPublisher` 패턴 사용.

**파일 변경**: `src/api/backend_resources.py`

```python
# [이관 주석] 이 리소스는 Neo4j 위치와 무관하게 항상 필요.
# Backend가 프론트엔드에 그래프 데이터를 서빙하기 위해 사용.
RESOURCE_GRAPH_ANALYSIS = "graph_analyses"
TYPE_GRAPH_ANALYSIS = "graph_analysis"
```

**podcast_reasoning.py process() 내에서 호출**:

```python
# GoT 완료 후, 변환 + 저장
from src.api.graph_transformer import transform_got_to_graph_data, calc_category_distribution

transformed = transform_got_to_graph_data(got_result)
category_dist = calc_category_distribution(transformed["nodes"])

# [이관 주석] 아래 Neo4j 저장은 이관 후 삭제. Backend 전송만 유지.
await self._save_got_to_neo4j(got_result, session_id, episode_id)

# Backend 전송 (항상 유지)
publisher = AgentDataPublisher()
await publisher.publish(
    resource=RESOURCE_GRAPH_ANALYSIS,
    data={
        "got_result": got_result,
        "graph_data": transformed,
        "category_distribution": category_dist,
    },
    user_id=state.get("user_id", ""),
    session_id=state.get("session_id", ""),
)
```

---

## Phase 5: 다중 에피소드 누적 + 조회 API

### 5-1. 누적 Cypher 쿼리

**근거**: "자주 연결된 키워드"(count=5회 등)는 단일 에피소드에서 생성 불가. 다중 에피소드의 GoTNode를 Neo4j에서 집계해야 한다.

```cypher
-- 1. 자주 연결된 키워드
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g1:GoTNode)-[:LEADS_TO]->(g2:GoTNode)
WITH g1.label AS label1, g2.label AS label2, count(*) AS cnt
ORDER BY cnt DESC LIMIT 10
RETURN collect({tags: [label1, label2], count: cnt}) AS frequent_keywords

-- 2. 카테고리 분포 (누적)
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g:GoTNode)
RETURN g.group AS category, count(*) AS count
ORDER BY count DESC

-- 3. 전체 노드/링크 (누적 그래프)
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g:GoTNode)
OPTIONAL MATCH (g)-[r:LEADS_TO]->(g2:GoTNode)
RETURN g.got_node_id AS id, g.label AS name, g.group AS group, g.weight AS val,
       g2.got_node_id AS target_id
```

### 5-2. Backend 프록시용 내부 API

**신규 파일**: `src/api/routes/graph.py`

```python
"""
Backend 전용 그래프 데이터 조회 API.

[이관 주석] Neo4j를 Backend로 이관 시:
- 이 라우터 전체를 삭제한다.
- Backend가 직접 Neo4j를 조회하도록 Cypher 쿼리를 Backend팀에 인계한다.
- 인계 대상: 이 파일의 CYPHER_* 상수와 transform 로직.
"""
from fastapi import APIRouter
from src.db.factory import create_graph_client
from src.api.graph_transformer import transform_got_to_graph_data, calc_category_distribution

router = APIRouter(prefix="/internal/graph", tags=["Graph (Internal)"])

@router.get("/users/{user_id}/data")
async def get_user_graph_data(user_id: str, limit: int = 50):
    """사용자 누적 그래프 데이터 조회."""
    # ... Cypher 실행 + 변환
```

`src/api/main.py`에 라우터 등록:

```python
# [이관 주석] Neo4j 이관 시 아래 import와 include_router를 삭제.
from src.api.routes.graph import router as graph_router
app.include_router(graph_router)
```

### 5-3. Backend팀 협의 사항

| 항목 | AI팀 제공물 | Backend 구현 |
|------|-----------|-------------|
| 저장 페이로드 | SaveRequest 스키마 (4-2에서 정의) | `POST /api/v1/graph_analyses` 수신 |
| 프론트엔드 조회 | 응답 형식 예시 (nodes/links/keywords/distribution) | `GET /api/v1/users/{user_id}/graph` 구현 |
| 데이터 소스 (현재) | AI서버 내부 API `/internal/graph/users/{user_id}/data` | Backend가 프록시 |
| 데이터 소스 (이관 후) | Cypher 쿼리 + transform 로직 인계 | Backend가 직접 Neo4j 조회 |

---

## Phase 6: 검증

### 6-1. 전체 검증 체크리스트

```bash
# 1. Neo4j 배포
docker compose up -d
docker exec -i mindlog-neo4j cypher-shell -u neo4j -p <pw> "RETURN 1"
docker exec -i mindlog-neo4j cypher-shell -u neo4j -p <pw> "SHOW CONSTRAINTS"

# 2. 모델 ID 해상도 (Phase 2-2)
python -c "from config.loader import get_settings; ..."

# 3. 기존 테스트 통과
pytest tests/agents/ -v

# 4. Neo4j 통합 테스트
pytest dev/local_db/test_neo4j_integration.py -v
pytest dev/local_db/test_factory_crossdb.py -v

# 5. graph_transformer 단위 테스트
pytest tests/api/test_graph_transformer.py -v

# 6. E2E 파이프라인 실행 후 Neo4j 확인
docker exec -i mindlog-neo4j cypher-shell -u neo4j -p <pw> \
  "MATCH (g:GoTNode) RETURN g.group, count(g)"

# 7. 메모리 모니터링
docker stats --no-stream
```

### 6-2. 성능 회귀 방지

| 테스트 | 합격 | 롤백 |
|--------|------|------|
| bv_score (5회 평균) | ≥ 0.82 | < 0.78 |
| GoT group 유효율 | ≥ 90% (보정 전) | < 70% |
| JSON 파싱 오류율 | ≤ 5% | > 10% |
| 파이프라인 실행 시간 | ≤ 90초 | > 120초 |
| 메모리 (AI+Neo4j) | ≤ 3.5GB | OOM 발생 |

---

## 이관 시 삭제 대상 코드 정리 ★

Neo4j가 Backend(app-3)로 이관될 때 삭제/수정할 코드 목록.
모든 대상 코드에 `[이관 주석]`을 달아 식별 가능하게 한다.

### 삭제 대상 파일

| 파일 | 조치 | 이유 |
|------|------|------|
| `src/db/neo4j_client.py` | **파일 삭제** | AI서버 직접 접속 코드. 이관 후 GraphProxyClient만 사용 |
| `src/api/routes/graph.py` | **파일 삭제** | Backend 프록시용 내부 API. Backend가 직접 Neo4j 조회 시 불필요 |

### 삭제 대상 코드 블록

| 파일 | 라인 | 조치 | 설명 |
|------|------|------|------|
| `docker-compose.yml` | L36-64 | Neo4j 서비스 블록 삭제 | AI서버에서 Neo4j 제거 |
| `docker-compose.yml` | L19-21 | depends_on 삭제 | Neo4j 의존성 제거 |
| `docker-compose.yml` | L16 | mem_limit 복원 (1500m→2000m) | Neo4j 메모리 해제 |
| `src/db/factory.py` | L49-57 | local/hybrid 분기 삭제 | proxy만 남김 |
| `src/agents/podcast/podcast_reasoning.py` | `_save_got_to_neo4j()` 전체 | 메서드 삭제 | Backend 전송(4-2)만 유지 |
| `src/api/main.py` | graph_router import/include | 삭제 | 내부 API 제거 |
| `.env` | NEO4J_* 변수 3개 | 삭제 | Backend가 관리 |

### 유지 대상 (이관 후에도 필요)

| 파일 | 이유 |
|------|------|
| `src/db/base.py` (BaseGraphClient) | 추상 인터페이스. 구현체만 변경 |
| `src/db/api_proxy.py` (GraphProxyClient) | 이관 후 유일한 Neo4j 접근 경로 |
| `src/db/factory.py` (단순화 후) | proxy 모드만 반환하도록 수정 |
| `src/api/graph_transformer.py` | 변환 로직은 AI서버 책임. Neo4j 위치 무관 |
| `src/api/backend_resources.py` (RESOURCE_GRAPH_ANALYSIS) | Backend 저장은 항상 필요 |
| `dev/local_db/neo4j/init.cypher` | Backend 이관 시 인계 자료 |
| `dev/local_db/test_neo4j_integration.py` | Backend 이관 시 인계 자료 |

### 이관 전 Backend팀 인계물

| 자료 | 파일 |
|------|------|
| Cypher 쿼리 모음 | `src/api/routes/graph.py` 내 CYPHER_* 상수 |
| 스키마 DDL | `dev/local_db/neo4j/init.cypher` |
| 통합 테스트 | `dev/local_db/test_neo4j_integration.py` |
| 크로스DB 테스트 | `dev/local_db/test_factory_crossdb.py` |
| 시드 데이터 | `dev/local_db/seed.py` + `seed_data.json` |
| 변환 로직 참고 | `src/api/graph_transformer.py` |

---

## 수정 대상 파일 요약

| 파일 | Phase | 담당 | 변경 내용 | 이관 시 |
|------|-------|------|----------|---------|
| `docker-compose.yml` | 1-1 | 인프라 | Neo4j 주석 해제, mem_limit 조정 | 삭제 |
| `.env` | 1-2 | 인프라 | NEO4J_* + STORAGE_MODE | NEO4J_* 삭제 |
| `dev/local_db/neo4j/init.cypher` | 1-3 | 인프라 | group 인덱스 추가 | Backend 인계 |
| `config/settings.yaml` | 2-1 | 개발자3 | model: sonnet_37, max_tokens: 6000 | 유지 |
| `prompts/.../podcast_reasoning.yaml` | 3-1 | 개발자3 | v3.1.0: group 필드 + 6개 카테고리 | 유지 |
| `src/api/graph_transformer.py` (신규) | 3-2 | 개발자3 | 변환 + 검증 + 보정 | **유지** |
| `src/agents/podcast/podcast_reasoning.py` | 4-1,4-2 | 개발자3 | `_save_got_to_neo4j()` + Backend 전송 | Neo4j 부분 삭제 |
| `src/api/backend_resources.py` | 4-2 | 공용 | RESOURCE/TYPE 추가 | **유지** |
| `src/api/routes/graph.py` (신규) | 5-2 | 개발자 | 내부 조회 API | 삭제 |
| `src/api/main.py` | 5-2 | 개발자 | graph 라우터 등록 | 등록 삭제 |

> **Protected File**: `workflow.py` 수정 없음 ✅, `contracts.py` 수정 없음 ✅

---

## 작업 순서 (의존관계 반영)

```
Phase 1: Neo4j Docker 배포 + 스키마 (독립)
  1-1 docker-compose.yml
  1-2 .env
  1-3 init.cypher + group 인덱스
  1-4 시드 데이터
     ↓
Phase 2: 모델 변경 Haiku → Sonnet (Phase 1과 병렬 가능)
  2-1 settings.yaml 변경 ──┐
  2-2 모델 ID 해상도 검증 ──┤ (순차 필수)
  2-3 성능 비교 테스트 ─────┘
  [실패 시 2-5 롤백]
     ↓
Phase 3: GoT 프롬프트 + 변환 (Phase 2 완료 필수)
  3-1 v3.1.0 프롬프트 ──────┐
  3-2 graph_transformer.py ──┤ (병렬)
  3-3 v3.1.0 프롬프트 테스트 ┘ (3-1,3-2 완료 후)
     ↓
Phase 4: 저장 연결 (Phase 1,3 완료 필수)
  4-1 _save_got_to_neo4j()
  4-2 Backend 전송 (backend_resources)
     ↓
Phase 5: 누적 + 조회 API (Phase 4 완료 후)
  5-1 Cypher 집계 쿼리
  5-2 내부 API + main.py 등록
  5-3 Backend팀 협의
     ↓
Phase 6: 전체 검증
```

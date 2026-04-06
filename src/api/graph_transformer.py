"""
GoT 출력 → 프론트엔드 그래프 데이터 변환 + group 검증.

PodcastReasoning의 GoT JSON을 프론트엔드 Force-directed 그래프 형식으로 변환한다.
LLM이 생성한 group 값을 검증하고, 잘못된 값은 KEYWORD_MAP으로 보정한다.

[이관 주석] 이 파일은 Neo4j 위치와 무관하게 항상 필요.
GoT JSON → 프론트엔드 형식 변환은 AI서버의 책임.
"""

from __future__ import annotations

from typing import Any

VALID_GROUPS = frozenset(
    {
        "work_structure",
        "leadership",
        "peer_relations",
        "career_growth",
        "culture_system",
        "emotional_exhaustion",
    }
)

# GoT label 텍스트에서 group을 유추하기 위한 키워드 → group 매핑 사전.
# LLM이 group을 잘못 생성했을 때 fallback으로 사용한다.
KEYWORD_MAP: dict[str, str] = {
    # work_structure
    "과부하": "work_structure",
    "업무과중": "work_structure",
    "야근": "work_structure",
    "리소스부족": "work_structure",
    "모호": "work_structure",
    "병목": "work_structure",
    "독박": "work_structure",
    "목표상실": "work_structure",
    # leadership
    "상사": "leadership",
    "압박": "leadership",
    "과잉간섭": "leadership",
    "책임회피": "leadership",
    "권위": "leadership",
    "피드백부족": "leadership",
    # peer_relations
    "신뢰": "peer_relations",
    "갈등": "peer_relations",
    "소통단절": "peer_relations",
    "뒷담화": "peer_relations",
    "배신": "peer_relations",
    "책임전가": "peer_relations",
    # career_growth
    "성장정체": "career_growth",
    "전문성": "career_growth",
    "가면증후군": "career_growth",
    "역량불안": "career_growth",
    # culture_system
    "보상": "culture_system",
    "불공정": "culture_system",
    "복지": "culture_system",
    "연차": "culture_system",
    # emotional_exhaustion
    "번아웃": "emotional_exhaustion",
    "우울": "emotional_exhaustion",
    "고립": "emotional_exhaustion",
    "불안": "emotional_exhaustion",
    "무기력": "emotional_exhaustion",
}

# 프론트엔드 더미 데이터의 ID prefix 규칙과 동일.
GROUP_PREFIXES: dict[str, str] = {
    "work_structure": "b",
    "leadership": "p",
    "peer_relations": "y",
    "career_growth": "g",
    "culture_system": "pk",
    "emotional_exhaustion": "br",
}


def validate_group(node: dict[str, Any]) -> str:
    """LLM이 생성한 group을 검증. 유효하지 않으면 label 키워드로 재분류."""
    group: str = str(node.get("group", ""))
    if group in VALID_GROUPS:
        return group

    # fallback: label 텍스트에서 키워드 매칭
    label = node.get("label", "")
    for keyword, mapped_group in KEYWORD_MAP.items():
        if keyword in label:
            return mapped_group

    return "emotional_exhaustion"  # 최종 기본값


def intensity_to_val(intensity: float) -> int:
    """intensity(0.0~1.0) → 프론트엔드 val(20/50/100) 3단계 변환.

    프론트엔드가 val을 100/50/20으로 구분하여 노드 크기를 결정한다.
    """
    if intensity >= 0.75:
        return 100
    if intensity >= 0.45:
        return 50
    return 20


def transform_got_to_graph_data(got_result: dict) -> dict:
    """GoT JSON → 프론트엔드 ``{ nodes, links }`` 변환.

    변환 규칙:
    - id: ``"1"`` → ``"b1"`` (group prefix + 순번)
    - label → name
    - type은 프론트엔드에서 미사용 → 제외
    - intensity → val (100/50/20)
    - edges.from/to → links.source/target
    """
    group_counters: dict[str, int] = {}
    id_map: dict[str, str] = {}  # GoT id → frontend id

    nodes: list[dict] = []
    for node in got_result.get("nodes", []):
        group = validate_group(node)
        prefix = GROUP_PREFIXES[group]
        group_counters[group] = group_counters.get(group, 0) + 1
        new_id = f"{prefix}{group_counters[group]}"
        id_map[str(node["id"])] = new_id
        nodes.append(
            {
                "id": new_id,
                "name": node.get("label", ""),
                "group": group,
                "val": intensity_to_val(node.get("intensity", 0.5)),
            }
        )

    links: list[dict] = []
    for edge in got_result.get("edges", []):
        source = id_map.get(str(edge.get("from", "")))
        target = id_map.get(str(edge.get("to", "")))
        if source and target:
            links.append({"source": source, "target": target})

    return {"nodes": nodes, "links": links}


def transform_neo4j_rows_to_graph_data(rows: list[dict]) -> dict:
    """Neo4j 쿼리 결과 → 프론트엔드 ``{ nodes, links }`` 변환.

    routes/graph.py에서 사용. transform_got_to_graph_data()와
    동일한 ID 생성/group 처리 로직을 공유한다.

    각 row는 ``id``, ``name``, ``grp``, ``intensity``, ``target_id`` 필드를 포함한다.
    """
    seen_ids: set[str] = set()
    group_counters: dict[str, int] = {}
    id_map: dict[str, str] = {}
    nodes: list[dict] = []
    links_raw: list[dict] = []

    for row in rows:
        node_id = row.get("id", "")
        if node_id and node_id not in seen_ids:
            seen_ids.add(node_id)
            grp = row.get("grp", "emotional_exhaustion")
            if grp not in VALID_GROUPS:
                grp = "emotional_exhaustion"
            prefix = GROUP_PREFIXES[grp]
            group_counters[grp] = group_counters.get(grp, 0) + 1
            frontend_id = f"{prefix}{group_counters[grp]}"
            id_map[node_id] = frontend_id
            nodes.append(
                {
                    "id": frontend_id,
                    "name": row.get("name", ""),
                    "group": grp,
                    "val": intensity_to_val(row.get("intensity", 0.5)),
                }
            )

        target = row.get("target_id")
        if target and node_id:
            links_raw.append({"source_raw": node_id, "target_raw": target})

    links = []
    for link in links_raw:
        s = id_map.get(link["source_raw"])
        t = id_map.get(link["target_raw"])
        if s and t:
            links.append({"source": s, "target": t})

    return {"nodes": nodes, "links": links}


def calc_category_distribution(nodes: list[dict]) -> dict[str, int]:
    """group별 노드 수 집계. 단일 에피소드에서도 계산 가능."""
    dist: dict[str, int] = {}
    for node in nodes:
        g = node.get("group", "emotional_exhaustion")
        dist[g] = dist.get(g, 0) + 1
    return dist


def transform_cumulative_to_frontend(
    nodes: list[dict],
    edges: list[dict],
) -> dict:
    """RDB 누적 그래프 데이터 → 프론트엔드 ``{ nodes, links }`` 변환.

    입력은 RDB 누적 테이블에서 조회한 데이터이며,
    각 노드는 ``label``, ``grp``, ``weight``, ``mention_count``, ``trend``,
    ``first_seen``, ``last_seen`` 필드를 포함한다.

    에피소드별 변환(``transform_got_to_graph_data``)과 달리:
    - **weight 원본값**을 그대로 전달 (``intensity_to_val()`` 미사용)
    - ``mention_count``, ``trend``, ``first_seen``, ``last_seen`` 메타데이터 포함
    - ID 생성은 기존 ``GROUP_PREFIXES`` + 순번 규칙 동일

    Args:
        nodes: RDB 누적 노드 목록 (label, grp, weight, mention_count, trend 등)
        edges: RDB 누적 엣지 목록 (source_label, source_grp, target_label, target_grp, weight)

    Returns:
        ``{ "nodes": [...], "links": [...] }`` 프론트엔드 형식
    """
    group_counters: dict[str, int] = {}
    # (label, grp) → frontend_id 매핑
    key_to_id: dict[tuple[str, str], str] = {}

    frontend_nodes: list[dict] = []
    for node in nodes:
        label = node.get("label", "")
        grp = node.get("grp", "emotional_exhaustion")
        if grp not in VALID_GROUPS:
            grp = "emotional_exhaustion"

        prefix = GROUP_PREFIXES[grp]
        group_counters[grp] = group_counters.get(grp, 0) + 1
        frontend_id = f"{prefix}{group_counters[grp]}"
        key_to_id[(label, grp)] = frontend_id

        frontend_nodes.append(
            {
                "id": frontend_id,
                "name": label,
                "group": grp,
                "weight": node.get("weight", 0.0),
                "mention_count": node.get("mention_count", 1),
                "trend": node.get("trend", "stable"),
                "first_seen": node.get("first_seen", ""),
                "last_seen": node.get("last_seen", ""),
            }
        )

    frontend_links: list[dict] = []
    for edge in edges:
        source_key = (edge.get("source_label", ""), edge.get("source_grp", ""))
        target_key = (edge.get("target_label", ""), edge.get("target_grp", ""))
        source_id = key_to_id.get(source_key)
        target_id = key_to_id.get(target_key)
        if source_id and target_id and source_id != target_id:
            frontend_links.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "weight": edge.get("weight", 1),
                }
            )

    return {"nodes": frontend_nodes, "links": frontend_links}

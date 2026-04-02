"""
Backend 전용 그래프 데이터 조회 API.

사용자의 누적 GoT 데이터를 Neo4j에서 집계하여
프론트엔드 Force-directed 그래프 형식으로 반환한다.

[이관 주석] Neo4j를 Backend로 이관 시:
- 이 라우터 전체를 삭제한다.
- Backend가 직접 Neo4j를 조회하도록 아래 CYPHER_* 상수와
  graph_transformer 로직을 Backend팀에 인계한다.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from src.api.graph_transformer import (
    GROUP_PREFIXES,
    intensity_to_val,
)
from src.db.factory import create_graph_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/graph", tags=["Graph (Internal)"])

# ===================================================================
# Cypher 쿼리 상수 — Backend 이관 시 인계 대상
# ===================================================================

CYPHER_USER_GRAPH = """
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g:GoTNode)
OPTIONAL MATCH (g)-[r:LEADS_TO]->(g2:GoTNode)
WHERE g2.episode_id IS NOT NULL
RETURN g.got_node_id AS id, g.label AS name, g.group AS grp,
       g.weight AS intensity, g2.got_node_id AS target_id
LIMIT $limit
"""

CYPHER_FREQUENT_KEYWORDS = """
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g1:GoTNode)-[:LEADS_TO]->(g2:GoTNode)
WITH g1.label AS label1, g2.label AS label2, count(*) AS cnt
ORDER BY cnt DESC
LIMIT $limit
RETURN collect({tags: [label1, label2], count: cnt}) AS frequent_keywords
"""

CYPHER_CATEGORY_DISTRIBUTION = """
MATCH (u:User {user_id: $user_id})-[:HAS_SESSION]->(s:Session)
      -[:REASONED_BY]->(g:GoTNode)
RETURN g.group AS category, count(*) AS count
ORDER BY count DESC
"""


@router.get("/users/{user_id}/data")
async def get_user_graph_data(
    user_id: str,
    limit: int = Query(default=100, le=500),
) -> dict[str, Any]:
    """사용자 누적 그래프 데이터 조회.

    Returns:
        nodes, links, frequent_keywords, category_distribution 포함 dict.
    """
    try:
        async with create_graph_client() as client:
            # 1. 노드 + 링크
            raw = await client.execute_query(
                CYPHER_USER_GRAPH,
                params={"user_id": user_id, "limit": limit},
            )

            seen_ids: set[str] = set()
            group_counters: dict[str, int] = {}
            id_map: dict[str, str] = {}
            nodes: list[dict] = []
            links: list[dict] = []

            for row in raw:
                node_id = row.get("id", "")
                if node_id and node_id not in seen_ids:
                    seen_ids.add(node_id)
                    grp = row.get("grp", "emotional_exhaustion")
                    if grp not in GROUP_PREFIXES:
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
                    links.append({"source_raw": node_id, "target_raw": target})

            # 링크 ID 재매핑
            mapped_links = []
            for link in links:
                s = id_map.get(link["source_raw"])
                t = id_map.get(link["target_raw"])
                if s and t:
                    mapped_links.append({"source": s, "target": t})

            # 2. 자주 연결된 키워드
            kw_raw = await client.execute_query(
                CYPHER_FREQUENT_KEYWORDS,
                params={"user_id": user_id, "limit": 10},
            )
            frequent_keywords = (
                kw_raw[0].get("frequent_keywords", []) if kw_raw else []
            )

            # 3. 카테고리 분포
            dist_raw = await client.execute_query(
                CYPHER_CATEGORY_DISTRIBUTION,
                params={"user_id": user_id},
            )
            category_distribution = {
                row["category"]: row["count"]
                for row in dist_raw
                if row.get("category")
            }

        return {
            "success": True,
            "data": {
                "nodes": nodes,
                "links": mapped_links,
                "frequent_keywords": frequent_keywords,
                "category_distribution": category_distribution,
            },
        }
    except Exception:
        logger.exception("그래프 데이터 조회 실패: user_id=%s", user_id)
        return {
            "success": False,
            "error": {"code": "GRAPH_QUERY_ERROR", "message": "그래프 데이터 조회 실패"},
        }

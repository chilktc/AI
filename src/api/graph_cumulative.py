"""
GoT 그래프 데이터를 누적하여 Backend에 저장하는 모듈 (Mode A).

흐름:
  1. GET /api/v1/graph_nodes    — 기존 누적 데이터 조회
  2. EMA 계산                   — 기존 가중치와 새 GoT 결과를 지수이동평균으로 병합
  3. PUT /api/v1/graph_nodes    — 병합된 최종 데이터 저장

EMA 공식:
  new_weight = α × new_intensity + (1 - α) × existing_weight
  α = config/settings.yaml → graph.ema_alpha  (기본값 0.3)

사용 방법:
    await publish_graph_to_rdb(got_result, state, episode_id)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.graph_transformer import validate_group

logger = logging.getLogger(__name__)

_TREND_THRESHOLD: float = 0.05


def _apply_ema(existing_weight: float, new_intensity: float, alpha: float) -> float:
    """EMA: α × new + (1 - α) × existing. 소수점 4자리 반올림."""
    return round(alpha * new_intensity + (1.0 - alpha) * existing_weight, 4)


def _calc_trend(old_weight: float, new_weight: float) -> str:
    """가중치 변화량으로 trend를 판정한다.

    Returns:
        "increasing" | "stable" | "decreasing"
    """
    delta = new_weight - old_weight
    if delta >= _TREND_THRESHOLD:
        return "increasing"
    if delta <= -_TREND_THRESHOLD:
        return "decreasing"
    return "stable"


def _merge_nodes(
    existing_nodes: list[dict[str, Any]],
    got_nodes: list[dict[str, Any]],
    now: datetime,
    alpha: float,
) -> list[dict[str, Any]]:
    """기존 누적 노드와 새 GoT 노드를 EMA로 병합한다.

    Args:
        existing_nodes: GET /graph_nodes에서 받은 GraphCumulativeData.nodes
        got_nodes: 이번 에피소드 GoT 노드 (label, group, intensity 포함)
        now: 현재 시각 (last_seen 갱신용)
        alpha: EMA 계수

    Returns:
        병합된 누적 노드 목록 (grp는 소문자)
    """
    now_iso = now.isoformat()
    # (label, grp소문자) → 노드 dict 매핑 (기존 데이터 grp 대소문자 정규화)
    result: dict[tuple[str, str], dict[str, Any]] = {
        (n["label"], n["grp"].lower()): dict(n) for n in existing_nodes
    }

    for got_node in got_nodes:
        label = got_node.get("label", "").strip()
        if not label:
            continue
        grp = validate_group(got_node).lower()
        intensity = float(got_node.get("intensity", 0.5))
        key = (label, grp)

        if key in result:
            existing = result[key]
            old_w = float(existing.get("weight", 0.5))
            new_w = _apply_ema(old_w, intensity, alpha)
            result[key] = {
                **existing,
                "weight": new_w,
                "mention_count": int(existing.get("mention_count", 1)) + 1,
                "trend": _calc_trend(old_w, new_w),
                "last_seen": now_iso,
            }
        else:
            result[key] = {
                "label": label,
                "grp": grp,
                "weight": round(intensity, 4),
                "mention_count": 1,
                "trend": "stable",
                "first_seen": now_iso,
                "last_seen": now_iso,
            }

    return list(result.values())


def _merge_links(
    existing_links: list[dict[str, Any]],
    got_edges: list[dict[str, Any]],
    got_node_map: dict[str, dict[str, str]],
    now: datetime,
) -> list[dict[str, Any]]:
    """기존 누적 엣지와 새 GoT 엣지를 병합한다. 등장 횟수(weight)를 누적한다.

    Args:
        existing_links: GET /graph_nodes에서 받은 GraphCumulativeData.links
        got_edges: 이번 에피소드 GoT 엣지 (from/to 키 사용, relationship)
        got_node_map: GoT node id → {"label": ..., "grp": ...} 매핑
        now: 현재 시각

    Returns:
        병합된 누적 엣지 목록 (self-loop 제외)
    """
    now_iso = now.isoformat()
    # (src_label, src_grp소문자, tgt_label, tgt_grp소문자) → 엣지 dict
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {
        (
            e["source_label"],
            e["source_grp"].lower(),
            e["target_label"],
            e["target_grp"].lower(),
        ): dict(e)
        for e in existing_links
    }

    for edge in got_edges:
        src_id = str(edge.get("from", ""))
        tgt_id = str(edge.get("to", ""))
        src_info = got_node_map.get(src_id, {})
        tgt_info = got_node_map.get(tgt_id, {})

        src_label = src_info.get("label", "")
        src_grp = src_info.get("grp", "").lower()
        tgt_label = tgt_info.get("label", "")
        tgt_grp = tgt_info.get("grp", "").lower()

        if not src_label or not tgt_label:
            continue
        # self-loop 방지
        if src_label == tgt_label and src_grp == tgt_grp:
            continue

        key = (src_label, src_grp, tgt_label, tgt_grp)
        relationship = str(edge.get("relationship", "related"))

        if key in result:
            existing_edge = result[key]
            result[key] = {
                **existing_edge,
                "weight": int(existing_edge.get("weight", 1)) + 1,
                "last_seen": now_iso,
            }
        else:
            result[key] = {
                "source_label": src_label,
                "source_grp": src_grp,
                "target_label": tgt_label,
                "target_grp": tgt_grp,
                "weight": 1,
                "relationship": relationship,
                "first_seen": now_iso,
                "last_seen": now_iso,
            }

    return list(result.values())


async def publish_graph_to_rdb(
    got_result: dict[str, Any],
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """GoT 결과를 EMA로 누적하여 Backend에 저장한다 (Mode A).

    흐름:
      1. GET /api/v1/graph_nodes  — 기존 누적 데이터 조회
      2. EMA 병합                 — 새 GoT 노드/엣지를 기존 데이터와 통합
      3. PUT /api/v1/graph_nodes  — 병합 결과 저장

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)
        episode_id: 로그 컨텍스트용 (PUT payload에 미포함)

    Returns:
        성공 시 True, 실패 시 False (파이프라인 비중단)
    """
    try:
        from src.api.backend_resources import (  # noqa: F401
            RESOURCE_GRAPH_NODES,
            TYPE_GRAPH_CUMULATIVE,
        )
        from src.api.contracts import GraphCumulativeData, SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            logger.warning("BackendClient가 초기화되지 않았습니다")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 누적 갱신을 건너뜁니다")
            return True

        from config.loader import get_settings

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        now = datetime.now(timezone.utc)
        alpha = get_settings().graph_ema_alpha

        # 1. 기존 누적 데이터 조회
        existing = await backend_client.load_graph_cumulative(user_id)
        if existing is None:
            logger.warning(
                "기존 누적 데이터 조회 실패 — 신규 사용자로 처리 후 진행 (user=%s)", user_id
            )
            existing = GraphCumulativeData()

        # GoT node id → {label, grp} 매핑 (엣지 해석용)
        got_node_map: dict[str, dict[str, str]] = {
            str(n.get("id", str(i))): {
                "label": n.get("label", ""),
                "grp": validate_group(n),
            }
            for i, n in enumerate(got_nodes)
        }

        # 2. EMA 병합
        merged_nodes = _merge_nodes(existing.nodes, got_nodes, now, alpha)
        merged_links = _merge_links(
            existing.links,
            got_result.get("edges", []),
            got_node_map,
            now,
        )

        # 3. PUT 저장
        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_GRAPH_CUMULATIVE,
            data={"nodes": merged_nodes, "links": merged_links},
            timestamp=now,
        )
        success = await backend_client.put_graph_cumulative(request)
        if success:
            logger.info(
                "누적 그래프 갱신 완료 (user=%s, nodes=%d, links=%d, ep=%s)",
                user_id,
                len(merged_nodes),
                len(merged_links),
                episode_id or "unknown",
            )
        else:
            logger.warning("누적 그래프 PUT 실패 (user=%s)", user_id)
        return success

    except Exception as e:
        logger.warning(
            "누적 그래프 갱신 실패 — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False

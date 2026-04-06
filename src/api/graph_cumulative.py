"""
GoT 그래프 데이터 누적 저장 모듈.

에피소드별 GoT 결과를 사용자별 누적 그래프로 통합하여 RDB에 저장한다.
Mode A(AI 서버 UPSERT)와 Mode B(Backend UPSERT) 두 가지 방식을 지원한다.

사용 방법:
    - Mode A (AI 서버가 UPSERT):
        await publish_graph_cumulative_mode_a(got_result, state)
    - Mode B (Backend가 UPSERT):
        await publish_graph_raw_mode_b(got_result, state, episode_id)

모드 전환:
    config/settings.yaml → graph.upsert_mode: "ai_server" | "backend"

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

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# EMA 계산 유틸리티 — Mode A, Mode B 공통
# ═══════════════════════════════════════════════════════════════════════


def calc_ema(old_weight: float, new_intensity: float, alpha: float | None = None) -> float:
    """지수이동평균(EMA)으로 weight를 갱신한다.

    Args:
        old_weight: 기존 누적 weight (0.0~1.0)
        new_intensity: 신규 에피소드에서의 intensity (0.0~1.0)
        alpha: EMA 알파값 (None이면 설정에서 로드)

    Returns:
        갱신된 weight (0.0~1.0 범위 클램핑)
    """
    if alpha is None:
        alpha = get_settings().graph_ema_alpha
    result = alpha * new_intensity + (1 - alpha) * old_weight
    return max(0.0, min(1.0, result))


def calc_trend(old_weight: float, new_weight: float) -> str:
    """weight 변화량으로 trend를 결정한다.

    임계값 0.05: 이보다 작은 변화는 'stable'로 간주.

    Args:
        old_weight: 이전 weight
        new_weight: 갱신된 weight

    Returns:
        "increasing", "decreasing", 또는 "stable"
    """
    diff = new_weight - old_weight
    if diff > 0.05:
        return "increasing"
    if diff < -0.05:
        return "decreasing"
    return "stable"


# ═══════════════════════════════════════════════════════════════════════
# 노드/엣지 병합 순수 함수 — Mode A 전용
# ═══════════════════════════════════════════════════════════════════════


def merge_nodes_from_got(
    got_result: dict,
    existing_nodes: list[dict],
    alpha: float | None = None,
) -> list[dict]:
    """GoT 노드를 기존 누적 노드에 병합한다.

    (label, group) 기준으로 기존 노드가 있으면 EMA 갱신,
    없으면 신규 추가한다.

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        existing_nodes: RDB에서 조회한 기존 누적 노드 목록
        alpha: EMA 알파값 (None이면 설정에서 로드)

    Returns:
        병합된 전체 노드 목록 (기존 + 신규/갱신)
    """
    if alpha is None:
        alpha = get_settings().graph_ema_alpha

    now = datetime.now(timezone.utc).isoformat()

    # 기존 노드를 (label, grp) → dict 인덱스로 변환
    existing_map: dict[tuple[str, str], dict] = {}
    for node in existing_nodes:
        key = (node.get("label", ""), node.get("grp", ""))
        existing_map[key] = dict(node)  # 복사본 사용

    # GoT 노드 순회하며 병합
    for got_node in got_result.get("nodes", []):
        label = got_node.get("label", "")
        group = validate_group(got_node)
        intensity = got_node.get("intensity", 0.5)
        key = (label, group)

        if key in existing_map:
            # 기존 노드 갱신 (EMA)
            old = existing_map[key]
            old_weight = old.get("weight", 0.5)
            new_weight = calc_ema(old_weight, intensity, alpha)
            old["weight"] = round(new_weight, 4)
            old["mention_count"] = old.get("mention_count", 1) + 1
            old["trend"] = calc_trend(old_weight, new_weight)
            old["last_seen"] = now
        else:
            # 신규 노드 추가
            existing_map[key] = {
                "label": label,
                "grp": group,
                "weight": round(intensity, 4),
                "mention_count": 1,
                "trend": "stable",
                "first_seen": now,
                "last_seen": now,
            }

    return list(existing_map.values())


def merge_edges_from_got(
    got_result: dict,
    existing_edges: list[dict],
) -> list[dict]:
    """GoT 엣지를 기존 누적 엣지에 병합한다.

    (source_label, source_grp, target_label, target_grp) 기준으로
    기존 엣지가 있으면 weight 1 증가, 없으면 신규 추가한다.

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        existing_edges: RDB에서 조회한 기존 누적 엣지 목록

    Returns:
        병합된 전체 엣지 목록
    """
    # GoT node id → (label, group) 매핑 생성
    id_to_key: dict[str, tuple[str, str]] = {}
    for node in got_result.get("nodes", []):
        node_id = str(node.get("id", ""))
        label = node.get("label", "")
        group = validate_group(node)
        id_to_key[node_id] = (label, group)

    # 기존 엣지를 키 인덱스로 변환
    EdgeKey = tuple[str, str, str, str]
    existing_map: dict[EdgeKey, dict] = {}
    for edge in existing_edges:
        key: EdgeKey = (
            edge.get("source_label", ""),
            edge.get("source_grp", ""),
            edge.get("target_label", ""),
            edge.get("target_grp", ""),
        )
        existing_map[key] = dict(edge)

    # GoT 엣지 순회하며 병합
    for got_edge in got_result.get("edges", []):
        source_id = str(got_edge.get("from", ""))
        target_id = str(got_edge.get("to", ""))
        source_key = id_to_key.get(source_id)
        target_key = id_to_key.get(target_id)

        if not source_key or not target_key:
            continue  # 참조 불가능한 노드 → 스킵

        # self-loop 방지
        if source_key == target_key:
            continue

        edge_key: EdgeKey = (source_key[0], source_key[1], target_key[0], target_key[1])

        if edge_key in existing_map:
            existing_map[edge_key]["weight"] = existing_map[edge_key].get("weight", 1) + 1
        else:
            existing_map[edge_key] = {
                "source_label": source_key[0],
                "source_grp": source_key[1],
                "target_label": target_key[0],
                "target_grp": target_key[1],
                "weight": 1,
                "relationship": got_edge.get("relationship", "relates_to"),
            }

    return list(existing_map.values())


# ═══════════════════════════════════════════════════════════════════════
# Mode A: AI 서버 UPSERT (GET → EMA 계산 → PUT)
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_cumulative_mode_a(
    got_result: dict,
    state: dict[str, Any],
) -> bool:
    """Mode A: AI 서버가 EMA 계산 후 누적 데이터를 PUT한다.

    흐름:
        1. BackendClient.load()로 기존 누적 데이터 조회
        2. merge_nodes_from_got() / merge_edges_from_got()로 병합
        3. BackendClient.update()로 갱신된 데이터 PUT

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)

    Returns:
        성공 시 True, 실패 시 False (파이프라인 비중단)
    """
    try:
        # lazy import — 순환 참조 방지
        from src.api.backend_resources import RESOURCE_GRAPH_NODES
        from src.api.contracts import SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            logger.warning("BackendClient가 초기화되지 않았습니다 (Mode A)")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 누적 저장을 건너뜁니다")
            return True

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")

        # 1) 기존 누적 데이터 조회
        existing_nodes: list[dict] = []
        existing_edges: list[dict] = []
        try:
            load_resp = await backend_client.load(
                RESOURCE_GRAPH_NODES,
                user_id=user_id,
            )
            if load_resp.data:
                first = load_resp.data[0] if load_resp.data else {}
                existing_nodes = first.get("nodes", [])
                existing_edges = first.get("edges", [])
        except Exception as e:
            logger.info(
                "기존 누적 데이터 조회 실패 (최초 저장으로 진행) — %s: %s",
                type(e).__name__,
                str(e),
            )

        # 2) 병합
        alpha = get_settings().graph_ema_alpha
        merged_nodes = merge_nodes_from_got(got_result, existing_nodes, alpha)
        merged_edges = merge_edges_from_got(got_result, existing_edges)

        # 3) PUT 갱신
        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type="graph_cumulative",
            data={
                "nodes": merged_nodes,
                "edges": merged_edges,
            },
            timestamp=datetime.now(timezone.utc),
        )
        await backend_client.update(RESOURCE_GRAPH_NODES, request)
        logger.info(
            "누적 그래프 갱신 완료 (Mode A, nodes=%d, edges=%d)",
            len(merged_nodes),
            len(merged_edges),
        )
        return True

    except Exception as e:
        logger.warning(
            "누적 그래프 갱신 실패 (Mode A) — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False


# ═══════════════════════════════════════════════════════════════════════
# Mode B: Backend UPSERT (POST raw, Backend가 EMA 계산)
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_raw_mode_b(
    got_result: dict,
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """Mode B: GoT 결과를 그대로 Backend에 POST한다.

    Backend가 수신 후 EMA 계산 + UPSERT를 수행한다.
    AI 서버는 group 검증만 수행하고 계산하지 않는다.

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)
        episode_id: 에피소드 ID (빈 문자열이면 session_id로 생성)

    Returns:
        성공 시 True, 실패 시 False (파이프라인 비중단)
    """
    try:
        from src.api.backend_resources import RESOURCE_GRAPH_EPISODES, TYPE_GRAPH_EPISODE
        from src.api.contracts import SaveRequest
        from src.api.main import backend_client

        if backend_client is None:
            logger.warning("BackendClient가 초기화되지 않았습니다 (Mode B)")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 Raw 전송을 건너뜁니다")
            return True

        user_id = state.get("user_id", "")
        session_id = state.get("session_id", "")
        ep_id = episode_id or f"ep_{session_id}"

        # group 검증만 수행 (계산 없음)
        validated_nodes = []
        for node in got_nodes:
            validated = dict(node)
            validated["group"] = validate_group(node)
            validated_nodes.append(validated)

        request = SaveRequest(
            user_id=user_id,
            session_id=session_id,
            type=TYPE_GRAPH_EPISODE,
            data={
                "episode_id": ep_id,
                "got_result": {
                    "nodes": validated_nodes,
                    "edges": got_result.get("edges", []),
                },
            },
            timestamp=datetime.now(timezone.utc),
        )
        await backend_client.save(RESOURCE_GRAPH_EPISODES, request)
        logger.info(
            "에피소드 Raw 데이터 전송 완료 (Mode B, episode=%s, nodes=%d)",
            ep_id,
            len(validated_nodes),
        )
        return True

    except Exception as e:
        logger.warning(
            "에피소드 Raw 데이터 전송 실패 (Mode B) — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False


# ═══════════════════════════════════════════════════════════════════════
# 디스패처 — settings에서 모드를 읽어 자동 분기
# ═══════════════════════════════════════════════════════════════════════


async def publish_graph_to_rdb(
    got_result: dict,
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """설정에 따라 Mode A 또는 Mode B를 호출한다.

    config/settings.yaml → graph.upsert_mode:
        "ai_server" → Mode A (publish_graph_cumulative_mode_a)
        "backend"   → Mode B (publish_graph_raw_mode_b)

    Args:
        got_result: GoT 출력 (nodes, edges 포함)
        state: AgentState (user_id, session_id 포함)
        episode_id: 에피소드 ID (Mode B에서 사용)

    Returns:
        성공 시 True, 실패 시 False
    """
    mode = get_settings().graph_upsert_mode

    if mode == "backend":
        return await publish_graph_raw_mode_b(got_result, state, episode_id)
    else:
        return await publish_graph_cumulative_mode_a(got_result, state)

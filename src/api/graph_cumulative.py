"""
GoT 그래프 에피소드 데이터를 Backend에 전송하는 모듈.

에피소드별 GoT 결과를 Backend에 POST한다.
Backend가 EMA 계산 + UPSERT를 수행한다.
AI 서버는 group 검증만 수행한다.

사용 방법:
    await publish_graph_to_rdb(got_result, state, episode_id)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.graph_transformer import validate_group

logger = logging.getLogger(__name__)


async def publish_graph_to_rdb(
    got_result: dict,
    state: dict[str, Any],
    episode_id: str = "",
) -> bool:
    """GoT 결과를 Backend에 POST한다.

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
            logger.warning("BackendClient가 초기화되지 않았습니다")
            return False

        got_nodes = got_result.get("nodes", [])
        if not got_nodes:
            logger.info("GoT 노드가 비어있어 전송을 건너뜁니다")
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
            "에피소드 GoT 데이터 전송 완료 (episode=%s, nodes=%d)",
            ep_id,
            len(validated_nodes),
        )
        return True

    except Exception as e:
        logger.warning(
            "에피소드 GoT 데이터 전송 실패 — %s: %s",
            type(e).__name__,
            str(e),
        )
        return False

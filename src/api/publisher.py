"""
에이전트 데이터 전달 유틸리티.

파이프라인 실행 중 에이전트가 백엔드에 데이터를 전달하기 위한 공통 클래스.
SaveRequest 생성, 에러 처리, 로깅을 캡슐화하여 보일러플레이트를 제거한다.

사용 예시::

    publisher = AgentDataPublisher()
    await publisher.publish(
        resource=RESOURCE_EMOTION_LOG,
        data={"primary_emotion": "anxiety", "intensity": 0.7},
        user_id="user_123",
        session_id="sess_456",
    )

설계 근거:
    - LearningAgent(learning.py:116-132)에서 반복되는 SaveRequest 생성 +
      BackendClient.save() + try/except 패턴을 공통 유틸리티로 추출.
    - 에이전트의 process() 메서드 내에서 await로 호출 가능 (async 함수).
    - TIER 1 병렬 Fan-out에서도 각 에이전트가 독립 코루틴이므로 안전.
    - publish() 실패 시 예외를 전파하지 않아 파이프라인 흐름에 영향 없음.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.api.contracts import SaveRequest

logger = logging.getLogger(__name__)


class AgentDataPublisher:
    """
    에이전트 결과를 백엔드에 전달하는 공통 유틸리티.

    특징:
        - BackendClient lazy import (circular dependency 방지)
        - 실패 시 예외 미전파 (bool 반환)
        - 로깅 내장 (성공/실패 모두 기록)
        - @with_retry(3회) 내장 (BackendClient.save()에 이미 적용)

    Args:
        client: BackendClient 인스턴스 (None이면 lazy import).
                테스트 시 mock 객체를 주입할 수 있다.
    """

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        """
        BackendClient를 lazy import로 가져온다.

        src.api.main에서 초기화된 backend_client 싱글톤을 사용한다.
        podcasts.py의 _save_episode_bundle()과 동일한 패턴으로
        circular dependency를 방지한다.

        Raises:
            RuntimeError: BackendClient가 초기화되지 않은 경우
        """
        if self._client is None:
            from src.api.main import backend_client

            if backend_client is None:
                raise RuntimeError("BackendClient가 초기화되지 않았습니다.")
            self._client = backend_client
        return self._client

    async def publish(
        self,
        resource: str,
        data: dict[str, Any],
        user_id: str,
        session_id: str,
        data_type: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        """
        에이전트 결과를 백엔드에 전달한다.

        Args:
            resource: 리소스 경로 (backend_resources.py 상수 사용)
            data: 전달할 데이터 dict (에이전트별 구조)
            user_id: 사용자 ID
            session_id: 세션 ID
            data_type: SaveRequest.type 값 (None이면 resource 사용)
            trace_id: 추적 ID (선택, data에 포함됨)

        Returns:
            성공 시 True, 실패 시 False (예외 미전파)
        """
        try:
            client = self._get_client()

            payload = dict(data)
            if trace_id:
                payload["trace_id"] = trace_id

            request = SaveRequest(
                user_id=user_id,
                session_id=session_id,
                type=data_type or resource,
                data=payload,
                timestamp=datetime.now(timezone.utc),
            )

            await client.save(resource, request)
            logger.info(
                "데이터 전달 완료 (resource=%s, user=%s, session=%s)",
                resource,
                user_id,
                session_id,
            )
            return True

        except Exception as e:
            logger.warning(
                "데이터 전달 실패 (resource=%s) — %s: %s",
                resource,
                type(e).__name__,
                str(e),
            )
            return False

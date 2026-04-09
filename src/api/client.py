"""
백엔드 API HTTP 클라이언트.

모든 백엔드 API 호출은 이 모듈을 통해서만 수행한다 (직접 HTTP 호출 금지).
재시도, 타임아웃, 에러 핸들링을 내장한다.
"""

from __future__ import annotations

from typing import Any

import httpx

from config.loader import get_settings
from src.api.contracts import (
    GraphCumulativeData,
    LoadResponse,
    SaveRequest,
    SaveResponse,
)
from src.utils.retry import with_retry


class BackendClient:
    """
    백엔드 REST API 비동기 클라이언트.

    사용 예시:
        client = BackendClient()
        result = await client.save("learning", SaveRequest(...))
        data = await client.load("learning", user_id="user_123")
    """

    def __init__(self, base_url: str | None = None) -> None:
        """
        클라이언트를 초기화한다.

        Args:
            base_url: API 기본 URL (None이면 설정에서 자동 로드)
        """
        settings = get_settings()
        self._base_url = base_url or settings.api_base_url
        self._timeout = settings.api_timeout
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        """HTTP 클라이언트 리소스를 정리한다."""
        await self._client.aclose()

    @with_retry(max_retries=3, base_delay=1.0)
    async def save(self, resource: str, data: SaveRequest) -> SaveResponse:
        """
        데이터를 백엔드에 저장한다.

        Args:
            resource: 리소스 경로 (예: "learning", "emotion_log")
            data: 저장할 데이터 (SaveRequest 스키마)

        Returns:
            저장 결과 (SaveResponse)

        Raises:
            httpx.HTTPStatusError: HTTP 에러 응답 시
        """
        response = await self._client.post(
            f"{self._base_url}/{resource}",
            json=data.model_dump(mode="json"),
        )
        response.raise_for_status()
        return SaveResponse.model_validate(response.json())  # type: ignore[no-any-return]

    @with_retry(max_retries=3, base_delay=1.0)
    async def load(
        self,
        resource: str,
        user_id: str,
        **params: Any,
    ) -> LoadResponse:
        """
        백엔드에서 데이터를 조회한다.

        Args:
            resource: 리소스 경로 (예: "learning", "sessions")
            user_id: 사용자 고유 ID
            **params: 추가 쿼리 파라미터 (type, limit, page 등)

        Returns:
            조회 결과 (LoadResponse)

        Raises:
            httpx.HTTPStatusError: HTTP 에러 응답 시
        """
        response = await self._client.get(
            f"{self._base_url}/{resource}",
            params={"user_id": user_id, **params},
        )
        response.raise_for_status()
        return LoadResponse.model_validate(response.json())  # type: ignore[no-any-return]

    @with_retry(max_retries=3, base_delay=1.0)
    async def update(self, resource: str, data: SaveRequest) -> SaveResponse:
        """
        백엔드에 데이터를 갱신(UPSERT)한다.

        Args:
            resource: 리소스 경로 (예: "graph_nodes")
            data: 갱신할 데이터 (SaveRequest 스키마)

        Returns:
            갱신 결과 (SaveResponse)

        Raises:
            httpx.HTTPStatusError: HTTP 에러 응답 시
        """
        response = await self._client.put(
            f"{self._base_url}/{resource}",
            json=data.model_dump(mode="json"),
        )
        response.raise_for_status()
        return SaveResponse.model_validate(response.json())  # type: ignore[no-any-return]

    async def load_graph_cumulative(self, user_id: str) -> GraphCumulativeData | None:
        """사용자의 누적 그래프 데이터를 조회한다.

        반환값:
          - GraphCumulativeData(nodes=[], links=[]) : 신규 사용자 (HTTP 404 — 정상)
          - GraphCumulativeData(nodes=[...], ...)  : 기존 사용자 (HTTP 200 — 정상)
          - None                                   : GET 실패 (5xx, 네트워크 에러 등)

        Args:
            user_id: 사용자 고유 ID

        Returns:
            GraphCumulativeData (신규 또는 기존 사용자) | None (에러)
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/graph_nodes",
                params={"user_id": user_id},
            )
            if response.status_code == 404:
                return GraphCumulativeData()
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            inner = body.get("data", {}).get("data") or {}
            return GraphCumulativeData.model_validate(inner)  # type: ignore[no-any-return]
        except Exception:
            return None

    async def put_graph_cumulative(self, data: SaveRequest) -> bool:
        """누적 그래프 데이터를 백엔드에 저장(UPSERT)한다.

        HTTP status_code AND 응답 body의 code 필드를 모두 검증한다.
        Backend 실제 응답: {"code":"ok","message":"성공"}

        Args:
            data: SaveRequest 스키마 (type="graph_cumulative")

        Returns:
            HTTP 2xx + code=="ok" 시 True, 그 외 False
        """
        try:
            response = await self._client.put(
                f"{self._base_url}/graph_nodes",
                json=data.model_dump(mode="json"),
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            return isinstance(body, dict) and body.get("code") == "ok"
        except Exception:
            return False

"""
백엔드 API HTTP 클라이언트.

모든 백엔드 API 호출은 이 모듈을 통해서만 수행한다 (직접 HTTP 호출 금지).
재시도, 타임아웃, 에러 핸들링을 내장한다.
"""

from __future__ import annotations

from typing import Any

import httpx

from config.loader import get_settings
from src.api.contracts import LoadResponse, SaveRequest, SaveResponse
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
        return SaveResponse.model_validate(response.json())

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
        return LoadResponse.model_validate(response.json())

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
        return SaveResponse.model_validate(response.json())

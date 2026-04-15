"""
백엔드 API HTTP 클라이언트.

모든 백엔드 API 호출은 이 모듈을 통해서만 수행한다 (직접 HTTP 호출 금지).
재시도, 타임아웃, 에러 핸들링을 내장한다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from config.loader import get_settings
from src.api.backend_resources import (
    RESOURCE_MIND_FREQUENCIES,
    RESOURCE_PODCAST_EPISODES,
)
from src.api.contracts import (
    GraphCumulativeData,
    LoadResponse,
    SaveRequest,
    SaveResponse,
)
from src.utils.logger import get_agent_logger
from src.utils.retry import with_retry

_logger = get_agent_logger("client")


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
            base_url: API 기본 URL (None이면 설정에서 자동 로드).
                      내부 저장 API 경로 기준.
                      사용자 프로필 조회는 별도 _profile_base_url(호스트만) 사용.
                      지식 문서 조회/적재는 별도 _knowledge_base_url 사용.
        """
        settings = get_settings()
        self._base_url = base_url or settings.api_base_url
        parsed = urlparse(self._base_url)
        self._profile_base_url = f"{parsed.scheme}://{parsed.netloc}"
        self._graph_base_url = f"{parsed.scheme}://{parsed.netloc}/api/v1"
        # 지식 문서 전용 URL: BACKEND_API_URL의 경로와 무관하게 호스트 기준으로 고정
        # GET /api/internal/knowledge?ids=...  (KnowledgeAgent 조회)
        # POST /api/internal/knowledge         (ingest 적재)
        self._knowledge_base_url = f"{parsed.scheme}://{parsed.netloc}/api/internal/knowledge"
        self._timeout = settings.api_timeout
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            event_hooks={
                "request": [self._on_request],
                "response": [self._on_response],
            },
        )

    async def close(self) -> None:
        """HTTP 클라이언트 리소스를 정리한다."""
        await self._client.aclose()

    async def _on_request(self, request: httpx.Request) -> None:
        """HTTP 요청 로깅 이벤트 훅."""
        content_length = len(request.content) if request.content else 0
        _logger.info(
            "[BackendClient] HTTP 요청",
            extra={
                "method": request.method,
                "url": str(request.url),
                "content_length": content_length,
            },
        )

    async def _on_response(self, response: httpx.Response) -> None:
        """HTTP 응답 로깅 이벤트 훅 (모든 응답 상세 로깅)."""
        try:
            response_body = response.text[:1000]
        except Exception:
            response_body = "[응답 본문 읽기 실패]"

        if response.status_code >= 400:
            # 에러 응답: ERROR 레벨
            _logger.error(
                "[BackendClient] HTTP 에러 응답",
                extra={
                    "status_code": response.status_code,
                    "url": str(response.request.url),
                    "response_body": response_body,
                    "headers": dict(response.headers),
                },
            )
        else:
            # 성공 응답 (200-399): INFO 레벨
            _logger.info(
                "[BackendClient] HTTP 성공 응답",
                extra={
                    "status_code": response.status_code,
                    "url": str(response.request.url),
                    "response_body": response_body,
                    "content_length": len(response_body),
                },
            )

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

    @with_retry(max_retries=3, base_delay=1.0)
    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """
        백엔드에서 사용자 프로필을 조회한다.
        GET {host}/internal/users/{user_id}/profile

        Args:
            user_id: 조회할 사용자 고유 ID

        Returns:
            사용자 프로필 데이터 딕셔너리
        """
        response = await self._client.get(
            f"{self._profile_base_url}/internal/users/{user_id}/profile"
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    async def ingest_mind_frequencies(
        self, session_id: str, keywords: list[str], description: str
    ) -> None:
        """mind-frequencies 수집 엔드포인트 호출 (fire-and-forget).

        POST {base_url}/mind-frequencies
        실패 시 ERROR 로그만 기록하고 파이프라인에 영향을 주지 않는다.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/{RESOURCE_MIND_FREQUENCIES}",
                json={
                    "session_id": session_id,
                    "keywords": keywords,
                    "description": description,
                },
            )
            response.raise_for_status()
            _logger.info(
                "[BackendClient] ingest_mind_frequencies OK (session=%s, keywords=%d개)",
                session_id,
                len(keywords),
            )
        except Exception as e:
            _logger.error(
                "[BackendClient] ingest_mind_frequencies FAILED (session=%s): %s",
                session_id,
                e,
            )

    async def ingest_podcast_episodes(
        self,
        session_id: str,
        image_url: str,
        text: str,
        title: str = "",
    ) -> None:
        """podcast_episodes 수집 → 백엔드 podcasts 테이블.

        POST {base_url}/podcast_episodes
        백엔드 자동 채움: id(PK,UUID), user_id, created_at
        AI 서버 전송: session_id, image_url, text, title
        """
        payload = {
            "session_id": session_id,
            "image_url": image_url,
            "text": text,
            "title": title,
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/{RESOURCE_PODCAST_EPISODES}",
                json=payload,
            )
            response.raise_for_status()
            _logger.info(
                "[ingest_podcast_episodes] 성공",
                extra={
                    "session_id": session_id,
                    "status_code": response.status_code,
                },
            )
        except httpx.HTTPStatusError as e:
            try:
                response_body = e.response.text[:1000]
            except Exception:
                response_body = "[응답 본문 읽기 실패]"
            _logger.error(
                "[ingest_podcast_episodes] HTTP 에러",
                extra={
                    "status_code": e.response.status_code,
                    "endpoint": RESOURCE_PODCAST_EPISODES,
                    "response_body": response_body,
                    "session_id": session_id,
                    "payload_keys": list(payload.keys()),
                },
            )
            raise
        except Exception as e:
            _logger.error(
                "[ingest_podcast_episodes] 예외 발생",
                extra={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "session_id": session_id,
                },
            )
            raise

    async def fetch_knowledge_documents(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """
        지식 문서 청크 원문을 Backend RDB에서 조회한다.

        GET {host}/api/internal/knowledge?ids=id1,id2,...

        Args:
            chunk_ids: Pinecone에서 검색된 청크 ID 목록

        Returns:
            문서 데이터 목록. 실패 시 빈 리스트 반환 (graceful degradation)
        """
        if not chunk_ids:
            return []
        try:
            response = await self._client.get(
                self._knowledge_base_url,
                params={"ids": ",".join(chunk_ids)},
                timeout=10.0,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data.get("data", [])  # type: ignore[no-any-return]
        except Exception:
            _logger.error(
                "[BackendClient] 지식 문서 조회 실패 (요청=%d건)", len(chunk_ids), exc_info=True
            )
            return []

    async def ingest_knowledge_chunk(
        self,
        chunk_id: str,
        title: str,
        content: str,
        page: int,
        source: str,
        domain: str,
    ) -> None:
        """
        지식 문서 청크를 Backend RDB에 적재한다.

        POST {host}/api/internal/knowledge

        실패 시 ERROR 로그만 기록하고 예외를 전파한다 (ingest 스크립트에서 개별 처리).
        """
        response = await self._client.post(
            self._knowledge_base_url,
            json={
                "id": chunk_id,
                "title": title,
                "content": content,
                "page": page,
                "source": source,
                "domain": domain,
            },
            timeout=10.0,
        )
        response.raise_for_status()

    async def load_graph_cumulative(self, user_id: str) -> GraphCumulativeData | None:
        """사용자의 누적 그래프 데이터를 조회한다."""
        try:
            response = await self._client.get(
                f"{self._graph_base_url}/graph_nodes",
                params={"user_id": user_id},
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            inner = body.get("data", {}).get("data") or {}
            return GraphCumulativeData.model_validate(inner)  # type: ignore[no-any-return]
        except Exception:
            return None

    async def put_graph_cumulative(self, data: SaveRequest) -> bool:
        """누적 그래프 데이터를 백엔드에 저장(UPSERT)한다."""
        try:
            body = {
                "user_id": data.user_id,
                "type": data.type,
                "data": data.data,
            }
            response = await self._client.put(
                f"{self._graph_base_url}/graph_nodes",
                json=body,
            )
            response.raise_for_status()
            resp_body: dict[str, Any] = response.json()
            return isinstance(resp_body, dict) and resp_body.get("code") == "ok"
        except Exception:
            return False

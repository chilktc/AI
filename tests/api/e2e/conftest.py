"""
백엔드 연동 E2E 테스트 전용 Fixture.

실제 Backend 서버(app-3)에 HTTP 요청을 보내어
AI 서버 ↔ Backend 서버 간 통신을 검증한다.

사용법:
    # 백엔드 URL 지정
    pytest tests/api/e2e/ -v -m live --backend-url=http://10.7.10.20:8080

    # 환경변수로 지정
    BACKEND_API_URL=http://10.7.10.20:8080/api/v1 pytest tests/api/e2e/ -v -m live
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import httpx
import pytest

from src.api.client import BackendClient

# ---------------------------------------------------------------------------
# CLI 옵션 등록
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    """--backend-url 커스텀 CLI 옵션 등록."""
    parser.addoption(
        "--backend-url",
        action="store",
        default=None,
        help="Backend 서버 URL (예: http://10.7.10.20:8080)",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def backend_url(request: pytest.FixtureRequest) -> str:
    """Backend 서버 URL을 결정한다.

    우선순위:
        1. --backend-url CLI 옵션
        2. BACKEND_API_URL 환경변수
        3. 기본값 (http://localhost:8080)
    """
    cli_url = request.config.getoption("--backend-url", default=None)
    if cli_url:
        return cli_url.rstrip("/")

    env_url = os.getenv("BACKEND_API_URL", "")
    if env_url:
        # 환경변수가 /api/v1 까지 포함할 수 있으므로 base만 추출
        parsed = urlparse(env_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    return "http://localhost:8080"


@pytest.fixture(scope="session")
def backend_api_url(backend_url: str) -> str:
    """Backend API v1 전체 경로."""
    return f"{backend_url}/api/v1"


@pytest.fixture(scope="session")
def backend_host_port(backend_url: str) -> tuple[str, int]:
    """Backend URL에서 host와 port를 추출한다."""
    parsed = urlparse(backend_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    return host, port


@pytest.fixture(scope="session")
def is_backend_reachable(backend_host_port: tuple[str, int]) -> bool:
    """Backend 서버에 TCP 연결이 가능한지 확인한다."""
    host, port = backend_host_port
    try:
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
        return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


@pytest.fixture
def skip_if_no_backend(is_backend_reachable: bool) -> None:
    """Backend 서버에 연결할 수 없으면 테스트를 건너뛴다."""
    if not is_backend_reachable:
        pytest.skip("Backend 서버에 연결할 수 없습니다 (--backend-url 확인)")


@pytest.fixture
async def real_backend_client(backend_api_url: str) -> BackendClient:
    """실제 BackendClient 인스턴스 (mock 아님).

    테스트 종료 시 자동으로 리소스를 정리한다.
    """
    client = BackendClient(base_url=backend_api_url)
    yield client  # type: ignore[misc]
    await client.close()


@pytest.fixture(scope="session")
def http_client() -> httpx.Client:
    """동기 HTTP 클라이언트 (헬스체크 등 간단한 요청용)."""
    client = httpx.Client(timeout=5)
    yield client  # type: ignore[misc]
    client.close()

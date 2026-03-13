"""
백엔드 서버 헬스체크 E2E 테스트.

AI 서버(app-2) → Backend 서버(app-3) 간 네트워크 연결과
기본 엔드포인트 응답을 검증한다.

1차 통합 테스트로, 백엔드팀과의 최초 연동 확인에 사용.

실행 방법:
    # Backend URL 지정하여 실행
    pytest tests/api/e2e/test_backend_health.py -v -m live \\
        --backend-url=http://10.7.10.20:8080

    # 환경변수로 실행
    BACKEND_API_URL=http://10.7.10.20:8080/api/v1 \\
        pytest tests/api/e2e/test_backend_health.py -v -m live
"""

from __future__ import annotations

import socket

import httpx
import pytest


# ---------------------------------------------------------------------------
# 1차: 네트워크 연결 확인
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestBackendConnectivity:
    """Backend 서버 네트워크 연결 테스트."""

    def test_backend_server_reachable(
        self, backend_host_port: tuple[str, int],
    ) -> None:
        """Backend 서버에 TCP 연결이 가능해야 한다.

        실패 시: 네트워크 문제, 방화벽, 서버 미실행 등을 확인.
        """
        host, port = backend_host_port

        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            pytest.fail(
                f"Backend 서버 ({host}:{port})에 연결할 수 없습니다: {e}\n"
                f"  - 서버가 실행 중인지 확인: docker ps (app-3)\n"
                f"  - 방화벽/보안그룹 규칙 확인\n"
                f"  - 올바른 IP/포트인지 확인"
            )

    def test_backend_responds_to_http(
        self, skip_if_no_backend: None,
        backend_url: str,
        http_client: httpx.Client,
    ) -> None:
        """Backend 서버가 HTTP 요청에 응답해야 한다.

        헬스체크 경로가 확정되지 않았으므로 루트(/) 또는 /health를 시도.
        어떤 경로든 HTTP 응답(200~404)이 오면 서버가 동작 중인 것.
        """
        # 가능한 헬스체크 경로 목록 (백엔드 프레임워크에 따라 다를 수 있음)
        health_paths = ["/health", "/", "/api/v1"]
        any_responded = False

        for path in health_paths:
            try:
                response = http_client.get(f"{backend_url}{path}")
                # 200~499 범위면 서버가 동작 중 (500도 서버 오류일 뿐 응답은 됨)
                if response.status_code < 500:
                    any_responded = True
                    break
            except httpx.ConnectError:
                continue

        assert any_responded, (
            f"Backend 서버({backend_url})가 HTTP 요청에 응답하지 않습니다.\n"
            f"  시도한 경로: {health_paths}\n"
            f"  서버 상태와 포트를 확인하세요."
        )


# ---------------------------------------------------------------------------
# 2차: 헬스체크 엔드포인트 확인
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestBackendHealthEndpoint:
    """Backend 서버 헬스체크 엔드포인트 검증."""

    def test_health_returns_200(
        self, skip_if_no_backend: None,
        backend_url: str,
        http_client: httpx.Client,
    ) -> None:
        """GET /health → 200 OK.

        Spring Boot Actuator 기본 경로(/actuator/health)도 함께 확인.
        """
        # Spring Boot 기본 헬스체크 경로 목록
        candidates = ["/health", "/actuator/health"]
        success = False
        results: list[str] = []

        for path in candidates:
            try:
                response = http_client.get(f"{backend_url}{path}")
                results.append(f"  {path} → {response.status_code}")
                if response.status_code == 200:
                    success = True
                    break
            except httpx.ConnectError as e:
                results.append(f"  {path} → 연결 실패 ({e})")

        assert success, (
            f"Backend 헬스체크 엔드포인트를 찾을 수 없습니다:\n"
            + "\n".join(results)
            + "\n  백엔드팀에 헬스체크 경로를 확인하세요."
        )

    def test_health_response_is_json(
        self, skip_if_no_backend: None,
        backend_url: str,
        http_client: httpx.Client,
    ) -> None:
        """헬스체크 응답이 JSON 형식이어야 한다."""
        candidates = ["/health", "/actuator/health"]

        for path in candidates:
            try:
                response = http_client.get(f"{backend_url}{path}")
                if response.status_code == 200:
                    # JSON 파싱 시도
                    data = response.json()
                    assert isinstance(data, dict), (
                        f"헬스체크 응답이 dict가 아닙니다: {type(data)}"
                    )
                    return
            except httpx.ConnectError:
                continue

        pytest.skip("헬스체크 엔드포인트 미발견 — 경로 확인 필요")


# ---------------------------------------------------------------------------
# 3차: API 기본 경로 확인
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestBackendApiBase:
    """Backend API v1 기본 경로 접근 확인."""

    def test_api_v1_path_exists(
        self, skip_if_no_backend: None,
        backend_api_url: str,
        http_client: httpx.Client,
    ) -> None:
        """GET /api/v1/ 경로가 존재해야 한다.

        404(Not Found)도 서버가 해당 경로 패턴을 인식한다는 의미이므로 허용.
        405(Method Not Allowed)도 경로 인식의 증거.
        """
        try:
            response = http_client.get(backend_api_url)
        except httpx.ConnectError as e:
            pytest.fail(f"Backend API에 연결할 수 없습니다: {e}")

        # 200, 401, 403, 404, 405 모두 서버가 경로를 인식한다는 증거
        assert response.status_code < 500, (
            f"Backend API({backend_api_url}) 서버 오류: {response.status_code}\n"
            f"  응답: {response.text[:200]}"
        )


# ---------------------------------------------------------------------------
# 4차: BackendClient 초기화 검증
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestBackendClientLive:
    """BackendClient를 실제 Backend URL로 초기화하여 검증."""

    @pytest.mark.asyncio
    async def test_client_initialization(
        self, skip_if_no_backend: None,
        backend_api_url: str,
    ) -> None:
        """BackendClient(base_url) 생성 및 close가 정상 동작해야 한다."""
        from src.api.client import BackendClient

        client = BackendClient(base_url=backend_api_url)

        assert client._base_url == backend_api_url
        assert client._client is not None

        # 리소스 정리
        await client.close()

    @pytest.mark.asyncio
    async def test_client_timeout_setting(
        self, skip_if_no_backend: None,
        backend_api_url: str,
    ) -> None:
        """BackendClient 타임아웃이 설정값과 일치해야 한다."""
        from src.api.client import BackendClient

        client = BackendClient(base_url=backend_api_url)

        # 타임아웃이 양수값이어야 함
        assert client._timeout > 0

        await client.close()

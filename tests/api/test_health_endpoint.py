"""
Health Check 엔드포인트 테스트.

GET /health (ALB Liveness)과 GET /health/ready (Readiness Probe) 검증.
"""

from __future__ import annotations


class TestHealthCheck:
    """GET /health 엔드포인트 테스트."""

    def test_health_returns_200(self, test_client) -> None:
        """ALB 헬스체크: 200 OK와 status=ok 반환."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestReadyCheck:
    """GET /health/ready 엔드포인트 테스트."""

    def test_ready_returns_200_when_all_ok(self, test_client) -> None:
        """모든 컴포넌트 정상 시 200 OK와 status=ready 반환."""
        response = test_client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert isinstance(data["components"], dict)
        assert data["components"]["graph"] == "ok"
        assert data["components"]["backend_client"] == "ok"
        assert "storage_mode" in data
        assert isinstance(data["storage_mode"], str)

    def test_ready_graph_not_ready(self, test_client_not_ready) -> None:
        """compiled_graph=None 시 status=not_ready."""
        response = test_client_not_ready.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["components"]["graph"] == "not_ready"

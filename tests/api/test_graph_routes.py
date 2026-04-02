"""routes/graph.py API 테스트.

Neo4j를 mock하여 /internal/graph 엔드포인트를 검증한다.

Python 3.9 호환을 위해 graph 라우터만 독립 FastAPI 앱에
마운트하여 src.api.main의 깊은 임포트 체인(StrEnum, Self)을 우회한다.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Python 3.11+ 전용 모듈(Self, StrEnum) 임포트 체인 우회
# routes/__init__.py → podcasts → external_schemas(StrEnum)
# graph.py → src.db.factory → src.db.base(Self)
for _mod in (
    "src.api.external_schemas",
    "src.api.routes.podcasts",
    "src.api.routes.sessions",
    "src.db.base",
    "src.db",
    "src.db.factory",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# create_graph_client mock 설정
sys.modules["src.db.factory"].create_graph_client = MagicMock()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.routes.graph import router as graph_router  # noqa: E402

_test_app = FastAPI()
_test_app.include_router(graph_router)


@pytest.fixture
def mock_graph_client():
    """Neo4j GraphClient async context manager mock."""
    client = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


@pytest.fixture
def graph_test_client(mock_graph_client):
    """graph.py 테스트 전용 TestClient."""
    cm, _ = mock_graph_client
    with patch("src.api.routes.graph.create_graph_client", return_value=cm):
        yield TestClient(_test_app, raise_server_exceptions=False)


class TestGetUserGraphData:
    def test_normal_response(self, mock_graph_client, graph_test_client) -> None:
        _, client = mock_graph_client

        # 1차 쿼리: 노드+링크
        client.execute_query.side_effect = [
            [
                {
                    "id": "n1",
                    "name": "업무 과부하",
                    "grp": "work_structure",
                    "intensity": 0.8,
                    "target_id": "n2",
                },
                {
                    "id": "n2",
                    "name": "상사 갈등",
                    "grp": "leadership",
                    "intensity": 0.5,
                    "target_id": None,
                },
            ],
            # 2차: frequent_keywords
            [{"frequent_keywords": [{"tags": ["과부하", "갈등"], "count": 3}]}],
            # 3차: category_distribution
            [
                {"category": "work_structure", "count": 5},
                {"category": "leadership", "count": 3},
            ],
        ]

        resp = graph_test_client.get("/internal/graph/users/user123/data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["nodes"]) == 2
        assert data["data"]["nodes"][0]["id"] == "b1"  # work_structure prefix
        assert data["data"]["nodes"][1]["id"] == "p1"  # leadership prefix
        assert len(data["data"]["links"]) == 1
        assert data["data"]["links"][0]["source"] == "b1"
        assert data["data"]["links"][0]["target"] == "p1"

    def test_empty_result(self, mock_graph_client, graph_test_client) -> None:
        _, client = mock_graph_client
        client.execute_query.side_effect = [[], [], []]

        resp = graph_test_client.get("/internal/graph/users/unknown_user/data")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["nodes"] == []
        assert data["data"]["links"] == []
        assert data["data"]["frequent_keywords"] == []
        assert data["data"]["category_distribution"] == {}

    def test_neo4j_error_returns_error_response(self, graph_test_client) -> None:
        with patch(
            "src.api.routes.graph.create_graph_client",
            side_effect=Exception("Neo4j connection failed"),
        ):
            resp = graph_test_client.get("/internal/graph/users/user123/data")
            assert resp.status_code == 200  # 에러도 200 + success=False
            data = resp.json()
            assert data["success"] is False
            assert data["error"]["code"] == "GRAPH_QUERY_ERROR"

    def test_limit_parameter(self, mock_graph_client, graph_test_client) -> None:
        _, client = mock_graph_client
        client.execute_query.side_effect = [[], [], []]

        resp = graph_test_client.get("/internal/graph/users/user123/data?limit=500")
        assert resp.status_code == 200

    def test_limit_exceeds_max(self, graph_test_client) -> None:
        resp = graph_test_client.get("/internal/graph/users/user123/data?limit=501")
        assert resp.status_code == 422

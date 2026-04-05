"""
환경별 클라이언트 팩토리.

storage_mode(settings.yaml → 환경변수 fallback)에 따라
직접 클라이언트 또는 Backend API 프록시를 반환한다.

모드:
  local    개발: 모든 DB 직접 접속
  proxy    배포: 모든 DB Backend API 경유
  hybrid   배포 변형: Pinecone+Neo4j 직접, MySQL Backend 경유

환경변수:
  S3_MODE  (선택) S3만 별도 모드 — storage_mode와 독립적으로 지정

사용법:
    from src.db.factory import create_vector_client
    client = create_vector_client()
"""

from __future__ import annotations

import os

from config.loader import get_settings
from src.db.base import BaseGraphClient, BaseRDBClient, BaseStorageClient, BaseVectorClient


def create_vector_client() -> BaseVectorClient:
    """벡터 DB 클라이언트를 생성한다.

    local/hybrid: Pinecone 직접 접속
    proxy: Backend API 경유
    """
    mode = get_settings().storage_mode
    if mode == "proxy":
        from src.api.client import BackendClient
        from src.db.api_proxy import VectorProxyClient

        return VectorProxyClient(BackendClient())

    from src.db.pinecone_client import PineconeClient

    return PineconeClient()


def create_graph_client() -> BaseGraphClient:
    """그래프 DB 클라이언트를 생성한다.

    local/hybrid: Neo4j 직접 접속
    proxy: Backend API 경유
    """
    mode = get_settings().storage_mode
    if mode == "proxy":
        from src.api.client import BackendClient
        from src.db.api_proxy import GraphProxyClient

        return GraphProxyClient(BackendClient())

    from src.db.neo4j_client import Neo4jClient

    return Neo4jClient()


def create_rdb_client() -> BaseRDBClient:
    """관계형 DB 클라이언트를 생성한다.

    local: MySQL 직접 접속
    proxy/hybrid: Backend API 경유 (hybrid에서 MySQL만 Backend 경유)
    """
    mode = get_settings().storage_mode
    if mode in ("proxy", "hybrid"):
        from src.api.client import BackendClient
        from src.db.api_proxy import RDBProxyClient

        return RDBProxyClient(BackendClient())

    from src.db.mysql_client import MySQLClient

    return MySQLClient()


def create_storage_client() -> BaseStorageClient:
    """오브젝트 스토리지 클라이언트를 생성한다.

    S3_MODE 환경변수가 있으면 STORAGE_MODE 대신 사용.
    proxy: Backend API 경유
    그 외: S3 직접 접속
    """
    s3_mode = os.getenv("S3_MODE", get_settings().storage_mode)
    if s3_mode == "proxy":
        from src.api.client import BackendClient
        from src.db.api_proxy import StorageProxyClient

        return StorageProxyClient(BackendClient())

    from src.db.s3_client import S3Client

    return S3Client()

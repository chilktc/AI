"""
저장소 추상화 패키지.

전략 패턴 + 팩토리로 환경별 DB 접근 방식을 전환한다.
STORAGE_MODE 환경변수에 따라 직접/프록시 구현체를 자동 선택.

사용법:
    from src.db import create_vector_client, create_storage_client
    vector_client = create_vector_client()
    s3_client = create_storage_client()
"""

from src.db.base import (
    BaseGraphClient,
    BaseRDBClient,
    BaseStorageClient,
    BaseVectorClient,
)
from src.db.factory import (
    create_graph_client,
    create_rdb_client,
    create_storage_client,
    create_vector_client,
)

__all__ = [
    "BaseVectorClient",
    "BaseGraphClient",
    "BaseRDBClient",
    "BaseStorageClient",
    "create_vector_client",
    "create_graph_client",
    "create_rdb_client",
    "create_storage_client",
]

"""
S3 오브젝트 스토리지 클라이언트.

C-3(읽기: s3:Get*, s3:List*) + 4-4(쓰기: s3:PutObject) 통합.
boto3는 동기 라이브러리이므로 asyncio.to_thread()로 래핑한다.

사용법:
    async with S3Client() as client:
        data = await client.get_object("vis/user123/cover.png")
        await client.put_object("vis/user123/new.png", image_bytes, "image/png")
        url = await client.generate_presigned_url("vis/user123/cover.png")
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import boto3

from src.db.base import BaseStorageClient

logger = logging.getLogger(__name__)


class S3Client(BaseStorageClient):
    """S3 직접 클라이언트 (boto3 + asyncio.to_thread).

    읽기(C-3)와 쓰기(4-4) 모두 지원.
    쓰기 권한이 없으면 put_object가 ClientError를 전달한다.

    환경변수:
        AWS_S3_BUCKET: S3 버킷명
        AWS_REGION: AWS 리전
    """

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
    ) -> None:
        self._bucket = bucket or os.getenv("AWS_S3_BUCKET", "mindlog-images")
        self._region = region or os.getenv("AWS_REGION", "ap-northeast-2")
        self._client = boto3.client("s3", region_name=self._region)

    async def get_object(self, key: str) -> bytes:
        """S3 오브젝트를 읽는다."""
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=key,
        )
        body = response["Body"]
        data: bytes = await asyncio.to_thread(body.read)
        return data

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "",
    ) -> dict[str, Any]:
        """S3에 오브젝트를 업로드한다.

        TODO(backend): 4-4 업로드 prefix 구조 확정 (현재: vis/{user_id}/{id}/)
        """
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        result: dict[str, Any] = await asyncio.to_thread(self._client.put_object, **kwargs)
        return result

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 100,
    ) -> list[dict[str, Any]]:
        """S3 오브젝트 목록을 조회한다."""
        response = await asyncio.to_thread(
            self._client.list_objects_v2,
            Bucket=self._bucket,
            Prefix=prefix,
            MaxKeys=max_keys,
        )
        return list(response.get("Contents", []))

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """S3 Presigned URL을 생성한다."""
        url: str = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url

    async def close(self) -> None:
        """boto3 클라이언트 리소스를 정리한다."""
        logger.debug("S3Client closed")

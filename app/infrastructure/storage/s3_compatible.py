import asyncio
from functools import cached_property

import boto3


class S3CompatibleFileStorage:
    """FileStorage over the S3 API. Serves both real AWS S3 and MinIO -- MinIO
    is just S3 with `endpoint_url` set and path-style addressing; everything
    else about the API is identical. `boto3` is synchronous, so every call is
    wrapped in `asyncio.to_thread` rather than pulling in `aioboto3`.
    """

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._endpoint_url = endpoint_url

    @cached_property
    def _client(self):
        return boto3.client(
            "s3",
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            endpoint_url=self._endpoint_url,
            config=boto3.session.Config(
                s3={"addressing_style": "path"} if self._endpoint_url else {}
            ),
        )

    async def upload(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
        )

    async def download(self, key: str) -> bytes:
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        return response["Body"].read()

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

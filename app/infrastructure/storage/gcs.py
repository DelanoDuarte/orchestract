import asyncio
import datetime
from functools import cached_property

from google.cloud import storage
from google.oauth2 import service_account


class GCSFileStorage:
    """FileStorage over Google Cloud Storage. `google-cloud-storage`'s client
    is synchronous, so calls are wrapped in `asyncio.to_thread`, matching the
    S3-compatible adapter.
    """

    def __init__(self, bucket: str, service_account_info: dict) -> None:
        self._bucket_name = bucket
        self._service_account_info = service_account_info

    @cached_property
    def _bucket(self):
        credentials = service_account.Credentials.from_service_account_info(self._service_account_info)
        client = storage.Client(credentials=credentials, project=credentials.project_id)
        return client.bucket(self._bucket_name)

    async def upload(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._upload, key, content, content_type)

    def _upload(self, key: str, content: bytes, content_type: str) -> None:
        self._bucket.blob(key).upload_from_string(content, content_type=content_type)

    async def download(self, key: str) -> bytes:
        return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._bucket.blob(key).generate_signed_url,
            expiration=datetime.timedelta(seconds=expires_in),
        )

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._bucket.blob(key).delete)

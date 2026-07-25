from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None


@dataclass(frozen=True)
class ExternalFile:
    id: str
    name: str
    mime_type: str
    size: int | None
    modified_at: datetime | None


class FileStorage(Protocol):
    """Write/read access to a configured storage backend (S3, GCS, MinIO, local disk)."""

    async def upload(self, key: str, content: bytes, content_type: str) -> None: ...

    async def download(self, key: str) -> bytes: ...

    async def get_url(self, key: str, expires_in: int = 3600) -> str: ...

    async def delete(self, key: str) -> None: ...


class FileConnector(Protocol):
    """Read-only OAuth access to a user's external drive (Google Drive, OneDrive)."""

    def get_authorization_url(self, state: str) -> str: ...

    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens: ...

    async def list_files(self, tokens: OAuthTokens, folder_id: str | None = None) -> list[ExternalFile]: ...

    async def download_file(self, tokens: OAuthTokens, file_id: str) -> tuple[bytes, str, str]:
        """Returns (content, filename, content_type)."""
        ...

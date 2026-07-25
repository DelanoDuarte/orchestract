from typing import Protocol

from app.domain.storage.models import StorageConnection, StorageProvider


class StorageConnectionRepository(Protocol):
    async def add(self, connection: StorageConnection) -> None: ...

    async def get(self, connection_id: int) -> StorageConnection | None: ...

    async def get_by_org_and_provider(
        self, organization_id: int, provider: StorageProvider
    ) -> StorageConnection | None: ...

    async def get_primary_for_organization(self, organization_id: int) -> StorageConnection | None: ...

    async def list_for_organization(self, organization_id: int) -> list[StorageConnection]: ...

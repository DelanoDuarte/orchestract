from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.storage.models import StorageConnection, StorageProvider


class SqlAlchemyStorageConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, connection: StorageConnection) -> None:
        self._session.add(connection)
        await self._session.flush()
        # See SqlAlchemyWorkflowDefinitionRepository.add for why this refresh
        # is needed: flush() doesn't populate selectin relationships for a
        # freshly-added object, so accessing `.credential` after the session
        # closes would otherwise raise DetachedInstanceError.
        await self._session.refresh(connection, attribute_names=["credential"])

    async def get(self, connection_id: int) -> StorageConnection | None:
        return await self._session.get(StorageConnection, connection_id)

    async def get_by_org_and_provider(
        self, organization_id: int, provider: StorageProvider
    ) -> StorageConnection | None:
        result = await self._session.execute(
            select(StorageConnection).where(
                StorageConnection.organization_id == organization_id,
                StorageConnection.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def get_primary_for_organization(self, organization_id: int) -> StorageConnection | None:
        result = await self._session.execute(
            select(StorageConnection).where(
                StorageConnection.organization_id == organization_id,
                StorageConnection.is_primary.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: int) -> list[StorageConnection]:
        result = await self._session.execute(
            select(StorageConnection)
            .where(StorageConnection.organization_id == organization_id)
            .order_by(StorageConnection.created_at)
        )
        return list(result.scalars().all())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tenancy.models import Organization


class SqlAlchemyOrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        self._session.add(organization)
        await self._session.flush()

    async def get(self, organization_id: int) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def list(self) -> list[Organization]:
        result = await self._session.execute(select(Organization).order_by(Organization.name))
        return list(result.scalars().all())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import Role


class SqlAlchemyRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, role: Role) -> None:
        self._session.add(role)
        await self._session.flush()

    async def get(self, role_id: int) -> Role | None:
        return await self._session.get(Role, role_id)

    async def get_by_slug(self, organization_id: int, slug: str) -> Role | None:
        result = await self._session.execute(
            select(Role).where(Role.organization_id == organization_id, Role.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: int) -> list[Role]:
        result = await self._session.execute(
            select(Role).where(Role.organization_id == organization_id).order_by(Role.name)
        )
        return list(result.scalars().all())

    async def list_for_agent(self, agent_id: int) -> list[Role]:
        result = await self._session.execute(select(Role).where(Role.agent_id == agent_id))
        return list(result.scalars().all())

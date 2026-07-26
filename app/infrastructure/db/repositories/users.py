from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import User


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email.strip().lower()))
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: int) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.organization_id == organization_id).order_by(User.name)
        )
        return list(result.scalars().all())

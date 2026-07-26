from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import UserSession


class SqlAlchemyUserSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: UserSession) -> None:
        self._session.add(session)
        await self._session.flush()

    async def get_by_token(self, token: str) -> UserSession | None:
        result = await self._session.execute(select(UserSession).where(UserSession.token == token))
        return result.scalar_one_or_none()

    async def delete(self, token: str) -> None:
        await self._session.execute(delete(UserSession).where(UserSession.token == token))

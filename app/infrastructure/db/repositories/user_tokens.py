from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users.models import UserToken, UserTokenPurpose


class SqlAlchemyUserTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: UserToken) -> None:
        self._session.add(token)
        await self._session.flush()

    async def get_by_token(self, token: str, purpose: UserTokenPurpose) -> UserToken | None:
        result = await self._session.execute(
            select(UserToken).where(UserToken.token == token, UserToken.purpose == purpose)
        )
        return result.scalar_one_or_none()

    async def delete(self, token: str) -> None:
        await self._session.execute(delete(UserToken).where(UserToken.token == token))

    async def delete_for_user(self, user_id: int, purpose: UserTokenPurpose) -> None:
        await self._session.execute(
            delete(UserToken).where(UserToken.user_id == user_id, UserToken.purpose == purpose)
        )

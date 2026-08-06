from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.sharing.models import ShareLink


class SqlAlchemyShareLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, link: ShareLink) -> None:
        self._session.add(link)
        await self._session.flush()

    async def get(self, link_id: int) -> ShareLink | None:
        return await self._session.get(ShareLink, link_id)

    async def get_by_token(self, token: str) -> ShareLink | None:
        result = await self._session.execute(select(ShareLink).where(ShareLink.token == token))
        return result.scalar_one_or_none()

    async def list_for_contract(self, contract_id: int) -> list[ShareLink]:
        result = await self._session.execute(
            select(ShareLink)
            .where(ShareLink.contract_id == contract_id)
            .order_by(ShareLink.created_at.desc())
        )
        return list(result.scalars().all())

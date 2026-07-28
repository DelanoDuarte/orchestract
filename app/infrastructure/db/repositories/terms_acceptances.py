from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.compliance.models import TermsAcceptance


class SqlAlchemyTermsAcceptanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, acceptance: TermsAcceptance) -> None:
        self._session.add(acceptance)
        await self._session.flush()

    async def has_accepted(self, user_id: int, version: str) -> bool:
        result = await self._session.execute(
            select(TermsAcceptance.id)
            .where(TermsAcceptance.user_id == user_id, TermsAcceptance.version == version)
            .limit(1)
        )
        return result.first() is not None

    async def get_latest_for_user(self, user_id: int) -> TermsAcceptance | None:
        result = await self._session.execute(
            select(TermsAcceptance)
            .where(TermsAcceptance.user_id == user_id)
            .order_by(TermsAcceptance.accepted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: int) -> list[TermsAcceptance]:
        result = await self._session.execute(
            select(TermsAcceptance)
            .where(TermsAcceptance.organization_id == organization_id)
            .order_by(TermsAcceptance.accepted_at.desc())
        )
        return list(result.scalars().all())

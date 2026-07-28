from collections.abc import Callable

from app.domain.compliance.models import TermsAcceptance
from app.domain.compliance.terms import CURRENT_TERMS_VERSION
from app.infrastructure.db.unit_of_work import UnitOfWork


class ComplianceService:
    """Records and checks users' acceptance of the versioned Terms &
    Conditions. Acceptance is required to use the product (see the signup flow
    and the login gate in ``enforce_login_and_membership``)."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def record_acceptance(
        self,
        user_id: int,
        organization_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        version: str = CURRENT_TERMS_VERSION,
    ) -> TermsAcceptance:
        async with self._uow_factory() as uow:
            acceptance = TermsAcceptance.record(user_id, organization_id, version, ip_address, user_agent)
            await uow.terms_acceptances.add(acceptance)
            await uow.commit()
            return acceptance

    async def has_accepted_current(self, user_id: int) -> bool:
        async with self._uow_factory() as uow:
            return await uow.terms_acceptances.has_accepted(user_id, CURRENT_TERMS_VERSION)

    async def latest_acceptance(self, user_id: int) -> TermsAcceptance | None:
        async with self._uow_factory() as uow:
            return await uow.terms_acceptances.get_latest_for_user(user_id)

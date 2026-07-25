from collections.abc import Callable

from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.models import Organization
from app.infrastructure.db.unit_of_work import UnitOfWork


class OrganizationService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_organization(self, name: str) -> Organization:
        async with self._uow_factory() as uow:
            organization = Organization.create(name)
            await uow.organizations.add(organization)
            await uow.commit()
            return organization

    async def list_organizations(self) -> list[Organization]:
        async with self._uow_factory() as uow:
            return await uow.organizations.list()

    async def get(self, organization_id: int) -> Organization:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            return organization

    async def get_by_slug(self, slug: str) -> Organization:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get_by_slug(slug)
            if organization is None:
                raise NotFoundError(f"organization '{slug}' not found")
            return organization

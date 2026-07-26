from collections.abc import Callable

from app.domain.shared.exceptions import NotFoundError
from app.domain.shared.types import slugify
from app.domain.users.exceptions import DuplicateRoleNameError
from app.domain.users.models import Role, User
from app.domain.users.permissions import can_edit_step
from app.infrastructure.db.unit_of_work import UnitOfWork


class RoleService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_role(
        self,
        organization_id: int,
        name: str,
        description: str | None = None,
        agent_id: int | None = None,
    ) -> Role:
        async with self._uow_factory() as uow:
            existing = await uow.roles.get_by_slug(organization_id, slugify(name))
            if existing is not None:
                raise DuplicateRoleNameError(name)
            role = Role.create(organization_id, name, description, agent_id)
            await uow.roles.add(role)
            await uow.commit()
            return role

    async def get(self, role_id: int) -> Role:
        async with self._uow_factory() as uow:
            role = await uow.roles.get(role_id)
            if role is None:
                raise NotFoundError(f"role {role_id} not found")
            return role

    async def list_roles(self, organization_id: int) -> list[Role]:
        async with self._uow_factory() as uow:
            return await uow.roles.list_for_organization(organization_id)

    async def rename_role(self, role_id: int, new_name: str) -> Role:
        async with self._uow_factory() as uow:
            role = await uow.roles.get(role_id)
            if role is None:
                raise NotFoundError(f"role {role_id} not found")
            role.rename(new_name)
            await uow.commit()
            return role

    async def set_agent(self, role_id: int, agent_id: int | None) -> Role:
        async with self._uow_factory() as uow:
            role = await uow.roles.get(role_id)
            if role is None:
                raise NotFoundError(f"role {role_id} not found")
            role.set_agent(agent_id)
            await uow.commit()
            return role

    async def list_for_agent(self, agent_id: int) -> list[Role]:
        async with self._uow_factory() as uow:
            return await uow.roles.list_for_agent(agent_id)

    async def can_edit_step(self, user: User, agent_id: int) -> bool:
        roles_linked_to_agent = await self.list_for_agent(agent_id)
        return can_edit_step(user.role_id, roles_linked_to_agent)

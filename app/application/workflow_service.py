from collections.abc import Callable

from app.domain.shared.exceptions import NotFoundError
from app.domain.workflow.models import WorkflowDefinition
from app.domain.workflow.validation import find_validation_issues
from app.infrastructure.db.unit_of_work import UnitOfWork


class WorkflowService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_definition(
        self, organization_id: int, name: str, description: str | None = None
    ) -> WorkflowDefinition:
        async with self._uow_factory() as uow:
            definition = WorkflowDefinition.create(organization_id, name, description)
            await uow.workflow_definitions.add(definition)
            await uow.commit()
            return definition

    async def get(self, definition_id: int) -> WorkflowDefinition:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {definition_id} not found")
            return definition

    async def list_for_organization(self, organization_id: int) -> list[WorkflowDefinition]:
        async with self._uow_factory() as uow:
            return await uow.workflow_definitions.list_for_organization(organization_id)

    async def add_step(
        self,
        definition_id: int,
        key: str,
        name: str,
        agent_id: int,
        description: str | None = None,
        is_initial: bool = False,
        is_terminal: bool = False,
    ) -> WorkflowDefinition:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {definition_id} not found")
            definition.add_step(key, name, agent_id, description, is_initial, is_terminal)
            await uow.commit()
            return definition

    async def add_transition(
        self,
        definition_id: int,
        from_key: str,
        to_key: str,
        action_name: str,
        description: str | None = None,
    ) -> WorkflowDefinition:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {definition_id} not found")
            definition.add_transition(from_key, to_key, action_name, description)
            await uow.commit()
            return definition

    async def activate(self, definition_id: int) -> WorkflowDefinition:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {definition_id} not found")
            definition.activate()
            await uow.commit()
            return definition

    async def get_validation_issues(self, definition_id: int) -> list[str]:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {definition_id} not found")
            return find_validation_issues(definition)

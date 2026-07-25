from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workflow.models import WorkflowDefinition


class SqlAlchemyWorkflowDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, definition: WorkflowDefinition) -> None:
        self._session.add(definition)
        await self._session.flush()
        # Populate the collections while the session is still open: `flush()`
        # only inserts the row, it doesn't run selectin's batch load, so
        # accessing .steps/.transitions after the session closes (e.g. when
        # a router serializes the object we return) would otherwise raise
        # DetachedInstanceError.
        await self._session.refresh(definition, attribute_names=["steps", "transitions"])

    async def get(self, definition_id: int) -> WorkflowDefinition | None:
        return await self._session.get(WorkflowDefinition, definition_id)

    async def get_by_slug(self, organization_id: int, slug: str) -> WorkflowDefinition | None:
        result = await self._session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.organization_id == organization_id,
                WorkflowDefinition.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organization(self, organization_id: int) -> list[WorkflowDefinition]:
        result = await self._session.execute(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.organization_id == organization_id)
            .order_by(WorkflowDefinition.name)
        )
        return list(result.scalars().all())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.workflow_instances.models import WorkflowInstance


class SqlAlchemyWorkflowInstanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, instance: WorkflowInstance) -> None:
        self._session.add(instance)
        await self._session.flush()
        # See SqlAlchemyWorkflowDefinitionRepository.add for why this is needed.
        await self._session.refresh(instance, attribute_names=["history"])

    async def get(self, instance_id: int) -> WorkflowInstance | None:
        return await self._session.get(WorkflowInstance, instance_id)

    async def get_for_contract(self, contract_id: int) -> WorkflowInstance | None:
        result = await self._session.execute(
            select(WorkflowInstance)
            .where(WorkflowInstance.contract_id == contract_id)
            .order_by(WorkflowInstance.started_at.desc())
        )
        return result.scalars().first()

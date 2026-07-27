from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.models import Contract


class SqlAlchemyContractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, contract: Contract) -> None:
        self._session.add(contract)
        await self._session.flush()
        # See SqlAlchemyWorkflowDefinitionRepository.add for why this is needed.
        await self._session.refresh(contract, attribute_names=["documents"])

    async def get(self, contract_id: int) -> Contract | None:
        return await self._session.get(Contract, contract_id)

    async def list_for_organization(self, organization_id: int) -> list[Contract]:
        result = await self._session.execute(
            select(Contract)
            .where(Contract.organization_id == organization_id)
            .order_by(Contract.updated_at.desc())
        )
        return list(result.scalars().all())

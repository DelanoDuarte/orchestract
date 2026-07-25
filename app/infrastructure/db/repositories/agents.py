from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.agents.models import Agent


class SqlAlchemyAgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, agent: Agent) -> None:
        self._session.add(agent)
        await self._session.flush()

    async def get(self, agent_id: int) -> Agent | None:
        return await self._session.get(Agent, agent_id)

    async def list_for_organization(self, organization_id: int) -> list[Agent]:
        result = await self._session.execute(
            select(Agent).where(Agent.organization_id == organization_id).order_by(Agent.name)
        )
        return list(result.scalars().all())

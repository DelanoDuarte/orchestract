from collections.abc import Callable

from app.domain.agents.models import Agent
from app.domain.shared.exceptions import NotFoundError
from app.infrastructure.db.unit_of_work import UnitOfWork


class AgentService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_agent(self, organization_id: int, name: str, description: str | None = None) -> Agent:
        async with self._uow_factory() as uow:
            agent = Agent.create(organization_id, name, description)
            await uow.agents.add(agent)
            await uow.commit()
            return agent

    async def list_agents(self, organization_id: int) -> list[Agent]:
        async with self._uow_factory() as uow:
            return await uow.agents.list_for_organization(organization_id)

    async def get(self, agent_id: int) -> Agent:
        async with self._uow_factory() as uow:
            agent = await uow.agents.get(agent_id)
            if agent is None:
                raise NotFoundError(f"agent {agent_id} not found")
            return agent

    async def rename_agent(self, agent_id: int, new_name: str) -> Agent:
        async with self._uow_factory() as uow:
            agent = await uow.agents.get(agent_id)
            if agent is None:
                raise NotFoundError(f"agent {agent_id} not found")
            agent.rename(new_name)
            await uow.commit()
            return agent

    async def update(self, agent_id: int, name: str, description: str | None) -> Agent:
        async with self._uow_factory() as uow:
            agent = await uow.agents.get(agent_id)
            if agent is None:
                raise NotFoundError(f"agent {agent_id} not found")
            agent.rename(name)
            agent.set_description(description)
            await uow.commit()
            return agent

    async def set_active(self, agent_id: int, active: bool) -> Agent:
        async with self._uow_factory() as uow:
            agent = await uow.agents.get(agent_id)
            if agent is None:
                raise NotFoundError(f"agent {agent_id} not found")
            agent.activate() if active else agent.deactivate()
            await uow.commit()
            return agent

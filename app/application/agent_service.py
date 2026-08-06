from collections.abc import Callable

from app.domain.agents.models import Agent
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.exceptions import PlanLimitExceededError
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.infrastructure.db.unit_of_work import UnitOfWork


class AgentService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_agent(self, organization_id: int, name: str, description: str | None = None) -> Agent:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            limits = PLAN_LIMITS[Plan(organization.plan)]
            if limits.max_agents is not None:
                existing = await uow.agents.list_for_organization(organization_id)
                if len(existing) >= limits.max_agents:
                    raise PlanLimitExceededError(
                        f"the {limits.display_name} plan is limited to {limits.max_agents} agents -- "
                        "upgrade to add more"
                    )
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

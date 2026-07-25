from typing import Protocol

from app.domain.agents.models import Agent


class AgentRepository(Protocol):
    async def add(self, agent: Agent) -> None: ...

    async def get(self, agent_id: int) -> Agent | None: ...

    async def list_for_organization(self, organization_id: int) -> list[Agent]: ...

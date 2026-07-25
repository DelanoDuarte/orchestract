from fastapi import APIRouter, Depends

from app.api.deps import get_agent_service, get_current_organization_from_header
from app.api.schemas import AgentCreate, AgentOut, AgentRename, AgentSetActive
from app.application.agent_service import AgentService
from app.domain.tenancy.models import Organization

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentCreate,
    organization: Organization = Depends(get_current_organization_from_header),
    service: AgentService = Depends(get_agent_service),
):
    return await service.create_agent(organization.id, payload.name, payload.description)


@router.get("", response_model=list[AgentOut])
async def list_agents(
    organization: Organization = Depends(get_current_organization_from_header),
    service: AgentService = Depends(get_agent_service),
):
    return await service.list_agents(organization.id)


@router.patch("/{agent_id}", response_model=AgentOut)
async def rename_agent(
    agent_id: int, payload: AgentRename, service: AgentService = Depends(get_agent_service)
):
    return await service.rename_agent(agent_id, payload.name)


@router.patch("/{agent_id}/active", response_model=AgentOut)
async def set_agent_active(
    agent_id: int, payload: AgentSetActive, service: AgentService = Depends(get_agent_service)
):
    return await service.set_active(agent_id, payload.active)

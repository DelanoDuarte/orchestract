from fastapi import APIRouter, Depends

from app.api.deps import get_current_organization_from_header, get_workflow_service
from app.api.schemas import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowStepCreate,
    WorkflowTransitionCreate,
)
from app.application.workflow_service import WorkflowService
from app.domain.tenancy.models import Organization

router = APIRouter(prefix="/workflow-definitions", tags=["workflows"])


@router.post("", response_model=WorkflowDefinitionOut, status_code=201)
async def create_definition(
    payload: WorkflowDefinitionCreate,
    organization: Organization = Depends(get_current_organization_from_header),
    service: WorkflowService = Depends(get_workflow_service),
):
    return await service.create_definition(organization.id, payload.name, payload.description)


@router.get("", response_model=list[WorkflowDefinitionOut])
async def list_definitions(
    organization: Organization = Depends(get_current_organization_from_header),
    service: WorkflowService = Depends(get_workflow_service),
):
    return await service.list_for_organization(organization.id)


@router.get("/{definition_id}", response_model=WorkflowDefinitionOut)
async def get_definition(definition_id: int, service: WorkflowService = Depends(get_workflow_service)):
    return await service.get(definition_id)


@router.post("/{definition_id}/steps", response_model=WorkflowDefinitionOut, status_code=201)
async def add_step(
    definition_id: int, payload: WorkflowStepCreate, service: WorkflowService = Depends(get_workflow_service)
):
    return await service.add_step(
        definition_id,
        payload.key,
        payload.name,
        payload.agent_id,
        payload.description,
        payload.is_initial,
        payload.is_terminal,
    )


@router.post("/{definition_id}/transitions", response_model=WorkflowDefinitionOut, status_code=201)
async def add_transition(
    definition_id: int,
    payload: WorkflowTransitionCreate,
    service: WorkflowService = Depends(get_workflow_service),
):
    return await service.add_transition(
        definition_id, payload.from_key, payload.to_key, payload.action_name, payload.description
    )


@router.post("/{definition_id}/activate", response_model=WorkflowDefinitionOut)
async def activate_definition(definition_id: int, service: WorkflowService = Depends(get_workflow_service)):
    return await service.activate(definition_id)

from fastapi import APIRouter, Depends

from app.api.deps import get_contract_service, get_current_organization_from_header
from app.api.schemas import (
    ContractCreate,
    ContractOut,
    DocumentCreate,
    DocumentOut,
    TransitionExecute,
    WorkflowInstanceOut,
    WorkflowTransitionOut,
)
from app.application.contract_service import ContractService
from app.domain.tenancy.models import Organization

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.post("", response_model=ContractOut, status_code=201)
async def create_contract(
    payload: ContractCreate,
    organization: Organization = Depends(get_current_organization_from_header),
    service: ContractService = Depends(get_contract_service),
):
    return await service.create_contract(
        organization.id,
        payload.title,
        payload.contract_type,
        payload.workflow_definition_id,
        payload.actor,
        payload.description,
    )


@router.get("", response_model=list[ContractOut])
async def list_contracts(
    organization: Organization = Depends(get_current_organization_from_header),
    service: ContractService = Depends(get_contract_service),
):
    return await service.list_for_organization(organization.id)


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(contract_id: int, service: ContractService = Depends(get_contract_service)):
    return await service.get(contract_id)


@router.get("/{contract_id}/instance", response_model=WorkflowInstanceOut)
async def get_instance(contract_id: int, service: ContractService = Depends(get_contract_service)):
    return await service.get_instance(contract_id)


@router.get("/{contract_id}/actions", response_model=list[WorkflowTransitionOut])
async def get_available_actions(contract_id: int, service: ContractService = Depends(get_contract_service)):
    return await service.available_actions(contract_id)


@router.post("/{contract_id}/transitions", response_model=WorkflowInstanceOut)
async def execute_transition(
    contract_id: int, payload: TransitionExecute, service: ContractService = Depends(get_contract_service)
):
    return await service.transition_contract(contract_id, payload.action_name, payload.actor, payload.comment)


@router.post("/{contract_id}/documents", response_model=DocumentOut, status_code=201)
async def add_document(
    contract_id: int, payload: DocumentCreate, service: ContractService = Depends(get_contract_service)
):
    return await service.add_document(contract_id, payload.name)

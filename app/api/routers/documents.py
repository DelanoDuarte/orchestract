from fastapi import APIRouter, Depends

from app.api.deps import get_current_organization_from_header, get_document_service
from app.api.schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentVersionCreate,
    DocumentVersionOut,
    TransitionExecute,
    WorkflowInstanceOut,
    WorkflowTransitionOut,
)
from app.application.document_service import DocumentService
from app.domain.tenancy.models import Organization

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=201)
async def create_document(
    payload: DocumentCreate,
    organization: Organization = Depends(get_current_organization_from_header),
    service: DocumentService = Depends(get_document_service),
):
    return await service.create_document(
        organization.id,
        payload.title,
        payload.document_type,
        payload.workflow_definition_id,
        payload.actor,
        payload.description,
    )


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    organization: Organization = Depends(get_current_organization_from_header),
    service: DocumentService = Depends(get_document_service),
):
    return await service.list_for_organization(organization.id)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.get(document_id)


@router.get("/{document_id}/instance", response_model=WorkflowInstanceOut)
async def get_instance(document_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.get_instance(document_id)


@router.get("/{document_id}/actions", response_model=list[WorkflowTransitionOut])
async def get_available_actions(document_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.available_actions(document_id)


@router.post("/{document_id}/transitions", response_model=WorkflowInstanceOut)
async def execute_transition(
    document_id: int, payload: TransitionExecute, service: DocumentService = Depends(get_document_service)
):
    return await service.transition_document(document_id, payload.action_name, payload.actor, payload.comment)


@router.post("/{document_id}/versions", response_model=DocumentVersionOut, status_code=201)
async def add_version(
    document_id: int, payload: DocumentVersionCreate, service: DocumentService = Depends(get_document_service)
):
    return await service.add_version(document_id, payload.content_ref, payload.uploaded_by, payload.notes)

from fastapi import Header

from app.application.agent_service import AgentService
from app.application.document_service import DocumentService
from app.application.organization_service import OrganizationService
from app.application.workflow_service import WorkflowService
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.models import Organization
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.unit_of_work import UnitOfWork


def uow_factory() -> UnitOfWork:
    return UnitOfWork(async_session_factory)


organization_service = OrganizationService(uow_factory)
agent_service = AgentService(uow_factory)
workflow_service = WorkflowService(uow_factory)
document_service = DocumentService(uow_factory)


def get_organization_service() -> OrganizationService:
    return organization_service


def get_agent_service() -> AgentService:
    return agent_service


def get_workflow_service() -> WorkflowService:
    return workflow_service


def get_document_service() -> DocumentService:
    return document_service


async def get_current_organization_from_header(
    x_organization_id: int = Header(..., description="Tenant organization id"),
) -> Organization:
    async with uow_factory() as uow:
        organization = await uow.organizations.get(x_organization_id)
        if organization is None:
            raise NotFoundError(f"organization {x_organization_id} not found")
        return organization


async def get_current_organization_from_path(org_slug: str) -> Organization:
    return await organization_service.get_by_slug(org_slug)

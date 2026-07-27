from fastapi import Depends, Header, Request

from app.application.agent_service import AgentService
from app.application.ai_service import AIService
from app.application.billing_service import BillingService
from app.application.contract_service import ContractService
from app.application.document_service import DocumentService
from app.application.organization_service import OrganizationService
from app.application.registration_service import RegistrationService
from app.application.role_service import RoleService
from app.application.storage_service import StorageService
from app.application.user_service import UserService
from app.application.workflow_service import WorkflowService
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.models import Organization
from app.domain.users.models import User
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.unit_of_work import UnitOfWork

SESSION_COOKIE_NAME = "session_token"


class NotAuthenticatedError(Exception):
    """Raised when a web request has no valid session. Maps (via a
    dedicated exception handler in main.py) to a redirect to /login,
    rather than the JSON error body other DomainErrors get."""

    def __init__(self, next_path: str = "/") -> None:
        self.next_path = next_path


def uow_factory() -> UnitOfWork:
    return UnitOfWork(async_session_factory)


organization_service = OrganizationService(uow_factory)
agent_service = AgentService(uow_factory)
workflow_service = WorkflowService(uow_factory)
storage_service = StorageService(uow_factory)
document_service = DocumentService(uow_factory, storage_service)
contract_service = ContractService(uow_factory)
role_service = RoleService(uow_factory)
user_service = UserService(uow_factory)
registration_service = RegistrationService(uow_factory)
billing_service = BillingService(uow_factory)
ai_service = AIService(contract_service, document_service, role_service, workflow_service)


def get_organization_service() -> OrganizationService:
    return organization_service


def get_agent_service() -> AgentService:
    return agent_service


def get_workflow_service() -> WorkflowService:
    return workflow_service


def get_document_service() -> DocumentService:
    return document_service


def get_contract_service() -> ContractService:
    return contract_service


def get_ai_service() -> AIService:
    return ai_service


def get_storage_service() -> StorageService:
    return storage_service


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


async def enforce_login_and_membership(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
) -> None:
    """Router-level dependency for every org-scoped web route: requires a
    valid session belonging to a user of *this* organization, and stashes
    the user on `request.state.current_user` so templates/routes can read
    it without every route re-declaring it as a parameter."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await user_service.get_user_by_session_token(token) if token else None
    if user is None:
        raise NotAuthenticatedError(next_path=str(request.url.path))
    if user.organization_id != organization.id:
        raise NotAuthenticatedError(next_path=f"/{organization.slug}/")
    request.state.current_user = user
    request.state.current_role = await role_service.get(user.role_id)


def current_user_dep(request: Request) -> User:
    """For the handful of routes that need the logged-in User object in
    Python (permission checks, auto-filling 'actor'). Only valid on routes
    behind `enforce_login_and_membership`."""
    return request.state.current_user


def current_user_for_template(request: Request) -> User | None:
    """Jinja global so base.html can show 'signed in as ...' without every
    route passing it through the template context explicitly."""
    return getattr(request.state, "current_user", None)


def current_role_for_template(request: Request):
    return getattr(request.state, "current_role", None)

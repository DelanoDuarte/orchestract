from fastapi import Depends, Header, Request

from app.application.agent_service import AgentService
from app.application.ai_service import AIService
from app.application.billing_service import BillingService
from app.application.compliance_service import ComplianceService
from app.application.contract_service import ContractService
from app.application.document_service import DocumentService
from app.application.organization_service import OrganizationService
from app.application.registration_service import RegistrationService
from app.application.role_service import RoleService
from app.application.social_auth_service import SocialAuthService
from app.application.storage_service import StorageService
from app.application.user_service import UserService
from app.application.workflow_service import WorkflowService
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.models import Organization
from app.domain.users.models import User
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.unit_of_work import UnitOfWork
from app.infrastructure.i18n import (
    DEFAULT_LOCALE,
    LOCALE_COOKIE_NAME,
    SUPPORTED_LOCALES,
    negotiate_from_header,
    set_current_locale,
)

SESSION_COOKIE_NAME = "session_token"


class NotAuthenticatedError(Exception):
    """Raised when a web request has no valid session. Maps (via a
    dedicated exception handler in main.py) to a redirect to /login,
    rather than the JSON error body other DomainErrors get."""

    def __init__(self, next_path: str = "/") -> None:
        self.next_path = next_path


class TermsNotAcceptedError(Exception):
    """Raised when a logged-in user has not accepted the current Terms &
    Conditions version. Maps (via a handler in main.py) to a redirect to the
    consent screen, so a user can't reach any organization data until they
    accept -- the compliance gate for storing their documents in the cloud."""


def _negotiate_and_set_locale(request: Request, user: User | None = None) -> str:
    """Resolve the active UI language for this request and pin it for the
    render (via the i18n ContextVar). Priority: the logged-in user's saved
    preference, then the switcher cookie, then the browser's Accept-Language,
    then English. Also stashes it on `request.state.locale` for templates."""
    if user is not None and user.locale in SUPPORTED_LOCALES:
        chosen: str | None = user.locale
    else:
        cookie = request.cookies.get(LOCALE_COOKIE_NAME)
        if cookie in SUPPORTED_LOCALES:
            chosen = cookie
        else:
            chosen = negotiate_from_header(request.headers.get("accept-language", "")) or DEFAULT_LOCALE
    resolved = set_current_locale(chosen)
    request.state.locale = resolved
    return resolved


async def install_request_locale(request: Request) -> None:
    """Router-level dependency for public (unauthenticated) routes: negotiates
    locale from cookie/browser only. Org-scoped routes resolve it inside
    `enforce_login_and_membership` instead, where the user (and their saved
    preference) is known.

    Must be async: a sync dependency runs in a worker thread, and the i18n
    ContextVar we set there wouldn't propagate to the endpoint's task where the
    template renders."""
    _negotiate_and_set_locale(request, user=None)


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
social_auth_service = SocialAuthService(uow_factory)
billing_service = BillingService(uow_factory)
compliance_service = ComplianceService(uow_factory)
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
    if not await compliance_service.has_accepted_current(user.id):
        raise TermsNotAcceptedError()
    request.state.current_user = user
    request.state.current_role = await role_service.get(user.role_id)
    _negotiate_and_set_locale(request, user=user)


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

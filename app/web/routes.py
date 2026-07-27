import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import (
    SESSION_COOKIE_NAME,
    agent_service,
    ai_service,
    billing_service,
    contract_service,
    current_role_for_template,
    current_user_dep,
    current_user_for_template,
    document_service,
    enforce_login_and_membership,
    get_current_organization_from_path,
    organization_service,
    registration_service,
    role_service,
    storage_service,
    user_service,
    workflow_service,
)
from app.application.permissions import assert_can_edit_contract_step
from app.config import get_settings
from app.domain.shared.exceptions import DomainError, NotFoundError
from app.domain.storage.models import StorageProvider
from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.domain.users.exceptions import (
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    PermissionDeniedError,
)
from app.domain.users.models import User
from app.domain.workflow.models import WorkflowDefinition, WorkflowStatus
from app.infrastructure.ai.client import ai_enabled
from app.infrastructure.billing.stripe_client import InvalidWebhookEventError, billing_enabled, construct_webhook_event
from app.infrastructure.email.client import send_email
from app.infrastructure.email.templates import password_reset_email_html, verification_email_html
from app.web.icons import icon, step_icon_name

OAUTH_PROVIDER_LABELS = {StorageProvider.GOOGLE_DRIVE: "Google Drive", StorageProvider.ONEDRIVE: "OneDrive"}

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["icon"] = icon
templates.env.globals["step_icon"] = step_icon_name
templates.env.globals["current_user"] = current_user_for_template
templates.env.globals["current_role"] = current_role_for_template

root_router = APIRouter()
org_router = APIRouter(prefix="/{org_slug}", dependencies=[Depends(enforce_login_and_membership)])


async def _agent_names(organization_id: int) -> dict[int, str]:
    agents = await agent_service.list_agents(organization_id)
    return {agent.id: agent.name for agent in agents}


def _step_and_agent(definition: WorkflowDefinition, step_key: str, agent_names: dict[int, str]) -> tuple[str, str]:
    step = definition.get_step(step_key)
    return step.name, agent_names.get(step.agent_id, f"agent #{step.agent_id}")


async def _contract_rows_with_step_info(organization_id: int, contracts: list) -> list[dict]:
    """Enriches raw Contracts with their live workflow instance/definition
    so a template can render the current step and lifecycle pipeline
    (used by both the Dashboard and Contracts list "Preview" dialogs)."""
    agent_names = await _agent_names(organization_id)
    definitions_cache: dict[int, WorkflowDefinition] = {}
    rows = []
    for contract in contracts:
        instance = await contract_service.get_instance(contract.id)
        definition = definitions_cache.get(instance.workflow_definition_id)
        if definition is None:
            definition = await workflow_service.get(instance.workflow_definition_id)
            definitions_cache[instance.workflow_definition_id] = definition
        step_name, agent_name = _step_and_agent(definition, instance.current_step_key, agent_names)
        rows.append(
            {
                "contract": contract,
                "instance": instance,
                "definition": definition,
                "step_name": step_name,
                "step_icon": step_icon_name(instance.current_step_key),
                "agent_name": agent_name,
                "status": instance.status.value,
            }
        )
    return rows


async def _assert_can_edit_current_step(contract_id: int, current_user: User) -> None:
    """Defense in depth: the contract_detail template already hides the
    edit forms when this would fail, but every mutating route re-checks
    server-side before touching anything."""
    await assert_can_edit_contract_step(contract_service, workflow_service, role_service, contract_id, current_user)


@root_router.get("/")
async def index(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = await user_service.get_user_by_session_token(token) if token else None
    if user is not None:
        organization = await organization_service.get(user.organization_id)
        return RedirectResponse(f"/{organization.slug}/", status_code=303)
    return templates.TemplateResponse(request, "homepage.html", {"full_width": True})


@root_router.get("/pricing")
async def pricing_page(request: Request):
    return templates.TemplateResponse(
        request, "pricing.html", {"full_width": True, "plan_limits": PLAN_LIMITS}
    )


@root_router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: StorageProvider, request: Request, code: str, state: str):
    connection = await storage_service.complete_oauth_connection(state, code)
    organization = await organization_service.get(connection.organization_id)
    return RedirectResponse(f"/{organization.slug}/settings/storage", status_code=303)


@root_router.get("/login")
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next})


@root_router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    try:
        user = await user_service.authenticate(email, password)
    except InvalidCredentialsError as exc:
        return templates.TemplateResponse(
            request, "login.html", {"next": next, "error": str(exc)}, status_code=422
        )
    except EmailNotVerifiedError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": str(exc), "unverified_email": email},
            status_code=422,
        )
    session = await user_service.create_session(user.id)
    organization = await organization_service.get(user.organization_id)
    redirect_to = next if next.startswith(f"/{organization.slug}/") else f"/{organization.slug}/"
    response = RedirectResponse(redirect_to, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, session.token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14
    )
    return response


@root_router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await user_service.delete_session(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


def _session_response(redirect_to: str, session_token: str) -> RedirectResponse:
    response = RedirectResponse(redirect_to, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, session_token, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14
    )
    return response


@root_router.get("/signup")
async def signup_page(request: Request, plan: str = ""):
    return templates.TemplateResponse(request, "signup.html", {"plan": plan})


@root_router.post("/signup")
async def signup_submit(
    request: Request,
    organization_name: str = Form(...),
    user_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    plan: str = Form(""),
):
    try:
        organization, user, token = await registration_service.register(
            organization_name, user_name, email, password
        )
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "error": str(exc),
                "organization_name": organization_name,
                "user_name": user_name,
                "email": email,
                "plan": plan,
            },
            status_code=422,
        )
    link = f"{get_settings().app_base_url}/verify-email?token={token.token}"
    if plan in ("team", "business"):
        link += f"&plan={plan}"
    send_email(user.email, "Verify your email", verification_email_html(link))
    return templates.TemplateResponse(
        request,
        "auth_notice.html",
        {
            "heading": "Check your email",
            "message": f"We've sent a verification link to {user.email}. Click it to activate your account.",
            "is_error": False,
        },
    )


@root_router.get("/verify-email")
async def verify_email(request: Request, token: str, plan: str = ""):
    try:
        user = await user_service.verify_email(token)
    except InvalidOrExpiredTokenError as exc:
        return templates.TemplateResponse(
            request,
            "auth_notice.html",
            {
                "heading": "Link invalid",
                "message": str(exc),
                "is_error": True,
                "action_href": "/login",
                "action_label": "Back to sign in",
            },
            status_code=422,
        )
    session = await user_service.create_session(user.id)
    organization = await organization_service.get(user.organization_id)
    redirect_to = (
        f"/{organization.slug}/settings/billing?plan={plan}"
        if plan in ("team", "business")
        else f"/{organization.slug}/"
    )
    return _session_response(redirect_to, session.token)


@root_router.post("/verify-email/resend")
async def resend_verification(request: Request, email: str = Form(...)):
    result = await user_service.resend_verification(email)
    if result is not None:
        user, token = result
        link = f"{get_settings().app_base_url}/verify-email?token={token.token}"
        send_email(user.email, "Verify your email", verification_email_html(link))
    return templates.TemplateResponse(
        request,
        "auth_notice.html",
        {
            "heading": "Check your email",
            "message": f"If {email} has an unverified account, we've sent a new verification link.",
            "is_error": False,
        },
    )


@root_router.get("/forgot-password")
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {})


@root_router.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    result = await user_service.create_password_reset_token(email)
    if result is not None:
        user, token = result
        link = f"{get_settings().app_base_url}/reset-password?token={token.token}"
        send_email(user.email, "Reset your password", password_reset_email_html(link))
    return templates.TemplateResponse(
        request,
        "auth_notice.html",
        {
            "heading": "Check your email",
            "message": f"If {email} has an account, we've sent a password reset link.",
            "is_error": False,
        },
    )


@root_router.get("/reset-password")
async def reset_password_page(request: Request, token: str):
    return templates.TemplateResponse(request, "reset_password.html", {"token": token})


@root_router.post("/reset-password")
async def reset_password_submit(request: Request, token: str, new_password: str = Form(...)):
    try:
        user = await user_service.reset_password(token, new_password)
    except InvalidOrExpiredTokenError as exc:
        return templates.TemplateResponse(
            request,
            "auth_notice.html",
            {
                "heading": "Link invalid",
                "message": str(exc),
                "is_error": True,
                "action_href": "/forgot-password",
                "action_label": "Request a new link",
            },
            status_code=422,
        )
    session = await user_service.create_session(user.id)
    organization = await organization_service.get(user.organization_id)
    return _session_response(f"/{organization.slug}/", session.token)


@root_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = construct_webhook_event(payload, sig_header)
    except InvalidWebhookEventError:
        return JSONResponse(status_code=400, content={"detail": "invalid signature"})
    await billing_service.handle_webhook_event(event)
    return JSONResponse(status_code=200, content={"received": True})


@org_router.get("/")
async def dashboard(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    contracts = await contract_service.list_for_organization(organization.id)
    rows = await _contract_rows_with_step_info(organization.id, contracts)
    active_count = sum(1 for row in rows if row["status"] == "active")
    stats = [
        {"label": "In progress", "value": active_count},
        {"label": "Completed", "value": len(rows) - active_count},
        {"label": "Total contracts", "value": len(rows)},
    ]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"organization": organization, "rows": rows, "stats": stats, "active_nav": "dashboard"},
    )


async def _steps_owned_by_agent(organization_id: int) -> dict[int, int]:
    definitions = await workflow_service.list_for_organization(organization_id)
    counts: dict[int, int] = {}
    for definition in definitions:
        for step in definition.steps:
            counts[step.agent_id] = counts.get(step.agent_id, 0) + 1
    return counts


async def _roles_by_agent(organization_id: int) -> dict[int, list[str]]:
    roles = await role_service.list_roles(organization_id)
    by_agent: dict[int, list[str]] = {}
    for role in roles:
        if role.agent_id is not None:
            by_agent.setdefault(role.agent_id, []).append(role.name)
    return by_agent


async def _reconcile_agent_roles(organization_id: int, agent_id: int, selected_role_ids: list[int]) -> None:
    """Applies the "Linked roles" checklist from the agent create/edit form:
    checked roles get linked to this agent (taking them off whatever agent
    they were on, if any), and roles that were linked to this agent but got
    unchecked are unlinked. Roles linked to a *different* agent that stay
    unchecked are left alone."""
    selected = set(selected_role_ids)
    for role in await role_service.list_roles(organization_id):
        if role.id in selected and role.agent_id != agent_id:
            await role_service.set_agent(role.id, agent_id)
        elif role.id not in selected and role.agent_id == agent_id:
            await role_service.set_agent(role.id, None)


@org_router.get("/agents")
async def agents_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    agents = await agent_service.list_agents(organization.id)
    steps_owned = await _steps_owned_by_agent(organization.id)
    roles_by_agent = await _roles_by_agent(organization.id)
    return templates.TemplateResponse(
        request,
        "agents.html",
        {
            "organization": organization,
            "agents": agents,
            "steps_owned": steps_owned,
            "roles_by_agent": roles_by_agent,
            "active_nav": "agents",
        },
    )


@org_router.get("/agents/new")
async def new_agent_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    roles = await role_service.list_roles(organization.id)
    agent_names = await _agent_names(organization.id)
    return templates.TemplateResponse(
        request,
        "agent_new.html",
        {"organization": organization, "roles": roles, "agent_names": agent_names, "active_nav": "agents"},
    )


@org_router.post("/agents")
async def create_agent(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    role_ids: list[int] = Form([]),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        agent = await agent_service.create_agent(organization.id, name, description or None)
        await _reconcile_agent_roles(organization.id, agent.id, role_ids)
    except DomainError as exc:
        roles = await role_service.list_roles(organization.id)
        agent_names = await _agent_names(organization.id)
        return templates.TemplateResponse(
            request,
            "agent_new.html",
            {
                "organization": organization,
                "roles": roles,
                "agent_names": agent_names,
                "active_nav": "agents",
                "error": str(exc),
            },
            status_code=422,
        )
    return await agents_page(request, organization)


@org_router.get("/agents/{agent_id}/edit")
async def edit_agent_page(
    agent_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    agent = await agent_service.get(agent_id)
    roles = await role_service.list_roles(organization.id)
    agent_names = await _agent_names(organization.id)
    return templates.TemplateResponse(
        request,
        "agent_edit.html",
        {
            "organization": organization,
            "agent": agent,
            "roles": roles,
            "agent_names": agent_names,
            "active_nav": "agents",
        },
    )


@org_router.post("/agents/{agent_id}/edit")
async def update_agent(
    agent_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    role_ids: list[int] = Form([]),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        agent = await agent_service.update(agent_id, name, description or None)
        await _reconcile_agent_roles(organization.id, agent_id, role_ids)
    except DomainError as exc:
        agent = await agent_service.get(agent_id)
        roles = await role_service.list_roles(organization.id)
        agent_names = await _agent_names(organization.id)
        return templates.TemplateResponse(
            request,
            "agent_edit.html",
            {
                "organization": organization,
                "agent": agent,
                "roles": roles,
                "agent_names": agent_names,
                "active_nav": "agents",
                "error": str(exc),
            },
            status_code=422,
        )
    return await agents_page(request, organization)


@org_router.post("/agents/{agent_id}/toggle")
async def toggle_agent(
    agent_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    agent = await agent_service.get(agent_id)
    await agent_service.set_active(agent_id, not agent.is_active)
    return await agents_page(request, organization)


@org_router.get("/roles")
async def roles_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    roles = await role_service.list_roles(organization.id)
    agent_names = await _agent_names(organization.id)
    return templates.TemplateResponse(
        request,
        "roles.html",
        {"organization": organization, "roles": roles, "agent_names": agent_names, "active_nav": "roles"},
    )


@org_router.get("/roles/new")
async def new_role_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    agents = await agent_service.list_agents(organization.id)
    return templates.TemplateResponse(
        request,
        "role_new.html",
        {"organization": organization, "agents": agents, "active_nav": "roles"},
    )


@org_router.post("/roles")
async def create_role(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    agent_id: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await role_service.create_role(
            organization.id, name, description or None, int(agent_id) if agent_id else None
        )
    except DomainError as exc:
        agents = await agent_service.list_agents(organization.id)
        return templates.TemplateResponse(
            request,
            "role_new.html",
            {"organization": organization, "agents": agents, "active_nav": "roles", "error": str(exc)},
            status_code=422,
        )
    return await roles_page(request, organization)


@org_router.get("/users")
async def users_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    users = await user_service.list_users(organization.id)
    roles = await role_service.list_roles(organization.id)
    role_names = {role.id: role.name for role in roles}
    return templates.TemplateResponse(
        request,
        "users.html",
        {"organization": organization, "users": users, "role_names": role_names, "active_nav": "users"},
    )


@org_router.get("/users/new")
async def new_user_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    roles = await role_service.list_roles(organization.id)
    return templates.TemplateResponse(
        request,
        "user_new.html",
        {"organization": organization, "roles": roles, "active_nav": "users"},
    )


@org_router.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role_id: int = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await user_service.create_user(organization.id, name, email, password, role_id)
    except DomainError as exc:
        roles = await role_service.list_roles(organization.id)
        return templates.TemplateResponse(
            request,
            "user_new.html",
            {"organization": organization, "roles": roles, "active_nav": "users", "error": str(exc)},
            status_code=422,
        )
    return await users_page(request, organization)


@org_router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    user = await user_service.get(user_id)
    await user_service.set_active(user_id, not user.is_active)
    return await users_page(request, organization)


async def _account_context(organization: Organization, current_user: User) -> dict:
    role = await role_service.get(current_user.role_id) if current_user.role_id else None
    return {
        "organization": organization,
        "current_user_obj": current_user,
        "current_role_obj": role,
    }


@org_router.get("/account")
async def account_page(
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    context = await _account_context(organization, current_user)
    return templates.TemplateResponse(request, "account.html", context)


@org_router.post("/account")
async def update_account(
    request: Request,
    name: str = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await user_service.rename(current_user.id, name)
    except DomainError as exc:
        context = await _account_context(organization, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "account.html", context, status_code=422)
    context = await _account_context(organization, await user_service.get(current_user.id))
    context["success"] = "Name updated."
    return templates.TemplateResponse(request, "account.html", context)


@org_router.post("/account/password")
async def update_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await user_service.change_password(current_user.id, current_password, new_password)
    except DomainError as exc:
        context = await _account_context(organization, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "account.html", context, status_code=422)
    context = await _account_context(organization, current_user)
    context["success"] = "Password updated."
    return templates.TemplateResponse(request, "account.html", context)


async def _storage_settings_context(organization: Organization) -> dict:
    connections = await storage_service.list_connections(organization.id)
    return {
        "organization": organization,
        "connections": connections,
        "oauth_provider_labels": OAUTH_PROVIDER_LABELS,
        "google_configured": bool(get_settings().google_oauth_client_id),
        "microsoft_configured": bool(get_settings().microsoft_oauth_client_id),
        "active_nav": "storage",
    }


@org_router.get("/settings/storage")
async def storage_settings_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    context = await _storage_settings_context(organization)
    return templates.TemplateResponse(request, "storage_settings.html", context)


@org_router.post("/settings/storage/connect")
async def connect_bucket(
    request: Request,
    provider: StorageProvider = Form(...),
    display_name: str = Form(...),
    bucket: str = Form(""),
    region: str = Form(""),
    endpoint_url: str = Form(""),
    access_key: str = Form(""),
    secret_key: str = Form(""),
    service_account_json: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    config: dict = {}
    credentials: dict = {}
    if provider == StorageProvider.LOCAL:
        config = {"prefix": organization.slug}
    elif provider == StorageProvider.S3:
        config = {"bucket": bucket, "region": region or None}
        credentials = {"access_key": access_key, "secret_key": secret_key}
    elif provider == StorageProvider.MINIO:
        config = {"bucket": bucket, "endpoint_url": endpoint_url}
        credentials = {"access_key": access_key, "secret_key": secret_key}
    elif provider == StorageProvider.GCS:
        config = {"bucket": bucket}
        try:
            credentials = {"service_account_info": json.loads(service_account_json)}
        except ValueError:
            context = await _storage_settings_context(organization)
            context["error"] = "Service account JSON is not valid JSON."
            return templates.TemplateResponse(request, "storage_settings.html", context, status_code=422)

    try:
        await storage_service.connect_bucket(organization.id, provider, display_name, config, credentials)
    except DomainError as exc:
        context = await _storage_settings_context(organization)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "storage_settings.html", context, status_code=422)
    return await storage_settings_page(request, organization)


@org_router.get("/settings/storage/connect/{provider}/start")
async def start_oauth_connection(
    provider: StorageProvider, organization: Organization = Depends(get_current_organization_from_path)
):
    url = await storage_service.start_oauth_connection(organization.id, provider)
    return RedirectResponse(url, status_code=303)


@org_router.post("/settings/storage/{connection_id}/primary")
async def set_primary_connection(
    connection_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await storage_service.set_primary(connection_id)
    except DomainError as exc:
        context = await _storage_settings_context(organization)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "storage_settings.html", context, status_code=422)
    return await storage_settings_page(request, organization)


@org_router.post("/settings/storage/{connection_id}/disconnect")
async def disconnect_connection(
    connection_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    await storage_service.disconnect(connection_id)
    return await storage_settings_page(request, organization)


async def _billing_settings_context(organization: Organization) -> dict:
    limits = PLAN_LIMITS[Plan(organization.plan)]
    user_count = len(await user_service.list_users(organization.id))
    contract_count = len(await contract_service.list_for_organization(organization.id))
    return {
        "organization": organization,
        "billing_enabled": billing_enabled(),
        "plan_limits": PLAN_LIMITS,
        "current_plan": Plan(organization.plan),
        "current_limits": limits,
        "user_count": user_count,
        "contract_count": contract_count,
        "active_nav": "billing",
    }


@org_router.get("/settings/billing")
async def billing_settings_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path), plan: str = ""
):
    context = await _billing_settings_context(organization)
    context["preselected_plan"] = plan
    return templates.TemplateResponse(request, "billing_settings.html", context)


@org_router.post("/settings/billing/checkout")
async def start_checkout(
    request: Request,
    plan: str = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    settings = get_settings()
    price_id = settings.stripe_price_team if plan == "team" else settings.stripe_price_business
    if not billing_enabled() or not price_id:
        context = await _billing_settings_context(organization)
        context["error"] = "Billing is not configured yet."
        return templates.TemplateResponse(request, "billing_settings.html", context, status_code=422)
    base_url = f"{settings.app_base_url}/{organization.slug}/settings/billing"
    checkout_url = await billing_service.start_checkout(
        organization.id,
        Plan(plan),
        price_id,
        success_url=f"{base_url}?checkout=success",
        cancel_url=f"{base_url}?checkout=cancelled",
        user_email=current_user.email,
    )
    return RedirectResponse(checkout_url, status_code=303)


@org_router.post("/settings/billing/portal")
async def start_portal(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    settings = get_settings()
    return_url = f"{settings.app_base_url}/{organization.slug}/settings/billing"
    try:
        portal_url = await billing_service.start_portal_session(organization.id, return_url)
    except NotFoundError as exc:
        context = await _billing_settings_context(organization)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "billing_settings.html", context, status_code=422)
    return RedirectResponse(portal_url, status_code=303)


@org_router.get("/workflows")
async def workflows_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    workflows = await workflow_service.list_for_organization(organization.id)
    return templates.TemplateResponse(
        request,
        "workflows_list.html",
        {"organization": organization, "workflows": workflows, "active_nav": "workflows"},
    )


@org_router.get("/workflows/new")
async def new_workflow_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    return templates.TemplateResponse(
        request,
        "workflow_new.html",
        {"organization": organization, "active_nav": "workflows"},
    )


@org_router.post("/workflows")
async def create_workflow(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await workflow_service.create_definition(organization.id, name, description or None)
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "workflow_new.html",
            {
                "organization": organization,
                "active_nav": "workflows",
                "error": str(exc),
            },
            status_code=422,
        )
    return await workflows_page(request, organization)


async def _workflow_detail_context(organization: Organization, definition_id: int) -> dict:
    workflow = await workflow_service.get(definition_id)
    agents = await agent_service.list_agents(organization.id)
    agent_names = {agent.id: agent.name for agent in agents}
    issues = await workflow_service.get_validation_issues(definition_id)
    return {
        "organization": organization,
        "workflow": workflow,
        "agents": agents,
        "agent_names": agent_names,
        "issues": issues,
        "active_nav": "workflows",
    }


@org_router.get("/workflows/{definition_id}")
async def workflow_detail(
    definition_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    context = await _workflow_detail_context(organization, definition_id)
    return templates.TemplateResponse(request, "workflow_detail.html", context)


@org_router.post("/workflows/{definition_id}/steps")
async def add_step(
    definition_id: int,
    request: Request,
    key: str = Form(...),
    name: str = Form(...),
    agent_id: int = Form(...),
    description: str = Form(""),
    is_initial: bool = Form(False),
    is_terminal: bool = Form(False),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await workflow_service.add_step(
            definition_id, key, name, agent_id, description or None, is_initial, is_terminal
        )
    except DomainError as exc:
        context = await _workflow_detail_context(organization, definition_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "workflow_detail.html", context, status_code=422)
    return await workflow_detail(definition_id, request, organization)


@org_router.post("/workflows/{definition_id}/transitions")
async def add_transition(
    definition_id: int,
    request: Request,
    from_key: str = Form(...),
    to_key: str = Form(...),
    action_name: str = Form(...),
    description: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await workflow_service.add_transition(
            definition_id, from_key, to_key, action_name, description or None
        )
    except DomainError as exc:
        context = await _workflow_detail_context(organization, definition_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "workflow_detail.html", context, status_code=422)
    return await workflow_detail(definition_id, request, organization)


@org_router.post("/workflows/{definition_id}/activate")
async def activate_workflow(
    definition_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await workflow_service.activate(definition_id)
    except DomainError as exc:
        context = await _workflow_detail_context(organization, definition_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "workflow_detail.html", context, status_code=422)
    return await workflow_detail(definition_id, request, organization)


@org_router.get("/contracts")
async def contracts_page(
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    q: str = "",
    contract_type: str = "",
):
    all_contracts = await contract_service.list_for_organization(organization.id)
    contract_types = sorted({contract.contract_type for contract in all_contracts})
    contracts = all_contracts
    if q:
        needle = q.lower()
        contracts = [c for c in contracts if needle in c.title.lower()]
    if contract_type:
        contracts = [c for c in contracts if c.contract_type == contract_type]
    rows = await _contract_rows_with_step_info(organization.id, contracts)
    return templates.TemplateResponse(
        request,
        "contracts_list.html",
        {
            "organization": organization,
            "rows": rows,
            "contract_types": contract_types,
            "search_query": q,
            "active_type": contract_type,
            "active_nav": "contracts",
        },
    )


@org_router.get("/contracts/new")
async def new_contract_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    workflows = await workflow_service.list_for_organization(organization.id)
    active_workflows = [wf for wf in workflows if wf.status == WorkflowStatus.ACTIVE]
    return templates.TemplateResponse(
        request,
        "contract_new.html",
        {"organization": organization, "workflows": active_workflows, "active_nav": "contracts"},
    )


@org_router.post("/contracts")
async def create_contract(
    request: Request,
    title: str = Form(...),
    contract_type: str = Form(...),
    workflow_definition_id: int = Form(...),
    description: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        contract = await contract_service.create_contract(
            organization.id, title, contract_type, workflow_definition_id, current_user.name, description or None
        )
    except DomainError as exc:
        workflows = await workflow_service.list_for_organization(organization.id)
        active_workflows = [wf for wf in workflows if wf.status == WorkflowStatus.ACTIVE]
        return templates.TemplateResponse(
            request,
            "contract_new.html",
            {
                "organization": organization,
                "workflows": active_workflows,
                "active_nav": "contracts",
                "error": str(exc),
            },
            status_code=422,
        )
    return await contract_detail(contract.id, request, organization, current_user)


async def _contract_detail_context(organization: Organization, contract_id: int, current_user: User) -> dict:
    contract = await contract_service.get(contract_id)
    instance = await contract_service.get_instance(contract_id)
    definition = await workflow_service.get(instance.workflow_definition_id)
    agent_names = await _agent_names(organization.id)
    step_name, agent_name = _step_and_agent(definition, instance.current_step_key, agent_names)
    actions = instance.available_actions(definition)
    connections = await storage_service.list_connections(organization.id)
    drive_connections = [
        c for c in connections if c.provider in OAUTH_PROVIDER_LABELS and c.status.value == "connected"
    ]
    steps_traveled = len({entry.to_step_key for entry in instance.history})
    current_step_agent_id = definition.get_step(instance.current_step_key).agent_id
    can_edit = await role_service.can_edit_step(current_user, current_step_agent_id)
    edit_roles = await role_service.list_for_agent(current_step_agent_id)
    total_versions = sum(len(document.versions) for document in contract.documents)
    return {
        "organization": organization,
        "contract": contract,
        "instance": instance,
        "definition": definition,
        "current_step_name": step_name,
        "current_agent_name": agent_name,
        "actions": actions,
        "drive_connections": drive_connections,
        "oauth_provider_labels": OAUTH_PROVIDER_LABELS,
        "steps_traveled": steps_traveled,
        "total_steps": len(definition.steps),
        "total_versions": total_versions,
        "can_edit": can_edit,
        "edit_role_names": [role.name for role in edit_roles],
        "ai_enabled": ai_enabled() and PLAN_LIMITS[Plan(organization.plan)].ai_enabled,
        "active_nav": "contracts",
    }


@org_router.get("/contracts/{contract_id}")
async def contract_detail(
    contract_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    context = await _contract_detail_context(organization, contract_id, current_user)
    return templates.TemplateResponse(request, "contract_detail.html", context)


@org_router.post("/contracts/{contract_id}/transitions")
async def execute_transition(
    contract_id: int,
    request: Request,
    action_name: str = Form(...),
    comment: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await _assert_can_edit_current_step(contract_id, current_user)
        await contract_service.transition_contract(contract_id, action_name, current_user.name, comment or None)
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.post("/contracts/{contract_id}/documents")
async def add_document_to_contract(
    contract_id: int,
    request: Request,
    name: str = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await _assert_can_edit_current_step(contract_id, current_user)
        await contract_service.add_document(contract_id, name)
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.post("/contracts/{contract_id}/documents/{document_id}/versions")
async def upload_version(
    contract_id: int,
    document_id: int,
    request: Request,
    file: UploadFile,
    notes: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await _assert_can_edit_current_step(contract_id, current_user)
        content = await file.read()
        await document_service.upload_version(
            document_id,
            content,
            file.filename or "file",
            file.content_type or "application/octet-stream",
            current_user.name,
            notes or None,
        )
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.get("/contracts/{contract_id}/documents/{document_id}/import/{connection_id}")
async def import_browser_page(
    contract_id: int,
    document_id: int,
    connection_id: int,
    request: Request,
    folder_id: str | None = None,
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await _assert_can_edit_current_step(contract_id, current_user)
    except PermissionDeniedError:
        return RedirectResponse(f"/{organization.slug}/contracts/{contract_id}", status_code=303)
    document = await document_service.get(document_id)
    connection = await storage_service.get(connection_id)
    files = await storage_service.browse_external_files(connection_id, folder_id)
    return templates.TemplateResponse(
        request,
        "document_import_browser.html",
        {
            "organization": organization,
            "contract_id": contract_id,
            "document": document,
            "connection": connection,
            "files": files,
            "active_nav": "contracts",
        },
    )


@org_router.post("/contracts/{contract_id}/documents/{document_id}/import/{connection_id}")
async def import_version(
    contract_id: int,
    document_id: int,
    connection_id: int,
    request: Request,
    external_file_id: str = Form(...),
    notes: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await _assert_can_edit_current_step(contract_id, current_user)
        await document_service.import_version_from_external(
            document_id, connection_id, external_file_id, current_user.name, notes or None
        )
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.post("/contracts/{contract_id}/summarize")
async def summarize_contract(
    contract_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await ai_service.summarize_contract(contract_id, organization)
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.post("/contracts/{contract_id}/documents/{document_id}/summarize")
async def summarize_document(
    contract_id: int,
    document_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    try:
        await ai_service.summarize_document(document_id, organization)
    except DomainError as exc:
        context = await _contract_detail_context(organization, contract_id, current_user)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return await contract_detail(contract_id, request, organization, current_user)


@org_router.post("/contracts/{contract_id}/assistant")
async def run_assistant(
    contract_id: int,
    request: Request,
    instruction: str = Form(...),
    organization: Organization = Depends(get_current_organization_from_path),
    current_user: User = Depends(current_user_dep),
):
    context = await _contract_detail_context(organization, contract_id, current_user)
    context["assistant_instruction"] = instruction
    try:
        context["assistant_result"] = await ai_service.run_assistant(
            contract_id, instruction, current_user, organization
        )
    except DomainError as exc:
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "contract_detail.html", context, status_code=422)
    return templates.TemplateResponse(request, "contract_detail.html", context)

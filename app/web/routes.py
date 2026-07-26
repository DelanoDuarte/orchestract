import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import (
    agent_service,
    document_service,
    get_current_organization_from_path,
    organization_service,
    storage_service,
    workflow_service,
)
from app.config import get_settings
from app.domain.shared.exceptions import DomainError
from app.domain.storage.models import StorageProvider
from app.domain.tenancy.models import Organization
from app.domain.workflow.models import WorkflowDefinition, WorkflowStatus
from app.web.icons import icon, step_icon_name

OAUTH_PROVIDER_LABELS = {StorageProvider.GOOGLE_DRIVE: "Google Drive", StorageProvider.ONEDRIVE: "OneDrive"}

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["icon"] = icon
templates.env.globals["step_icon"] = step_icon_name

root_router = APIRouter()
org_router = APIRouter(prefix="/{org_slug}")


async def _agent_names(organization_id: int) -> dict[int, str]:
    agents = await agent_service.list_agents(organization_id)
    return {agent.id: agent.name for agent in agents}


def _step_and_agent(definition: WorkflowDefinition, step_key: str, agent_names: dict[int, str]) -> tuple[str, str]:
    step = definition.get_step(step_key)
    return step.name, agent_names.get(step.agent_id, f"agent #{step.agent_id}")


@root_router.get("/")
async def index(request: Request):
    organizations = await organization_service.list_organizations()
    return templates.TemplateResponse(request, "index.html", {"organizations": organizations})


@root_router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: StorageProvider, request: Request, code: str, state: str):
    connection = await storage_service.complete_oauth_connection(state, code)
    organization = await organization_service.get(connection.organization_id)
    return RedirectResponse(f"/{organization.slug}/settings/storage", status_code=303)


@org_router.get("/")
async def dashboard(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    documents = await document_service.list_for_organization(organization.id)
    agent_names = await _agent_names(organization.id)
    definitions_cache: dict[int, WorkflowDefinition] = {}
    rows = []
    for document in documents:
        instance = await document_service.get_instance(document.id)
        definition = definitions_cache.get(instance.workflow_definition_id)
        if definition is None:
            definition = await workflow_service.get(instance.workflow_definition_id)
            definitions_cache[instance.workflow_definition_id] = definition
        step_name, agent_name = _step_and_agent(definition, instance.current_step_key, agent_names)
        rows.append(
            {
                "document": document,
                "step_name": step_name,
                "step_icon": step_icon_name(instance.current_step_key),
                "agent_name": agent_name,
                "status": instance.status.value,
            }
        )
    active_count = sum(1 for row in rows if row["status"] == "active")
    stats = [
        {"label": "In progress", "value": active_count},
        {"label": "Completed", "value": len(rows) - active_count},
        {"label": "Total documents", "value": len(rows)},
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


@org_router.get("/agents")
async def agents_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    agents = await agent_service.list_agents(organization.id)
    steps_owned = await _steps_owned_by_agent(organization.id)
    return templates.TemplateResponse(
        request,
        "agents.html",
        {"organization": organization, "agents": agents, "steps_owned": steps_owned, "active_nav": "agents"},
    )


@org_router.get("/agents/new")
async def new_agent_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    return templates.TemplateResponse(
        request,
        "agent_new.html",
        {"organization": organization, "active_nav": "agents"},
    )


@org_router.post("/agents")
async def create_agent(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await agent_service.create_agent(organization.id, name, description or None)
    except DomainError as exc:
        return templates.TemplateResponse(
            request,
            "agent_new.html",
            {
                "organization": organization,
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


@org_router.get("/documents")
async def documents_page(
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
    q: str = "",
    doc_type: str = "",
):
    all_documents = await document_service.list_for_organization(organization.id)
    doc_types = sorted({document.document_type for document in all_documents})
    documents = all_documents
    if q:
        needle = q.lower()
        documents = [d for d in documents if needle in d.title.lower()]
    if doc_type:
        documents = [d for d in documents if d.document_type == doc_type]
    return templates.TemplateResponse(
        request,
        "documents_list.html",
        {
            "organization": organization,
            "documents": documents,
            "doc_types": doc_types,
            "search_query": q,
            "active_type": doc_type,
            "active_nav": "documents",
        },
    )


@org_router.get("/documents/new")
async def new_document_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    workflows = await workflow_service.list_for_organization(organization.id)
    active_workflows = [wf for wf in workflows if wf.status == WorkflowStatus.ACTIVE]
    return templates.TemplateResponse(
        request,
        "document_new.html",
        {"organization": organization, "workflows": active_workflows, "active_nav": "documents"},
    )


@org_router.post("/documents")
async def create_document(
    request: Request,
    title: str = Form(...),
    document_type: str = Form(...),
    workflow_definition_id: int = Form(...),
    actor: str = Form(...),
    description: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        document = await document_service.create_document(
            organization.id, title, document_type, workflow_definition_id, actor, description or None
        )
    except DomainError as exc:
        workflows = await workflow_service.list_for_organization(organization.id)
        active_workflows = [wf for wf in workflows if wf.status == WorkflowStatus.ACTIVE]
        return templates.TemplateResponse(
            request,
            "document_new.html",
            {
                "organization": organization,
                "workflows": active_workflows,
                "active_nav": "documents",
                "error": str(exc),
            },
            status_code=422,
        )
    return await document_detail(document.id, request, organization)


async def _document_detail_context(organization: Organization, document_id: int) -> dict:
    document = await document_service.get(document_id)
    instance = await document_service.get_instance(document_id)
    definition = await workflow_service.get(instance.workflow_definition_id)
    agent_names = await _agent_names(organization.id)
    step_name, agent_name = _step_and_agent(definition, instance.current_step_key, agent_names)
    actions = instance.available_actions(definition)
    connections = await storage_service.list_connections(organization.id)
    drive_connections = [
        c for c in connections if c.provider in OAUTH_PROVIDER_LABELS and c.status.value == "connected"
    ]
    steps_traveled = len({entry.to_step_key for entry in instance.history})
    return {
        "organization": organization,
        "document": document,
        "instance": instance,
        "definition": definition,
        "current_step_name": step_name,
        "current_agent_name": agent_name,
        "actions": actions,
        "drive_connections": drive_connections,
        "oauth_provider_labels": OAUTH_PROVIDER_LABELS,
        "steps_traveled": steps_traveled,
        "total_steps": len(definition.steps),
        "active_nav": "documents",
    }


@org_router.get("/documents/{document_id}")
async def document_detail(
    document_id: int,
    request: Request,
    organization: Organization = Depends(get_current_organization_from_path),
):
    context = await _document_detail_context(organization, document_id)
    return templates.TemplateResponse(request, "document_detail.html", context)


@org_router.post("/documents/{document_id}/transitions")
async def execute_transition(
    document_id: int,
    request: Request,
    action_name: str = Form(...),
    actor: str = Form(...),
    comment: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await document_service.transition_document(document_id, action_name, actor, comment or None)
    except DomainError as exc:
        context = await _document_detail_context(organization, document_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "document_detail.html", context, status_code=422)
    return await document_detail(document_id, request, organization)


@org_router.post("/documents/{document_id}/versions")
async def upload_version(
    document_id: int,
    request: Request,
    file: UploadFile,
    uploaded_by: str = Form(...),
    notes: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        content = await file.read()
        await document_service.upload_version(
            document_id,
            content,
            file.filename or "file",
            file.content_type or "application/octet-stream",
            uploaded_by,
            notes or None,
        )
    except DomainError as exc:
        context = await _document_detail_context(organization, document_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "document_detail.html", context, status_code=422)
    return await document_detail(document_id, request, organization)


@org_router.get("/documents/{document_id}/import/{connection_id}")
async def import_browser_page(
    document_id: int,
    connection_id: int,
    request: Request,
    folder_id: str | None = None,
    organization: Organization = Depends(get_current_organization_from_path),
):
    document = await document_service.get(document_id)
    connection = await storage_service.get(connection_id)
    files = await storage_service.browse_external_files(connection_id, folder_id)
    return templates.TemplateResponse(
        request,
        "document_import_browser.html",
        {
            "organization": organization,
            "document": document,
            "connection": connection,
            "files": files,
            "active_nav": "documents",
        },
    )


@org_router.post("/documents/{document_id}/import/{connection_id}")
async def import_version(
    document_id: int,
    connection_id: int,
    request: Request,
    external_file_id: str = Form(...),
    uploaded_by: str = Form(...),
    notes: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await document_service.import_version_from_external(
            document_id, connection_id, external_file_id, uploaded_by, notes or None
        )
    except DomainError as exc:
        context = await _document_detail_context(organization, document_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "document_detail.html", context, status_code=422)
    return await document_detail(document_id, request, organization)

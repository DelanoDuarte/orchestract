from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates

from app.api.deps import (
    agent_service,
    document_service,
    get_current_organization_from_path,
    organization_service,
    workflow_service,
)
from app.domain.shared.exceptions import DomainError
from app.domain.tenancy.models import Organization
from app.domain.workflow.models import WorkflowDefinition, WorkflowStatus
from app.web.icons import icon, step_icon_name

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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"organization": organization, "rows": rows, "active_nav": "dashboard"},
    )


@org_router.get("/agents")
async def agents_page(
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    agents = await agent_service.list_agents(organization.id)
    return templates.TemplateResponse(
        request,
        "agents.html",
        {"organization": organization, "agents": agents, "active_nav": "agents"},
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
        agents = await agent_service.list_agents(organization.id)
        return templates.TemplateResponse(
            request,
            "agents.html",
            {"organization": organization, "agents": agents, "active_nav": "agents", "error": str(exc)},
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
        workflows = await workflow_service.list_for_organization(organization.id)
        return templates.TemplateResponse(
            request,
            "workflows_list.html",
            {
                "organization": organization,
                "workflows": workflows,
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
    request: Request, organization: Organization = Depends(get_current_organization_from_path)
):
    documents = await document_service.list_for_organization(organization.id)
    return templates.TemplateResponse(
        request,
        "documents_list.html",
        {"organization": organization, "documents": documents, "active_nav": "documents"},
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
    return {
        "organization": organization,
        "document": document,
        "instance": instance,
        "definition": definition,
        "current_step_name": step_name,
        "current_agent_name": agent_name,
        "actions": actions,
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
async def add_version(
    document_id: int,
    request: Request,
    content_ref: str = Form(...),
    uploaded_by: str = Form(...),
    notes: str = Form(""),
    organization: Organization = Depends(get_current_organization_from_path),
):
    try:
        await document_service.add_version(document_id, content_ref, uploaded_by, notes or None)
    except DomainError as exc:
        context = await _document_detail_context(organization, document_id)
        context["error"] = str(exc)
        return templates.TemplateResponse(request, "document_detail.html", context, status_code=422)
    return await document_detail(document_id, request, organization)

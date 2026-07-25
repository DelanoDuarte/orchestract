from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.storage.models import ConnectionStatus, StorageProvider
from app.domain.workflow.models import WorkflowStatus
from app.domain.workflow_instances.models import InstanceStatus


class OrganizationCreate(BaseModel):
    name: str


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    created_at: datetime


class AgentCreate(BaseModel):
    name: str
    description: str | None = None


class AgentRename(BaseModel):
    name: str


class AgentSetActive(BaseModel):
    active: bool


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    slug: str
    description: str | None
    is_active: bool
    created_at: datetime


class WorkflowDefinitionCreate(BaseModel):
    name: str
    description: str | None = None


class WorkflowStepCreate(BaseModel):
    key: str
    name: str
    agent_id: int
    description: str | None = None
    is_initial: bool = False
    is_terminal: bool = False


class WorkflowTransitionCreate(BaseModel):
    from_key: str
    to_key: str
    action_name: str
    description: str | None = None


class WorkflowStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    name: str
    description: str | None
    agent_id: int
    is_initial: bool
    is_terminal: bool


class WorkflowTransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_step_key: str
    to_step_key: str
    action_name: str
    description: str | None


class WorkflowDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    slug: str
    description: str | None
    status: WorkflowStatus
    steps: list[WorkflowStepOut]
    transitions: list[WorkflowTransitionOut]


class DocumentCreate(BaseModel):
    title: str
    document_type: str
    workflow_definition_id: int
    actor: str
    description: str | None = None


class DocumentVersionImport(BaseModel):
    connection_id: int
    external_file_id: str
    uploaded_by: str
    notes: str | None = None


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_no: int
    storage_key: str
    original_filename: str
    content_type: str
    size_bytes: int
    source_provider: StorageProvider | None
    source_external_id: str | None
    uploaded_by: str
    notes: str | None
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    title: str
    description: str | None
    document_type: str
    current_version_no: int
    created_at: datetime
    updated_at: datetime
    versions: list[DocumentVersionOut]


class TransitionExecute(BaseModel):
    action_name: str
    actor: str
    comment: str | None = None


class WorkflowHistoryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_step_key: str | None
    to_step_key: str
    action_name: str | None
    actor: str
    comment: str | None
    occurred_at: datetime


class WorkflowInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    workflow_definition_id: int
    current_step_key: str
    status: InstanceStatus
    started_at: datetime
    completed_at: datetime | None
    history: list[WorkflowHistoryEntryOut]


class StorageConnectionCreate(BaseModel):
    provider: StorageProvider
    display_name: str
    config: dict = {}
    credentials: dict = {}


class StorageConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    provider: StorageProvider
    status: ConnectionStatus
    is_primary: bool
    display_name: str
    config: dict
    created_at: datetime


class OAuthStartOut(BaseModel):
    authorization_url: str


class ExternalFileOut(BaseModel):
    id: str
    name: str
    mime_type: str
    size: int | None
    modified_at: datetime | None

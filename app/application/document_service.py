from collections.abc import Callable

from app.domain.documents.models import Document, DocumentVersion
from app.domain.shared.exceptions import NotFoundError
from app.domain.workflow.models import WorkflowTransition
from app.domain.workflow_instances.models import WorkflowInstance
from app.infrastructure.db.unit_of_work import UnitOfWork


class DocumentService:
    """Orchestrates the Document, WorkflowDefinition and WorkflowInstance
    aggregates for use cases that span more than one of them. This kind of
    cross-aggregate coordination belongs in the application layer, not in
    any single aggregate's domain methods.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def create_document(
        self,
        organization_id: int,
        title: str,
        document_type: str,
        workflow_definition_id: int,
        actor: str,
        description: str | None = None,
    ) -> Document:
        async with self._uow_factory() as uow:
            definition = await uow.workflow_definitions.get(workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {workflow_definition_id} not found")
            document = Document.create(organization_id, title, document_type, description)
            await uow.documents.add(document)
            instance = WorkflowInstance.start(document.id, definition, actor)
            await uow.workflow_instances.add(instance)
            await uow.commit()
            return document

    async def get(self, document_id: int) -> Document:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            return document

    async def list_for_organization(self, organization_id: int) -> list[Document]:
        async with self._uow_factory() as uow:
            return await uow.documents.list_for_organization(organization_id)

    async def get_instance(self, document_id: int) -> WorkflowInstance:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_document(document_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for document {document_id}")
            return instance

    async def available_actions(self, document_id: int) -> list[WorkflowTransition]:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_document(document_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for document {document_id}")
            definition = await uow.workflow_definitions.get(instance.workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {instance.workflow_definition_id} not found")
            return instance.available_actions(definition)

    async def transition_document(
        self, document_id: int, action_name: str, actor: str, comment: str | None = None
    ) -> WorkflowInstance:
        async with self._uow_factory() as uow:
            instance = await uow.workflow_instances.get_for_document(document_id)
            if instance is None:
                raise NotFoundError(f"no workflow instance for document {document_id}")
            definition = await uow.workflow_definitions.get(instance.workflow_definition_id)
            if definition is None:
                raise NotFoundError(f"workflow definition {instance.workflow_definition_id} not found")
            instance.apply_transition(definition, action_name, actor, comment)
            await uow.commit()
            return instance

    async def add_version(
        self, document_id: int, content_ref: str, uploaded_by: str, notes: str | None = None
    ) -> DocumentVersion:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            version = document.add_version(content_ref, uploaded_by, notes)
            await uow.commit()
            return version

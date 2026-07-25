import re
from collections.abc import Callable

from app.application.storage_service import StorageService
from app.domain.documents.models import Document, DocumentVersion
from app.domain.shared.exceptions import NotFoundError
from app.domain.storage.exceptions import NoPrimaryStorageConnectionError
from app.domain.storage.models import StorageProvider
from app.domain.workflow.models import WorkflowTransition
from app.domain.workflow_instances.models import WorkflowInstance
from app.infrastructure.db.unit_of_work import UnitOfWork
from app.infrastructure.storage.factory import build_file_storage

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename(name: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", name).strip("_") or "file"


class DocumentService:
    """Orchestrates the Document, WorkflowDefinition, WorkflowInstance, and
    (for version uploads) StorageConnection aggregates for use cases that
    span more than one of them. This kind of cross-aggregate coordination
    belongs in the application layer, not in any single aggregate's domain
    methods.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage_service: StorageService) -> None:
        self._uow_factory = uow_factory
        self._storage_service = storage_service

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

    async def upload_version(
        self,
        document_id: int,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        uploaded_by: str,
        notes: str | None = None,
        source_provider: StorageProvider | None = None,
        source_external_id: str | None = None,
    ) -> DocumentVersion:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            connection = await uow.storage_connections.get_primary_for_organization(document.organization_id)
            if connection is None:
                raise NoPrimaryStorageConnectionError(document.organization_id)

            next_version_no = document.current_version_no + 1
            storage_key = f"org-{document.organization_id}/doc-{document.id}/v{next_version_no}-{_safe_filename(filename)}"
            secrets = connection.credential.secrets if connection.credential else {}
            adapter = build_file_storage(connection, secrets)
            await adapter.upload(storage_key, file_bytes, content_type)

            version = document.add_version(
                storage_connection_id=connection.id,
                storage_key=storage_key,
                original_filename=filename,
                content_type=content_type,
                size_bytes=len(file_bytes),
                uploaded_by=uploaded_by,
                notes=notes,
                source_provider=source_provider,
                source_external_id=source_external_id,
            )
            await uow.commit()
            return version

    async def import_version_from_external(
        self,
        document_id: int,
        connection_id: int,
        external_file_id: str,
        uploaded_by: str,
        notes: str | None = None,
    ) -> DocumentVersion:
        connection = await self._storage_service.get(connection_id)
        content, filename, content_type = await self._storage_service.import_external_file(
            connection_id, external_file_id
        )
        return await self.upload_version(
            document_id,
            content,
            filename,
            content_type,
            uploaded_by,
            notes,
            source_provider=connection.provider,
            source_external_id=external_file_id,
        )

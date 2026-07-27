import re
from collections.abc import Callable

from app.application.storage_service import StorageService
from app.domain.documents.models import Document, DocumentVersion
from app.domain.shared.exceptions import NotFoundError
from app.domain.storage.exceptions import NoPrimaryStorageConnectionError
from app.domain.storage.models import StorageProvider
from app.infrastructure.db.unit_of_work import UnitOfWork
from app.infrastructure.storage.factory import build_file_storage

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_filename(name: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", name).strip("_") or "file"


class DocumentService:
    """Orchestrates the Document, Contract, and StorageConnection aggregates
    for uploading/importing a version -- cross-aggregate coordination
    belongs in the application layer, not in any single aggregate's domain
    methods. Contract lifecycle/workflow concerns live in ContractService.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork], storage_service: StorageService) -> None:
        self._uow_factory = uow_factory
        self._storage_service = storage_service

    async def get(self, document_id: int) -> Document:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            return document

    async def list_for_contract(self, contract_id: int) -> list[Document]:
        async with self._uow_factory() as uow:
            return await uow.documents.list_for_contract(contract_id)

    async def set_summary(self, document_id: int, summary: str) -> Document:
        async with self._uow_factory() as uow:
            document = await uow.documents.get(document_id)
            if document is None:
                raise NotFoundError(f"document {document_id} not found")
            document.set_summary(summary)
            await uow.commit()
            return document

    async def download_version(self, version: DocumentVersion) -> bytes:
        async with self._uow_factory() as uow:
            connection = await uow.storage_connections.get(version.storage_connection_id)
            if connection is None:
                raise NotFoundError(f"storage connection {version.storage_connection_id} not found")
            secrets = connection.credential.secrets if connection.credential else {}
            adapter = build_file_storage(connection, secrets)
            return await adapter.download(version.storage_key)

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
            contract = await uow.contracts.get(document.contract_id)
            if contract is None:
                raise NotFoundError(f"contract {document.contract_id} not found")
            connection = await uow.storage_connections.get_primary_for_organization(contract.organization_id)
            if connection is None:
                raise NoPrimaryStorageConnectionError(contract.organization_id)

            next_version_no = document.current_version_no + 1
            storage_key = (
                f"org-{contract.organization_id}/contract-{contract.id}/doc-{document.id}"
                f"/v{next_version_no}-{_safe_filename(filename)}"
            )
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

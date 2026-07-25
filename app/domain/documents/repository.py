from typing import Protocol

from app.domain.documents.models import Document


class DocumentRepository(Protocol):
    async def add(self, document: Document) -> None: ...

    async def get(self, document_id: int) -> Document | None: ...

    async def list_for_organization(self, organization_id: int) -> list[Document]: ...

from typing import Protocol

from app.domain.documents.models import Document


class DocumentRepository(Protocol):
    async def get(self, document_id: int) -> Document | None: ...

    async def list_for_contract(self, contract_id: int) -> list[Document]: ...

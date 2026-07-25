from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import Document


class SqlAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, document: Document) -> None:
        self._session.add(document)
        await self._session.flush()
        # See SqlAlchemyWorkflowDefinitionRepository.add for why this is needed.
        await self._session.refresh(document, attribute_names=["versions"])

    async def get(self, document_id: int) -> Document | None:
        return await self._session.get(Document, document_id)

    async def list_for_organization(self, organization_id: int) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.organization_id == organization_id)
            .order_by(Document.updated_at.desc())
        )
        return list(result.scalars().all())

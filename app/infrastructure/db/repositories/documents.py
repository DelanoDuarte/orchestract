from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import Document


class SqlAlchemyDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, document_id: int) -> Document | None:
        return await self._session.get(Document, document_id)

    async def list_for_contract(self, contract_id: int) -> list[Document]:
        result = await self._session.execute(
            select(Document).where(Document.contract_id == contract_id).order_by(Document.id)
        )
        return list(result.scalars().all())

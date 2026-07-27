from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.contracts.exceptions import EmptyContractTitleError
from app.domain.shared.base import Base
from app.domain.shared.types import utcnow

if TYPE_CHECKING:
    from app.domain.documents.models import Document


class Contract(Base):
    """Aggregate root for a contract/matter being orchestrated through a
    workflow. A Contract owns one or more Documents (e.g. "Main Agreement",
    "Exhibit A", "Signature Page"), each with its own version history --
    the Contract itself is what moves through the workflow (see the separate
    WorkflowInstance aggregate, referenced by `contract_id`), not any single
    file.
    """

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    contract_type: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    summary_generated_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="Document.id",
        lazy="selectin",
    )

    @classmethod
    def create(
        cls, organization_id: int, title: str, contract_type: str, description: str | None = None
    ) -> "Contract":
        title = title.strip()
        if not title:
            raise EmptyContractTitleError()
        return cls(
            organization_id=organization_id,
            title=title,
            description=description,
            contract_type=contract_type,
        )

    def add_document(self, name: str) -> "Document":
        from app.domain.documents.models import Document

        document = Document.create(name)
        self.documents.append(document)
        self.updated_at = utcnow()
        return document

    def set_summary(self, summary: str) -> None:
        self.summary = summary
        self.summary_generated_at = utcnow()

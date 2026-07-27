from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
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
    ai_config: Mapped[dict] = mapped_column(JSON, default=dict)
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
            ai_config={},
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

    def set_ai_config(self, config: dict) -> None:
        """Stores this contract's optional per-contract AI override (see
        AIService for how `enabled`/`model`/`instructions`/`allowed_tools`
        are interpreted). Validating the values themselves is the
        application layer's job -- it's the one allowed to know about
        AI-specific constants like supported model names."""
        self.ai_config = config
        self.updated_at = utcnow()

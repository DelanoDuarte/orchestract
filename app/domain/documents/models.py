from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.documents.exceptions import EmptyDocumentTitleError
from app.domain.shared.base import Base
from app.domain.shared.types import utcnow


class DocumentVersion(Base):
    """An immutable version snapshot of a Document, owned by its aggregate."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_no: Mapped[int]
    content_ref: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="versions")


class Document(Base):
    """Aggregate root for a contract/document being orchestrated through a workflow.

    Which workflow it is running, and where it currently stands, lives in
    the separate WorkflowInstance aggregate (referenced by id) -- this
    aggregate only owns the document's own identity and version history.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    document_type: Mapped[str] = mapped_column(String(100))
    current_version_no: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_no",
        lazy="selectin",
    )

    @classmethod
    def create(
        cls, organization_id: int, title: str, document_type: str, description: str | None = None
    ) -> "Document":
        title = title.strip()
        if not title:
            raise EmptyDocumentTitleError()
        return cls(
            organization_id=organization_id,
            title=title,
            description=description,
            document_type=document_type,
            current_version_no=0,
        )

    def add_version(self, content_ref: str, uploaded_by: str, notes: str | None = None) -> DocumentVersion:
        self.current_version_no += 1
        version = DocumentVersion(
            version_no=self.current_version_no,
            content_ref=content_ref,
            uploaded_by=uploaded_by,
            notes=notes,
        )
        self.versions.append(version)
        self.updated_at = utcnow()
        return version

    def latest_version(self) -> DocumentVersion | None:
        return self.versions[-1] if self.versions else None

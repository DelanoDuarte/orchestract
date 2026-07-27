from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.documents.exceptions import EmptyDocumentNameError
from app.domain.shared.base import Base
from app.domain.shared.types import utcnow
from app.domain.storage.models import StorageProvider

if TYPE_CHECKING:
    from app.domain.contracts.models import Contract


class DocumentVersion(Base):
    """An immutable version snapshot of a Document, owned by its aggregate.

    `storage_key` is the object key/path inside `storage_connection_id`'s
    backend -- not a free-typed string. `source_provider`/`source_external_id`
    record how the bytes entered the system (direct upload vs. imported from
    a read-only connector like Google Drive/OneDrive) for traceability; both
    are null for a direct upload.
    """

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_no: Mapped[int]
    storage_connection_id: Mapped[int] = mapped_column(ForeignKey("storage_connections.id"))
    storage_key: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(150))
    size_bytes: Mapped[int]
    source_provider: Mapped[StorageProvider | None] = mapped_column(Enum(StorageProvider), default=None)
    source_external_id: Mapped[str | None] = mapped_column(String(300), default=None)
    uploaded_by: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="versions")


class Document(Base):
    """A single named file (e.g. "Main Agreement", "Exhibit A") owned by a
    Contract, with its own version history. Several Documents can belong to
    the same Contract -- the Contract is what moves through the workflow,
    not any one Document.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    current_version_no: Mapped[int] = mapped_column(default=0)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    summary_generated_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    contract: Mapped["Contract"] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_no",
        lazy="selectin",
    )

    @classmethod
    def create(cls, name: str) -> "Document":
        name = name.strip()
        if not name:
            raise EmptyDocumentNameError()
        return cls(name=name, current_version_no=0)

    def add_version(
        self,
        storage_connection_id: int,
        storage_key: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        uploaded_by: str,
        notes: str | None = None,
        source_provider: StorageProvider | None = None,
        source_external_id: str | None = None,
    ) -> DocumentVersion:
        self.current_version_no += 1
        version = DocumentVersion(
            version_no=self.current_version_no,
            storage_connection_id=storage_connection_id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_by=uploaded_by,
            notes=notes,
            source_provider=source_provider,
            source_external_id=source_external_id,
        )
        self.versions.append(version)
        self.updated_at = utcnow()
        return version

    def latest_version(self) -> DocumentVersion | None:
        return self.versions[-1] if self.versions else None

    def set_summary(self, summary: str) -> None:
        self.summary = summary
        self.summary_generated_at = utcnow()

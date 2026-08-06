import enum
import secrets
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.shared.base import Base
from app.domain.shared.password import hash_password, verify_password
from app.domain.shared.types import utcnow
from app.domain.sharing.exceptions import NoSharedDocumentsError


class ShareScope(str, enum.Enum):
    CONTRACT = "contract"  # every document on the contract
    DOCUMENTS = "documents"  # only the explicitly named documents


class ShareLinkDocument(Base):
    """Join row naming one Document exposed by a DOCUMENTS-scoped link.

    CONTRACT-scoped links have no rows here -- absence of rows means "every
    document on the contract", resolved against the live contract at view
    time so a document added later is automatically included.
    """

    __tablename__ = "share_link_documents"
    __table_args__ = (UniqueConstraint("share_link_id", "document_id", name="uq_share_link_document"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    share_link_id: Mapped[int] = mapped_column(ForeignKey("share_links.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))

    share_link: Mapped["ShareLink"] = relationship(back_populates="documents")


class ShareLink(Base):
    """A time-boxed, optionally password-protected view of a contract's
    documents for an external (unregistered) reviewer.

    `token` is the only secret in the URL; validity/expiry/revocation are all
    checked server-side against this row -- mirroring UserSession -- so a link
    can be killed by revoking it regardless of who holds the URL. An optional
    scrypt `password_hash` gates access (same scheme as user passwords), and
    `allow_download` decides whether the viewer can pull bytes as an attachment
    or is limited to inline preview.
    """

    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope: Mapped[ShareScope] = mapped_column(Enum(ShareScope))
    password_hash: Mapped[str | None] = mapped_column(String(300), default=None)
    allow_download: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_accessed_at: Mapped[datetime | None] = mapped_column(default=None)

    documents: Mapped[list[ShareLinkDocument]] = relationship(
        back_populates="share_link",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @classmethod
    def issue(
        cls,
        contract_id: int,
        scope: ShareScope,
        allow_download: bool,
        ttl: timedelta,
        created_by: str,
        document_ids: Iterable[int] | None = None,
        raw_password: str | None = None,
    ) -> "ShareLink":
        ids = list(dict.fromkeys(document_ids or []))
        if scope is ShareScope.DOCUMENTS and not ids:
            raise NoSharedDocumentsError()
        link = cls(
            contract_id=contract_id,
            token=secrets.token_urlsafe(32),
            scope=scope,
            password_hash=hash_password(raw_password) if raw_password else None,
            allow_download=allow_download,
            created_by=created_by,
            expires_at=utcnow() + ttl,
        )
        if scope is ShareScope.DOCUMENTS:
            link.documents = [ShareLinkDocument(document_id=doc_id) for doc_id in ids]
        return link

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    def is_active(self) -> bool:
        return self.revoked_at is None and utcnow() < self.expires_at

    def verify_password(self, raw_password: str) -> bool:
        if self.password_hash is None:
            return True
        return verify_password(raw_password, self.password_hash)

    def allowed_document_ids(self) -> set[int] | None:
        """The document ids this link exposes, or None for "all documents on
        the contract" (CONTRACT scope)."""
        if self.scope is ShareScope.CONTRACT:
            return None
        return {d.document_id for d in self.documents}

    def allows_document(self, document_id: int) -> bool:
        allowed = self.allowed_document_ids()
        return allowed is None or document_id in allowed

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = utcnow()

    def record_access(self) -> None:
        self.last_accessed_at = utcnow()

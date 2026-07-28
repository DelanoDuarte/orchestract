from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.shared.base import Base
from app.domain.shared.types import utcnow


class TermsAcceptance(Base):
    """An immutable audit record that a user accepted a specific version of the
    Terms & Conditions at a point in time.

    One row is written per acceptance event and rows are never updated or
    deleted, so an organization keeps a complete consent history -- who agreed
    to which revision, when, and from where. The captured `ip_address` and
    `user_agent` make the record defensible for a service that stores
    customers' contracts and documents in the cloud.
    """

    __tablename__ = "terms_acceptances"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    version: Mapped[str] = mapped_column(String(40), index=True)
    accepted_at: Mapped[datetime] = mapped_column(default=utcnow)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)

    @classmethod
    def record(
        cls,
        user_id: int,
        organization_id: int,
        version: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> "TermsAcceptance":
        return cls(
            user_id=user_id,
            organization_id=organization_id,
            version=version,
            ip_address=ip_address,
            # User-Agent strings can be arbitrarily long; keep within the column.
            user_agent=user_agent[:400] if user_agent else None,
        )

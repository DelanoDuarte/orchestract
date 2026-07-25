from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.shared.base import Base
from app.domain.shared.types import slugify, utcnow
from app.domain.tenancy.exceptions import EmptyOrganizationNameError


class Organization(Base):
    """Tenant boundary. Every other aggregate carries an organization_id."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def create(cls, name: str) -> "Organization":
        name = name.strip()
        if not name:
            raise EmptyOrganizationNameError()
        return cls(name=name, slug=slugify(name))

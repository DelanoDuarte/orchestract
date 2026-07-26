from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.agents.exceptions import EmptyAgentNameError
from app.domain.shared.base import Base
from app.domain.shared.types import slugify, utcnow


class Agent(Base):
    """A department/participant that can own steps in a workflow.

    Users are free to create arbitrary agents beyond the seeded defaults
    (Drafting, Negotiation, Signatory, ...) and assign them to whatever
    workflow steps they design.
    """

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_agent_org_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def create(cls, organization_id: int, name: str, description: str | None = None) -> "Agent":
        name = name.strip()
        if not name:
            raise EmptyAgentNameError()
        return cls(
            organization_id=organization_id,
            name=name,
            slug=slugify(name),
            description=description,
            is_active=True,
        )

    def rename(self, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise EmptyAgentNameError()
        self.name = new_name
        self.slug = slugify(new_name)

    def set_description(self, description: str | None) -> None:
        self.description = description

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

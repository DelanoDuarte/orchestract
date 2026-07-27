from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.shared.base import Base
from app.domain.shared.types import slugify, utcnow
from app.domain.tenancy.exceptions import EmptyOrganizationNameError
from app.domain.tenancy.plans import Plan


class Organization(Base):
    """Tenant boundary. Every other aggregate carries an organization_id."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(20), default=Plan.FREE.value)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), default=None)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), default=None)
    subscription_status: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def create(cls, name: str) -> "Organization":
        name = name.strip()
        if not name:
            raise EmptyOrganizationNameError()
        return cls(name=name, slug=slugify(name), plan=Plan.FREE.value)

    def set_plan(self, plan: Plan) -> None:
        self.plan = plan.value

    def set_stripe_customer(self, customer_id: str) -> None:
        self.stripe_customer_id = customer_id

    def apply_subscription(self, subscription_id: str, status: str, plan: Plan) -> None:
        self.stripe_subscription_id = subscription_id
        self.subscription_status = status
        self.plan = plan.value

    def clear_subscription(self) -> None:
        self.stripe_subscription_id = None
        self.subscription_status = None
        self.plan = Plan.FREE.value

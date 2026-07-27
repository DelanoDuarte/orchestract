import enum
from dataclasses import dataclass


class Plan(str, enum.Enum):
    FREE = "free"
    TEAM = "team"
    BUSINESS = "business"


@dataclass(frozen=True)
class PlanLimits:
    display_name: str
    monthly_price_usd: int
    max_users: int | None
    max_contracts: int | None
    ai_enabled: bool


PLAN_LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(
        display_name="Free", monthly_price_usd=0, max_users=3, max_contracts=5, ai_enabled=False
    ),
    Plan.TEAM: PlanLimits(
        display_name="Team", monthly_price_usd=49, max_users=15, max_contracts=None, ai_enabled=True
    ),
    Plan.BUSINESS: PlanLimits(
        display_name="Business",
        monthly_price_usd=199,
        max_users=None,
        max_contracts=None,
        ai_enabled=True,
    ),
}

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
    max_workflows: int | None
    max_agents: int | None
    ai_enabled: bool

    def can_add_user(self, current_count: int) -> bool:
        """Whether another user fits under this plan (None == unlimited).
        Mirrors the server-side guard in UserService.create_user so the UI
        can gate the 'New user' button before the form is even submitted."""
        return self.max_users is None or current_count < self.max_users

    def can_add_contract(self, current_count: int) -> bool:
        """Whether another contract fits under this plan (None == unlimited).
        Mirrors ContractService.create_contract's guard."""
        return self.max_contracts is None or current_count < self.max_contracts

    def can_add_workflow(self, current_count: int) -> bool:
        """Whether another workflow fits under this plan (None == unlimited).
        Mirrors WorkflowService.create_definition's guard."""
        return self.max_workflows is None or current_count < self.max_workflows

    def can_add_agent(self, current_count: int) -> bool:
        """Whether another agent fits under this plan (None == unlimited).
        Mirrors AgentService.create_agent's guard."""
        return self.max_agents is None or current_count < self.max_agents


PLAN_LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(
        display_name="Free",
        monthly_price_usd=0,
        max_users=3,
        max_contracts=5,
        max_workflows=3,
        max_agents=3,
        ai_enabled=False,
    ),
    Plan.TEAM: PlanLimits(
        display_name="Team",
        monthly_price_usd=49,
        max_users=15,
        max_contracts=None,
        max_workflows=None,
        max_agents=None,
        ai_enabled=True,
    ),
    Plan.BUSINESS: PlanLimits(
        display_name="Business",
        monthly_price_usd=199,
        max_users=None,
        max_contracts=None,
        max_workflows=None,
        max_agents=None,
        ai_enabled=True,
    ),
}

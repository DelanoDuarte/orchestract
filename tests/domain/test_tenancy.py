from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import PLAN_LIMITS, Plan


def test_organization_defaults_to_free_plan():
    organization = Organization.create("Acme Corp")
    assert organization.plan == Plan.FREE.value


def test_set_plan_updates_plan_only():
    organization = Organization.create("Acme Corp")
    organization.set_plan(Plan.TEAM)
    assert organization.plan == Plan.TEAM.value


def test_apply_subscription_sets_customer_plan_and_status():
    organization = Organization.create("Acme Corp")
    organization.set_stripe_customer("cus_123")
    organization.apply_subscription("sub_123", "active", Plan.TEAM)

    assert organization.stripe_customer_id == "cus_123"
    assert organization.stripe_subscription_id == "sub_123"
    assert organization.subscription_status == "active"
    assert organization.plan == Plan.TEAM.value


def test_clear_subscription_reverts_to_free():
    organization = Organization.create("Acme Corp")
    organization.set_stripe_customer("cus_123")
    organization.apply_subscription("sub_123", "active", Plan.BUSINESS)

    organization.clear_subscription()

    assert organization.plan == Plan.FREE.value
    assert organization.subscription_status is None
    assert organization.stripe_subscription_id is None
    # the Stripe customer id is kept -- the same customer may resubscribe later
    assert organization.stripe_customer_id == "cus_123"


def test_can_add_user_respects_the_plan_ceiling():
    free = PLAN_LIMITS[Plan.FREE]  # max_users=3
    assert free.can_add_user(2) is True
    assert free.can_add_user(3) is False  # at the ceiling -> button becomes "Upgrade"
    assert free.can_add_user(4) is False


def test_can_add_contract_respects_the_plan_ceiling():
    free = PLAN_LIMITS[Plan.FREE]  # max_contracts=5
    assert free.can_add_contract(4) is True
    assert free.can_add_contract(5) is False
    assert free.can_add_contract(6) is False


def test_can_add_workflow_and_agent_respect_the_free_ceiling():
    free = PLAN_LIMITS[Plan.FREE]  # max_workflows=3, max_agents=3
    assert free.can_add_workflow(2) is True
    assert free.can_add_workflow(3) is False
    assert free.can_add_agent(2) is True
    assert free.can_add_agent(3) is False


def test_unlimited_plan_always_allows_more():
    business = PLAN_LIMITS[Plan.BUSINESS]  # all caps = None
    assert business.can_add_user(10_000) is True
    assert business.can_add_contract(10_000) is True
    assert business.can_add_workflow(10_000) is True
    assert business.can_add_agent(10_000) is True

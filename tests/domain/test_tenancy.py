from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import Plan


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

import asyncio

from app.application.billing_service import BillingService
from app.domain.tenancy.models import Organization
from app.domain.tenancy.plans import Plan


class _FakeStripeObject(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _FakeEventData:
    def __init__(self, obj: dict) -> None:
        self.object = obj


class _FakeEvent:
    def __init__(self, event_type: str, obj: dict) -> None:
        self.type = event_type
        self.data = _FakeEventData(obj)


class _FakeOrganizationsRepo:
    def __init__(self, organization: Organization) -> None:
        self._organization = organization

    async def get(self, organization_id: int) -> Organization | None:
        return self._organization if organization_id == self._organization.id else None

    async def get_by_stripe_customer_id(self, customer_id: str) -> Organization | None:
        return self._organization if self._organization.stripe_customer_id == customer_id else None


class _FakeUow:
    def __init__(self, organization: Organization) -> None:
        self.organizations = _FakeOrganizationsRepo(organization)

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def commit(self) -> None:
        pass


def _service(organization: Organization) -> BillingService:
    return BillingService(lambda: _FakeUow(organization))


def test_checkout_completed_sets_stripe_customer_id():
    organization = Organization.create("Acme")
    organization.id = 1
    service = _service(organization)
    event = _FakeEvent(
        "checkout.session.completed",
        _FakeStripeObject(client_reference_id="1", customer="cus_123"),
    )

    asyncio.run(service.handle_webhook_event(event))

    assert organization.stripe_customer_id == "cus_123"


def test_subscription_updated_applies_plan_and_status(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ORCHESTRACT_STRIPE_PRICE_TEAM", "price_team_123")

    organization = Organization.create("Acme")
    organization.set_stripe_customer("cus_123")
    service = _service(organization)
    event = _FakeEvent(
        "customer.subscription.updated",
        _FakeStripeObject(
            id="sub_123",
            customer="cus_123",
            status="active",
            items={"data": [{"price": {"id": "price_team_123"}}]},
        ),
    )

    asyncio.run(service.handle_webhook_event(event))

    assert organization.plan == Plan.TEAM.value
    assert organization.subscription_status == "active"
    assert organization.stripe_subscription_id == "sub_123"
    get_settings.cache_clear()


def test_subscription_deleted_reverts_to_free():
    organization = Organization.create("Acme")
    organization.set_stripe_customer("cus_123")
    organization.apply_subscription("sub_123", "active", Plan.BUSINESS)
    service = _service(organization)
    event = _FakeEvent("customer.subscription.deleted", _FakeStripeObject(customer="cus_123"))

    asyncio.run(service.handle_webhook_event(event))

    assert organization.plan == Plan.FREE.value
    assert organization.subscription_status is None

from collections.abc import Callable

import stripe

from app.config import get_settings
from app.domain.shared.exceptions import NotFoundError
from app.domain.tenancy.plans import Plan
from app.infrastructure.billing.stripe_client import (
    create_billing_portal_session,
    create_checkout_session,
)
from app.infrastructure.db.unit_of_work import UnitOfWork

_PRICE_TO_PLAN_SETTINGS_ATTR = {
    Plan.TEAM: "stripe_price_team",
    Plan.BUSINESS: "stripe_price_business",
}


class BillingService:
    """Wraps Stripe Checkout/Portal session creation and syncs Organization
    subscription state from webhook events. Webhooks are the single source
    of truth for `plan`/`subscription_status` -- the post-checkout redirect
    never writes state itself.
    """

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def start_checkout(
        self, organization_id: int, plan: Plan, price_id: str, success_url: str, cancel_url: str, user_email: str
    ) -> str:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            customer_id = organization.stripe_customer_id
            customer_email = None if customer_id else user_email
        return create_checkout_session(
            customer_id=customer_id,
            customer_email=customer_email,
            price_id=price_id,
            client_reference_id=str(organization_id),
            success_url=success_url,
            cancel_url=cancel_url,
        )

    async def start_portal_session(self, organization_id: int, return_url: str) -> str:
        async with self._uow_factory() as uow:
            organization = await uow.organizations.get(organization_id)
            if organization is None:
                raise NotFoundError(f"organization {organization_id} not found")
            if organization.stripe_customer_id is None:
                raise NotFoundError(f"organization {organization_id} has no Stripe customer yet")
            customer_id = organization.stripe_customer_id
        return create_billing_portal_session(customer_id=customer_id, return_url=return_url)

    def _resolve_plan(self, price_id: str) -> Plan:
        settings = get_settings()
        for plan, attr in _PRICE_TO_PLAN_SETTINGS_ATTR.items():
            if price_id and price_id == getattr(settings, attr):
                return plan
        return Plan.FREE

    async def handle_webhook_event(self, event: stripe.Event) -> None:
        data = event.data.object
        if event.type == "checkout.session.completed":
            organization_id = int(data.client_reference_id)
            async with self._uow_factory() as uow:
                organization = await uow.organizations.get(organization_id)
                if organization is None:
                    return
                organization.set_stripe_customer(data.customer)
                await uow.commit()
            return
        if event.type in ("customer.subscription.updated", "customer.subscription.created"):
            price_id = data["items"]["data"][0]["price"]["id"] if data["items"]["data"] else None
            plan = self._resolve_plan(price_id)
            async with self._uow_factory() as uow:
                organization = await uow.organizations.get_by_stripe_customer_id(data.customer)
                if organization is None:
                    return
                organization.apply_subscription(data.id, data.status, plan)
                await uow.commit()
            return
        if event.type == "customer.subscription.deleted":
            async with self._uow_factory() as uow:
                organization = await uow.organizations.get_by_stripe_customer_id(data.customer)
                if organization is None:
                    return
                organization.clear_subscription()
                await uow.commit()
            return

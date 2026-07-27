from functools import lru_cache

import stripe

from app.config import get_settings


class InvalidWebhookEventError(Exception):
    """Raised when a webhook payload fails signature verification or is malformed."""


def billing_enabled() -> bool:
    return bool(get_settings().stripe_secret_key)


@lru_cache
def get_stripe_client() -> stripe.StripeClient:
    return stripe.StripeClient(get_settings().stripe_secret_key)


def create_checkout_session(
    *, customer_id: str | None, customer_email: str | None, price_id: str, client_reference_id: str,
    success_url: str, cancel_url: str,
) -> str:
    client = get_stripe_client()
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "client_reference_id": client_reference_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email
    session = client.v1.checkout.sessions.create(params=params)
    return session.url


def create_billing_portal_session(*, customer_id: str, return_url: str) -> str:
    client = get_stripe_client()
    session = client.v1.billing_portal.sessions.create(
        params={"customer": customer_id, "return_url": return_url}
    )
    return session.url


def retrieve_subscription(subscription_id: str) -> stripe.Subscription:
    client = get_stripe_client()
    return client.v1.subscriptions.retrieve(subscription_id)


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    client = get_stripe_client()
    settings = get_settings()
    try:
        return client.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.SignatureVerificationError, ValueError) as exc:
        raise InvalidWebhookEventError(str(exc)) from exc

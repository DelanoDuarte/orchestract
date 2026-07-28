"""Idempotently provision the Stripe products & prices the billing flow needs.

Creates one Product per paid plan (Team, Business -- kept separate per Stripe's
catalog guidance) and one recurring monthly Price each, priced from the single
source of truth in ``app.domain.tenancy.plans.PLAN_LIMITS``. Prices are keyed by
a stable ``lookup_key`` so re-running finds and reuses the existing price
instead of creating duplicates.

Run it after setting ORCHESTRACT_STRIPE_SECRET_KEY:

    uv run python -m app.infrastructure.billing.setup_stripe

It prints the resulting price ids as ready-to-paste .env lines.
"""

from app.config import get_settings
from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.infrastructure.billing.stripe_client import billing_enabled, get_stripe_client

# Which plans get a Stripe product/price, and the env var each price id feeds.
_PAID_PLANS: dict[Plan, str] = {
    Plan.TEAM: "ORCHESTRACT_STRIPE_PRICE_TEAM",
    Plan.BUSINESS: "ORCHESTRACT_STRIPE_PRICE_BUSINESS",
}


def _lookup_key(plan: Plan) -> str:
    return f"orchestract_{plan.value}_monthly"


def _find_existing_price(client, lookup_key: str):
    """Returns the active price carrying this lookup_key, or None. Lets the
    script be run repeatedly (e.g. after adding a plan) without duplicating."""
    result = client.v1.prices.list(params={"lookup_keys": [lookup_key], "active": True, "limit": 1})
    data = list(result.data)
    return data[0] if data else None


def ensure_price(client, plan: Plan) -> tuple[str, str]:
    """Returns (product_id, price_id), creating them if needed."""
    limits = PLAN_LIMITS[plan]
    lookup_key = _lookup_key(plan)

    existing = _find_existing_price(client, lookup_key)
    if existing is not None:
        print(f"  {plan.value}: reusing existing price {existing.id} (lookup_key={lookup_key})")
        return existing.product, existing.id

    product = client.v1.products.create(
        params={
            "name": f"Orchestract {limits.display_name}",
            "description": f"Orchestract {limits.display_name} plan — monthly subscription.",
            "metadata": {"plan": plan.value},
        }
    )
    price = client.v1.prices.create(
        params={
            "product": product.id,
            "currency": "usd",
            "unit_amount": limits.monthly_price_usd * 100,
            "recurring": {"interval": "month"},
            "lookup_key": lookup_key,
            "nickname": f"{limits.display_name} Monthly",
            "metadata": {"plan": plan.value},
        }
    )
    print(f"  {plan.value}: created product {product.id} + price {price.id} (${limits.monthly_price_usd}/mo)")
    return product.id, price.id


def ensure_portal_configuration(client, plan_products: dict[Plan, tuple[str, str]]) -> None:
    """Ensures a Customer Portal configuration exists so the "Manage billing"
    button lets customers switch plans, update payment methods, view invoices,
    and cancel. Best-effort: if it can't be created (e.g. missing public
    business info), we print guidance rather than fail the whole setup."""
    existing = list(client.v1.billing_portal.configurations.list(params={"is_default": True, "limit": 1}).data)
    if existing:
        print(f"  portal: reusing existing default configuration {existing[0].id}")
        return

    settings = get_settings()
    try:
        config = client.v1.billing_portal.configurations.create(
            params={
                "business_profile": {"terms_of_service_url": f"{settings.app_base_url}/terms"},
                "features": {
                    "invoice_history": {"enabled": True},
                    "payment_method_update": {"enabled": True},
                    "customer_update": {"enabled": True, "allowed_updates": ["email", "address", "tax_id"]},
                    "subscription_cancel": {"enabled": True, "mode": "at_period_end"},
                    "subscription_update": {
                        "enabled": True,
                        "default_allowed_updates": ["price"],
                        "proration_behavior": "create_prorations",
                        "products": [
                            {"product": product_id, "prices": [price_id]}
                            for product_id, price_id in plan_products.values()
                        ],
                    },
                },
            }
        )
        print(f"  portal: created default configuration {config.id}")
    except Exception as exc:  # noqa: BLE001 - surface, don't abort the price setup
        print(f"  portal: skipped ({exc}). Configure it in Dashboard → Settings → Billing → Customer portal.")


def main() -> None:
    if not billing_enabled():
        raise SystemExit(
            "ORCHESTRACT_STRIPE_SECRET_KEY is not set. Add it to .env (or the environment) and re-run."
        )

    client = get_stripe_client()
    print("Provisioning Stripe products & prices (test mode uses your test key)...")
    env_lines: list[str] = []
    plan_products: dict[Plan, tuple[str, str]] = {}
    for plan, env_var in _PAID_PLANS.items():
        product_id, price_id = ensure_price(client, plan)
        plan_products[plan] = (product_id, price_id)
        env_lines.append(f"{env_var}={price_id}")

    ensure_portal_configuration(client, plan_products)

    print("\nAdd these to your .env:\n")
    for line in env_lines:
        print(f"  {line}")


if __name__ == "__main__":
    main()

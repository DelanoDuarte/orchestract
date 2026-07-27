"""One-off idempotent Stripe setup: creates the Team/Business Products and
their monthly Prices if they don't already exist, and prints the Price IDs
to paste into .env. Run manually: `uv run python -m app.infrastructure.billing.setup`.

Mirrors app/infrastructure/seed.py in spirit (regenerable, safe to re-run) --
but this talks to Stripe's API instead of the local DB.
"""

from app.domain.tenancy.plans import PLAN_LIMITS, Plan
from app.infrastructure.billing.stripe_client import get_stripe_client

_LOOKUP_KEYS = {
    Plan.TEAM: "orchestract_team_monthly",
    Plan.BUSINESS: "orchestract_business_monthly",
}


def _ensure_price(plan: Plan) -> str:
    client = get_stripe_client()
    lookup_key = _LOOKUP_KEYS[plan]
    existing = client.v1.prices.list(params={"lookup_keys": [lookup_key], "active": True})
    if existing.data:
        return existing.data[0].id

    limits = PLAN_LIMITS[plan]
    product = client.v1.products.create(params={"name": f"Orchestract {limits.display_name}"})
    price = client.v1.prices.create(
        params={
            "product": product.id,
            "currency": "usd",
            "unit_amount": limits.monthly_price_usd * 100,
            "recurring": {"interval": "month"},
            "lookup_key": lookup_key,
        }
    )
    return price.id


def main() -> None:
    team_price_id = _ensure_price(Plan.TEAM)
    business_price_id = _ensure_price(Plan.BUSINESS)
    print("Stripe products/prices ready. Add these to .env:\n")
    print(f"ORCHESTRACT_STRIPE_PRICE_TEAM={team_price_id}")
    print(f"ORCHESTRACT_STRIPE_PRICE_BUSINESS={business_price_id}")


if __name__ == "__main__":
    main()

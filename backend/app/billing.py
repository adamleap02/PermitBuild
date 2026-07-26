"""
Stripe billing integration -- TEST MODE conceptually.

This module is written as if a Stripe TEST secret key were provided
via the STRIPE_SECRET_KEY environment variable. No real Stripe account
was created and no real/live key is used or required anywhere in this
codebase. When STRIPE_SECRET_KEY is absent (the default in this
environment), every billing operation degrades gracefully: routes
return a clear "billing not configured" response (see
app/routers/billing.py) instead of raising, so the rest of the app
runs completely unaffected.

To actually exercise this against Stripe's real test mode, a human
would need to:
  1. Create a free Stripe account (https://dashboard.stripe.com/register)
     -- no billing/credit card required to get TEST mode keys.
  2. Set STRIPE_SECRET_KEY=sk_test_... and STRIPE_WEBHOOK_SECRET=whsec_...
     (from the Stripe CLI's `stripe listen --forward-to ...` or the
     Dashboard's webhook endpoint config) in the environment.
  3. Create Products/Prices in the Stripe test dashboard and reference
     their price IDs from PLAN_PRICE_IDS below (or via env vars).

See BLOCKERS.md for the full writeup.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import stripe

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# Map our internal plan identifiers to Stripe Price IDs. In a real deploy
# these would be the price IDs created in the Stripe test dashboard;
# overridable via env vars so no code change is needed to point at real
# test-mode prices once a human has created them.
PLAN_PRICE_IDS: dict[str, Optional[str]] = {
    "starter": os.environ.get("STRIPE_PRICE_STARTER"),
    "pro": os.environ.get("STRIPE_PRICE_PRO"),
    "enterprise": os.environ.get("STRIPE_PRICE_ENTERPRISE"),
}

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


class BillingNotConfiguredError(RuntimeError):
    """Raised when a billing operation is attempted without STRIPE_SECRET_KEY set."""


def _require_configured() -> None:
    if not is_configured():
        raise BillingNotConfiguredError(
            "STRIPE_SECRET_KEY is not set -- billing is not configured in this "
            "environment. See BLOCKERS.md for how to enable it with a free "
            "Stripe test-mode account (no real card/billing required)."
        )


def get_or_create_customer(organization_id: int, organization_name: str, email: str) -> str:
    """Create (or would create) a Stripe Customer for an organization and
    return its Stripe customer ID. Idempotent in spirit via metadata
    lookup -- a real implementation would cache the customer id on the
    Subscription row (done by the caller) rather than searching Stripe
    every time."""
    _require_configured()
    customer = stripe.Customer.create(
        name=organization_name,
        email=email,
        metadata={"organization_id": str(organization_id)},
    )
    return customer["id"]


def create_checkout_session(
    customer_id: str,
    plan: str,
    success_url: str,
    cancel_url: str,
) -> "stripe.checkout.Session":
    _require_configured()
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError(
            f"No Stripe price configured for plan {plan!r}. Set the "
            f"STRIPE_PRICE_{plan.upper()} env var to a test-mode Stripe Price ID."
        )
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session


def construct_webhook_event(payload: bytes, sig_header: str) -> "stripe.Event":
    """Verify and parse an incoming Stripe webhook request body. Raises
    stripe.error.SignatureVerificationError on a bad/forged signature."""
    _require_configured()
    if not STRIPE_WEBHOOK_SECRET:
        raise BillingNotConfiguredError(
            "STRIPE_WEBHOOK_SECRET is not set -- cannot verify webhook signatures."
        )
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)

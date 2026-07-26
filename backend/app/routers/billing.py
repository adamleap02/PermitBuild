"""
Stripe billing routes -- TEST MODE conceptually, degrades gracefully
without a key. See app/billing.py and BLOCKERS.md for full context:
no real Stripe account was created and no real key is used anywhere.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import billing
from app.db import get_db
from app.models import Subscription, SubscriptionStatus, User
from app.schemas import BillingStatusResponse, CheckoutSessionRequest, CheckoutSessionResponse
from app.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


def _not_configured_response() -> BillingStatusResponse:
    return BillingStatusResponse(
        configured=False,
        message=(
            "Billing is not configured in this environment (STRIPE_SECRET_KEY is unset). "
            "This is expected for the free/local MVP -- see BLOCKERS.md for how a human "
            "enables it with a free Stripe TEST-mode account (no real card required)."
        ),
    )


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not billing.is_configured():
        return _not_configured_response()

    sub = (
        db.query(Subscription)
        .filter(Subscription.organization_id == current_user.organization_id)
        .order_by(Subscription.updated_at.desc())
        .first()
    )
    if sub is None:
        return BillingStatusResponse(configured=True, status=SubscriptionStatus.NONE.value)

    return BillingStatusResponse(
        configured=True,
        plan=sub.plan,
        status=sub.status.value if hasattr(sub.status, "value") else sub.status,
        current_period_end=sub.current_period_end,
        stripe_customer_id=sub.stripe_customer_id,
    )


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not billing.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Billing is not configured (STRIPE_SECRET_KEY unset). "
                "See BLOCKERS.md to enable it with a free Stripe test-mode key."
            ),
        )

    sub = (
        db.query(Subscription)
        .filter(Subscription.organization_id == current_user.organization_id)
        .order_by(Subscription.updated_at.desc())
        .first()
    )
    try:
        if sub is None or not sub.stripe_customer_id:
            customer_id = billing.get_or_create_customer(
                current_user.organization_id, current_user.organization.name, current_user.email
            )
            if sub is None:
                sub = Subscription(organization_id=current_user.organization_id, stripe_customer_id=customer_id)
                db.add(sub)
            else:
                sub.stripe_customer_id = customer_id
            db.commit()
        else:
            customer_id = sub.stripe_customer_id

        session = billing.create_checkout_session(
            customer_id=customer_id,
            plan=payload.plan,
            success_url=payload.success_url,
            cancel_url=payload.cancel_url,
        )
    except billing.BillingNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except stripe.error.StripeError as exc:  # pragma: no cover -- requires a real Stripe key to hit
        logger.exception("Stripe checkout session creation failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    return CheckoutSessionResponse(checkout_url=session["url"], session_id=session["id"])


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook receiver. Verifies the signature and updates the
    relevant Subscription row on checkout.session.completed /
    customer.subscription.updated / customer.subscription.deleted.

    Returns a clear 503 (never a crash) if billing isn't configured --
    matches the rest of this module's graceful-degradation posture.
    """
    if not billing.is_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured (STRIPE_SECRET_KEY unset).")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = billing.construct_webhook_event(payload, sig_header)
    except billing.BillingNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except stripe.error.SignatureVerificationError as exc:  # pragma: no cover -- requires a real webhook secret
        raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}") from exc

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type in ("checkout.session.completed",):
        customer_id = data.get("customer")
        sub = db.query(Subscription).filter(Subscription.stripe_customer_id == customer_id).one_or_none()
        if sub is not None:
            sub.stripe_subscription_id = data.get("subscription")
            sub.status = SubscriptionStatus.ACTIVE
            sub.raw_stripe_data = data
            db.commit()

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        stripe_sub_id = data.get("id")
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).one_or_none()
        if sub is not None:
            status_map = {
                "trialing": SubscriptionStatus.TRIALING,
                "active": SubscriptionStatus.ACTIVE,
                "past_due": SubscriptionStatus.PAST_DUE,
                "canceled": SubscriptionStatus.CANCELED,
                "incomplete": SubscriptionStatus.INCOMPLETE,
            }
            sub.status = status_map.get(data.get("status"), sub.status)
            sub.cancel_at_period_end = bool(data.get("cancel_at_period_end"))
            period_end = data.get("current_period_end")
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
            sub.raw_stripe_data = data
            db.commit()

    else:
        logger.info("Unhandled Stripe webhook event type: %s", event_type)

    return {"received": True}

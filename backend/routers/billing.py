"""Billing / subscription endpoints.

Phase 3: read-only entitlement status for the current user, so the frontend can
gate the add-source flow. Phase 4 (Stripe): hosted Checkout to subscribe, webhook
as the source of truth, Customer Portal for self-service management.
"""
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.services import stripe_billing
from app.services.entitlements import get_entitlement
from app.storage.sqlite import fetch_one

logger = logging.getLogger(__name__)

router = APIRouter()


class EntitlementOut(BaseModel):
    active: bool
    status: str
    provider: str | None
    current_period_end: str | None


class SessionUrlOut(BaseModel):
    url: str


@router.get("/status", response_model=EntitlementOut)
def billing_status(current_user: dict = Depends(get_current_user)):
    """Return the current user's subscription entitlement."""
    return get_entitlement(current_user["id"])


@router.post("/checkout-session", response_model=SessionUrlOut)
def create_checkout_session(current_user: dict = Depends(get_current_user)):
    """Start a Stripe hosted Checkout for the single subscription plan."""
    user_id = current_user["id"]
    user = fetch_one("SELECT email FROM users WHERE id = %s", (user_id,))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    url = stripe_billing.create_checkout_session(user_id, user["email"])
    return {"url": url}


@router.post("/portal-session", response_model=SessionUrlOut)
def create_portal_session(current_user: dict = Depends(get_current_user)):
    """Open the Stripe Customer Portal (cancel / update payment method)."""
    try:
        url = stripe_billing.create_portal_session(current_user["id"])
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_stripe_customer")
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook receiver — signature-verified, source of truth for subscriptions."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe_billing.construct_webhook_event(payload, sig_header)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_signature")
    try:
        stripe_billing.handle_webhook_event(event)
    except Exception:
        # Let Stripe retry on our failure rather than silently dropping the event.
        logger.exception("stripe webhook handling failed: %s", event["type"])
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="webhook_error")
    return {"received": True}

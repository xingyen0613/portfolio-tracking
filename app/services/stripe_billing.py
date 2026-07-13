"""Stripe billing adapter — the only module that talks to Stripe.

Hosted Checkout starts a subscription; webhook events are the source of truth
that writes the `subscriptions` table. entitlements.py stays provider-agnostic:
this module just writes provider='stripe' rows using the shared status
vocabulary (active|trialing|past_due|canceled).
"""
from datetime import datetime, timezone
import os
import uuid

import stripe

from app.storage.sqlite import execute, fetch_one

# Stripe statuses we pass through as-is; everything else (canceled, unpaid,
# incomplete, incomplete_expired, paused) collapses to 'canceled'.
_PASSTHROUGH_STATUSES = {"active", "trialing", "past_due"}


def _client() -> stripe.StripeClient:
    api_key = os.getenv("STRIPE_SECRET_KEY", "")
    if not api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    return stripe.StripeClient(api_key)


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")


def _map_status(stripe_status: str) -> str:
    return stripe_status if stripe_status in _PASSTHROUGH_STATUSES else "canceled"


def _get(obj, key, default=None):
    """StripeObject supports [] and `in` but not .get(); works for plain dicts too."""
    return obj[key] if key in obj else default


def _period_end_iso(subscription) -> str | None:
    """current_period_end lives on the subscription item (API 2025-03+)."""
    items = _get(subscription, "items")
    data = _get(items, "data", []) if items else []
    if not data:
        return None
    epoch = _get(data[0], "current_period_end")
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def create_checkout_session(user_id: str, email: str) -> str:
    """Create a hosted Checkout session for the single flat plan; return its URL."""
    price_id = os.getenv("STRIPE_PRICE_ID", "")
    if not price_id:
        raise RuntimeError("STRIPE_PRICE_ID is not set")
    base = _frontend_base_url()
    session = _client().v1.checkout.sessions.create(params={
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "client_reference_id": user_id,
        "customer_email": email,
        # Stamp the user onto the subscription so later subscription.* webhook
        # events can be attributed even if they arrive out of order.
        "subscription_data": {"metadata": {"user_id": user_id}},
        "success_url": f"{base}/?billing=success",
        "cancel_url": f"{base}/?billing=cancel",
    })
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str) -> stripe.Event:
    """Verify the webhook signature and parse the event. Raises on bad signature."""
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def handle_webhook_event(event) -> None:
    """Apply a verified Stripe event to the subscriptions table.

    Unhandled event types are ignored (webhook endpoint still returns 200 so
    Stripe doesn't retry them).
    """
    kind = event["type"]
    obj = event["data"]["object"]

    if kind == "checkout.session.completed":
        user_id = _get(obj, "client_reference_id")
        sub_id = _get(obj, "subscription")
        if not user_id or not sub_id:
            return
        subscription = _client().v1.subscriptions.retrieve(sub_id)
        _upsert(user_id, subscription)
        return

    if kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        user_id = _get(_get(obj, "metadata") or {}, "user_id")
        if not user_id:
            row = fetch_one(
                "SELECT user_id FROM subscriptions WHERE provider = 'stripe' AND external_id = %s",
                (obj["id"],),
            )
            if not row:
                return  # unknown subscription (e.g. created outside the app)
            user_id = row["user_id"]
        _upsert(user_id, obj)


def _upsert(user_id: str, subscription) -> None:
    status = _map_status(subscription["status"])
    now = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO subscriptions
            (id, user_id, provider, external_id, external_customer_id, status,
             current_period_end, created_at, updated_at)
        VALUES (%s, %s, 'stripe', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            provider             = 'stripe',
            external_id          = EXCLUDED.external_id,
            external_customer_id = EXCLUDED.external_customer_id,
            status               = EXCLUDED.status,
            current_period_end   = EXCLUDED.current_period_end,
            updated_at           = EXCLUDED.updated_at
        """,
        (str(uuid.uuid4()), user_id, subscription["id"], _get(subscription, "customer"),
         status, _period_end_iso(subscription), now, now),
    )


def create_portal_session(user_id: str) -> str:
    """Create a Customer Portal session for the user's Stripe customer; return its URL."""
    row = fetch_one(
        """SELECT external_customer_id FROM subscriptions
            WHERE user_id = %s AND provider = 'stripe'""",
        (user_id,),
    )
    if not row or not row["external_customer_id"]:
        raise ValueError("no_stripe_customer")
    session = _client().v1.billing_portal.sessions.create(params={
        "customer": row["external_customer_id"],
        "return_url": f"{_frontend_base_url()}/?billing=portal_return",
    })
    return session.url

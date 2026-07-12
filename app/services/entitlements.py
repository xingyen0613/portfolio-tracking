"""Subscription entitlement — the single source of truth for "is this user allowed".

All gating across the app (daily batch, adding sources, frontend) goes through
`get_entitlement` / `is_active`. This layer knows nothing about payment providers:
PayPal, a future Stripe, and the `comp` whitelist all just write a `status` into the
`subscriptions` table. Swap or add a provider without touching callers here.
"""
from datetime import datetime, timezone
import uuid

from app.storage.sqlite import execute, fetch_one

ACTIVE_STATUSES = {"active", "trialing"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(current_period_end: str | None) -> bool:
    """NULL end = never expires (comp). Otherwise expired if end < now (UTC)."""
    if not current_period_end:
        return False
    try:
        end = datetime.fromisoformat(current_period_end.replace("Z", "+00:00"))
    except ValueError:
        # Unparseable value → treat as not expired rather than locking the user out.
        return False
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end < _now()


def get_entitlement(user_id: str) -> dict:
    """Resolve a user's current entitlement.

    Returns {'active': bool, 'status': str, 'provider': str|None, 'current_period_end': str|None}.
    Precedence:
      1. is_system users are always active (owner exemption).
      2. Otherwise read the user's subscriptions row.
      3. No row → status 'none', inactive.
    """
    user = fetch_one("SELECT is_system FROM users WHERE id = %s", (user_id,))
    if user and user["is_system"]:
        return {"active": True, "status": "active", "provider": "system",
                "current_period_end": None}

    row = fetch_one(
        """SELECT status, provider, current_period_end
             FROM subscriptions WHERE user_id = %s""",
        (user_id,),
    )
    if not row:
        return {"active": False, "status": "none", "provider": None,
                "current_period_end": None}

    active = row["status"] in ACTIVE_STATUSES and not _is_expired(row["current_period_end"])
    return {"active": active, "status": row["status"], "provider": row["provider"],
            "current_period_end": row["current_period_end"]}


def is_active(user_id: str) -> bool:
    """Convenience gate used by batch / API dependencies."""
    return get_entitlement(user_id)["active"]


# --- Whitelist (comp) management --------------------------------------------

def _user_id_by_email(email: str) -> str:
    row = fetch_one("SELECT id FROM users WHERE email = %s", (email,))
    if not row:
        raise ValueError(f"No user found with email {email!r}")
    return row["id"]


def grant_comp(email: str) -> None:
    """Grant a free (complimentary) active subscription to the user with this email."""
    user_id = _user_id_by_email(email)
    now = _now().isoformat()
    execute(
        """
        INSERT INTO subscriptions
            (id, user_id, provider, external_id, status, current_period_end,
             created_at, updated_at)
        VALUES (%s, %s, 'comp', NULL, 'active', NULL, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            provider           = 'comp',
            external_id        = NULL,
            status             = 'active',
            current_period_end = NULL,
            updated_at         = EXCLUDED.updated_at
        """,
        (str(uuid.uuid4()), user_id, now, now),
    )


def revoke_comp(email: str) -> None:
    """Revoke a comp subscription (mark canceled; the row is kept for history)."""
    user_id = _user_id_by_email(email)
    now = _now().isoformat()
    execute(
        """UPDATE subscriptions
              SET status = 'canceled', updated_at = %s
            WHERE user_id = %s AND provider = 'comp'""",
        (now, user_id),
    )

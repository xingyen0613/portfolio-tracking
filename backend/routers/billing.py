"""Billing / subscription endpoints.

Phase 3: read-only entitlement status for the current user, so the frontend can
gate the add-source flow. PayPal subscribe/link/webhook endpoints land here in Phase 4.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.services.entitlements import get_entitlement

router = APIRouter()


class EntitlementOut(BaseModel):
    active: bool
    status: str
    provider: str | None
    current_period_end: str | None


@router.get("/status", response_model=EntitlementOut)
def billing_status(current_user: dict = Depends(get_current_user)):
    """Return the current user's subscription entitlement."""
    return get_entitlement(current_user["id"])

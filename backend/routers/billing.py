"""Billing / subscription endpoints.

Phase 3: read-only entitlement status for the current user, so the frontend can
gate the add-source flow. Phase 4 (ECPay 定期定額): checkout returns an
auto-submit form for ECPay's hosted payment page; the two ECPay callbacks are
the source of truth for the subscriptions table; cancel terminates future
charges via CreditCardPeriodAction.
"""
import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.services import ecpay_billing
from app.services.entitlements import get_entitlement

logger = logging.getLogger(__name__)

router = APIRouter()


class EntitlementOut(BaseModel):
    active: bool
    status: str
    provider: str | None
    current_period_end: str | None
    cancel_at_period_end: bool


class CheckoutOut(BaseModel):
    action: str
    params: dict[str, str]


@router.get("/status", response_model=EntitlementOut)
def billing_status(current_user: dict = Depends(get_current_user)):
    """Return the current user's subscription entitlement."""
    return get_entitlement(current_user["id"])


@router.post("/checkout", response_model=CheckoutOut)
def create_checkout(current_user: dict = Depends(get_current_user)):
    """Build the ECPay recurring-payment order for the frontend to form-POST."""
    return ecpay_billing.create_checkout(current_user["id"])


@router.post("/cancel")
def cancel_subscription(current_user: dict = Depends(get_current_user)):
    """Terminate future charges; the paid period stays usable until it ends."""
    try:
        ecpay_billing.cancel(current_user["id"])
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="no_ecpay_subscription")
    except RuntimeError as exc:
        logger.error("ecpay cancel failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="ecpay_cancel_failed")
    return {"ok": True}


# ECPay server-to-server callbacks: unauthenticated form POSTs, authenticated
# by CheckMacValue instead. Must answer plain-text `1|OK` with HTTP 200 within
# 10 seconds or ECPay retries (up to 4 times a day).

async def _ecpay_form(request: Request) -> dict:
    """Parse the callback body with PHP $_POST semantics.

    CheckMacValue is computed over every posted field, so parsing must keep
    blank values and decode UTF-8 exactly like PHP does — parse the raw body
    ourselves instead of trusting request.form()'s latin-1 round-trip.
    """
    body = (await request.body()).decode("utf-8")
    return dict(urllib.parse.parse_qsl(body, keep_blank_values=True))


@router.post("/ecpay/return", response_class=PlainTextResponse)
async def ecpay_return(request: Request):
    """First-authorization result (ReturnURL)."""
    form = await _ecpay_form(request)
    try:
        ecpay_billing.handle_first_auth(form)
    except ValueError:
        logger.warning("ecpay return callback failed CheckMacValue: %s",
                       form.get("MerchantTradeNo"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="invalid_checkmacvalue")
    return "1|OK"


@router.post("/ecpay/period", response_class=PlainTextResponse)
async def ecpay_period(request: Request):
    """Recurring-charge result from the 2nd period on (PeriodReturnURL)."""
    form = await _ecpay_form(request)
    try:
        ecpay_billing.handle_period(form)
    except ValueError:
        logger.warning("ecpay period callback failed CheckMacValue: %s",
                       form.get("MerchantTradeNo"))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="invalid_checkmacvalue")
    return "1|OK"

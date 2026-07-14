"""ECPay (綠界) billing adapter — the only module that talks to ECPay.

AIO 定期定額 (credit-card recurring): checkout is a browser form POST to ECPay's
hosted payment page. The first authorization result comes back to ReturnURL;
every later period hits PeriodReturnURL. Both are CheckMacValue-verified form
POSTs and are the source of truth writing the `subscriptions` table
(provider='ecpay'), using the shared status vocabulary. Cancel goes through the
CreditCardPeriodAction API: it terminates future charges only, so the paid
period stays usable and we just flag cancel_at_period_end.

Spec sources (fetched 2026-07-14):
- 定期定額參數: https://developers.ecpay.com.tw/2868.md
- 付款結果通知: https://developers.ecpay.com.tw/2878.md
- 定期定額每期通知: https://developers.ecpay.com.tw/5631.md
- 訂單作業 (Cancel): https://developers.ecpay.com.tw/2900.md
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import calendar
import hashlib
import hmac
import logging
import os
import secrets
import time
import urllib.parse
import uuid

import requests

from app.storage.sqlite import execute, fetch_one

logger = logging.getLogger(__name__)

_TAIPEI = ZoneInfo("Asia/Taipei")  # ECPay requires UTC+8 trade dates

# Monthly plan, charged every 1 month. ECPay has no open-ended contract:
# ExecTimes is capped at 999, which at monthly frequency is effectively
# "until canceled".
_PERIOD_TYPE = "M"
_FREQUENCY = 1
_EXEC_TIMES = 999


def _cfg(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _base_url() -> str:
    # payment-stage.ecpay.com.tw (sandbox) / payment.ecpay.com.tw (production)
    return os.getenv("ECPAY_BASE_URL", "https://payment-stage.ecpay.com.tw").rstrip("/")


def _backend_public_url() -> str:
    # Must be publicly reachable on port 443 for ECPay's server-side callbacks
    # (localhost never works — use ngrok in development).
    return _cfg("BACKEND_PUBLIC_URL").rstrip("/")


def _frontend_base_url() -> str:
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")


def _period_amount() -> int:
    return int(os.getenv("ECPAY_PERIOD_AMOUNT", "50"))


# --- CheckMacValue (CMV-SHA256) ----------------------------------------------
# Ported from the official PHP SDK per ecpay skill guides/13 §Python; verified
# against test-vectors/checkmacvalue.json.

def _ecpay_url_encode(source: str) -> str:
    """Match PHP urlencode() + the SDK's lowercase/.NET replacements."""
    encoded = urllib.parse.quote_plus(source)  # space → '+'
    encoded = encoded.replace("~", "%7E")  # quote_plus leaves '~' as-is; PHP doesn't
    encoded = encoded.lower()
    for old, new in {
        "%2d": "-", "%5f": "_", "%2e": ".", "%21": "!",
        "%2a": "*", "%28": "(", "%29": ")",
    }.items():
        encoded = encoded.replace(old, new)
    return encoded


def generate_check_mac_value(params: dict) -> str:
    filtered = {k: v for k, v in params.items() if k != "CheckMacValue"}
    sorted_params = sorted(filtered.items(), key=lambda x: x[0].lower())
    param_str = "&".join(f"{k}={v}" for k, v in sorted_params)
    raw = f"HashKey={_cfg('ECPAY_HASH_KEY')}&{param_str}&HashIV={_cfg('ECPAY_HASH_IV')}"
    return hashlib.sha256(_ecpay_url_encode(raw).encode("utf-8")).hexdigest().upper()


def verify_check_mac_value(params: dict) -> bool:
    received = params.get("CheckMacValue", "")
    return hmac.compare_digest(received, generate_check_mac_value(params))


# --- Checkout -----------------------------------------------------------------

def create_checkout(user_id: str) -> dict:
    """Build the auto-submit form for a monthly recurring credit-card order.

    Returns {'action': <ECPay cashier URL>, 'params': {field: value}} for the
    frontend to POST as a hidden form (ECPay forbids iframes).
    """
    amount = _period_amount()
    backend = _backend_public_url()
    # MerchantTradeNo: permanently unique, alphanumeric, ≤20 chars.
    trade_no = f"SUB{int(time.time())}{secrets.token_hex(3)}"[:20]
    params = {
        "MerchantID": _cfg("ECPAY_MERCHANT_ID"),
        "MerchantTradeNo": trade_no,
        "MerchantTradeDate": datetime.now(_TAIPEI).strftime("%Y/%m/%d %H:%M:%S"),
        "PaymentType": "aio",
        "TotalAmount": str(amount),
        "TradeDesc": "Portfolio tracking subscription",
        "ItemName": f"Monthly subscription NT${amount} x1",
        "ReturnURL": f"{backend}/api/billing/ecpay/return",
        "ChoosePayment": "Credit",
        "EncryptType": "1",
        "PeriodAmount": str(amount),  # must equal TotalAmount
        "PeriodType": _PERIOD_TYPE,
        "Frequency": str(_FREQUENCY),
        "ExecTimes": str(_EXEC_TIMES),
        "PeriodReturnURL": f"{backend}/api/billing/ecpay/period",
        "ClientBackURL": f"{_frontend_base_url()}/?billing=return",
        # Echoed back on every callback (and covered by CheckMacValue): the
        # only attribution we need to map a callback to a user.
        "CustomField1": user_id,
    }
    params["CheckMacValue"] = generate_check_mac_value(params)
    return {"action": f"{_base_url()}/Cashier/AioCheckOut/V5", "params": params}


# --- Callbacks (source of truth) ----------------------------------------------

def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    return dt.replace(year=year, month=month,
                      day=min(dt.day, calendar.monthrange(year, month)[1]))


def _period_end_iso(auth_date: str) -> str:
    """Next charge date (UTC ISO) computed from an ECPay UTC+8 timestamp."""
    try:
        authorized = datetime.strptime(auth_date, "%Y/%m/%d %H:%M:%S").replace(tzinfo=_TAIPEI)
    except ValueError:
        authorized = datetime.now(_TAIPEI)
    return _add_months(authorized, _FREQUENCY).astimezone(timezone.utc).isoformat()


def handle_first_auth(form: dict) -> None:
    """Apply the first-authorization result (ReturnURL callback).

    Raises ValueError on a bad CheckMacValue; the router turns that into a 400.
    A failed first auth never enters ECPay's schedule, so we write nothing.
    """
    if not verify_check_mac_value(form):
        logger.warning("CMV debug — form=%r received=%s calculated=%s",
                       form, form.get("CheckMacValue"), generate_check_mac_value(form))
        raise ValueError("checkmacvalue_mismatch")
    user_id = form.get("CustomField1", "")
    if not user_id:
        logger.warning("ecpay return callback without CustomField1: %s",
                       form.get("MerchantTradeNo"))
        return
    if str(form.get("SimulatePaid", "0")) == "1":
        logger.info("ecpay simulated payment ignored: %s", form.get("MerchantTradeNo"))
        return
    if str(form.get("RtnCode")) != "1":
        logger.warning("ecpay first auth failed for %s: %s %s",
                       form.get("MerchantTradeNo"), form.get("RtnCode"), form.get("RtnMsg"))
        return
    _upsert(user_id, form["MerchantTradeNo"], "active",
            _period_end_iso(form.get("PaymentDate", "")))


def handle_period(form: dict) -> None:
    """Apply a recurring-charge result (PeriodReturnURL callback, 2nd period on)."""
    if not verify_check_mac_value(form):
        raise ValueError("checkmacvalue_mismatch")
    user_id = form.get("CustomField1", "")
    if not user_id:
        logger.warning("ecpay period callback without CustomField1: %s",
                       form.get("MerchantTradeNo"))
        return
    if str(form.get("SimulatePaid", "0")) == "1":
        logger.info("ecpay simulated period payment ignored: %s", form.get("MerchantTradeNo"))
        return
    if str(form.get("RtnCode")) == "1":
        _upsert(user_id, form["MerchantTradeNo"], "active",
                _period_end_iso(form.get("ProcessDate", "")))
    else:
        # Charge failed. ECPay retries by itself and auto-terminates after 6
        # consecutive failures; past_due (inactive) until a retry succeeds.
        logger.warning("ecpay period charge failed for %s: %s %s",
                       form.get("MerchantTradeNo"), form.get("RtnCode"), form.get("RtnMsg"))
        execute(
            """UPDATE subscriptions SET status = 'past_due', updated_at = %s
                WHERE user_id = %s AND provider = 'ecpay'""",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )


def _upsert(user_id: str, trade_no: str, status: str, period_end: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    execute(
        """
        INSERT INTO subscriptions
            (id, user_id, provider, external_id, status, current_period_end,
             cancel_at_period_end, created_at, updated_at)
        VALUES (%s, %s, 'ecpay', %s, %s, %s, FALSE, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            provider             = 'ecpay',
            external_id          = EXCLUDED.external_id,
            status               = EXCLUDED.status,
            current_period_end   = EXCLUDED.current_period_end,
            cancel_at_period_end = FALSE,
            updated_at           = EXCLUDED.updated_at
        """,
        (str(uuid.uuid4()), user_id, trade_no, status, period_end, now, now),
    )


# --- Cancel -------------------------------------------------------------------

def cancel(user_id: str) -> None:
    """Terminate future charges via CreditCardPeriodAction (irreversible).

    The current paid period stays usable: status remains 'active' with
    cancel_at_period_end set, and the entitlement lapses naturally when
    current_period_end passes.
    """
    row = fetch_one(
        """SELECT external_id FROM subscriptions
            WHERE user_id = %s AND provider = 'ecpay'""",
        (user_id,),
    )
    if not row or not row["external_id"]:
        raise LookupError("no_ecpay_subscription")

    params = {
        "MerchantID": _cfg("ECPAY_MERCHANT_ID"),
        "MerchantTradeNo": row["external_id"],
        "Action": "Cancel",
        "TimeStamp": str(int(time.time())),
    }
    params["CheckMacValue"] = generate_check_mac_value(params)
    resp = requests.post(f"{_base_url()}/Cashier/CreditCardPeriodAction",
                         data=params, timeout=15)
    resp.raise_for_status()
    result = dict(urllib.parse.parse_qsl(resp.text))
    if not verify_check_mac_value(result):
        raise RuntimeError("ecpay_response_checkmacvalue_mismatch")
    # 90100149 = already disabled — treat as canceled rather than erroring.
    if str(result.get("RtnCode")) not in ("1", "90100149"):
        raise RuntimeError(result.get("RtnMsg", "cancel_failed"))
    execute(
        """UPDATE subscriptions SET cancel_at_period_end = TRUE, updated_at = %s
            WHERE user_id = %s AND provider = 'ecpay'""",
        (datetime.now(timezone.utc).isoformat(), user_id),
    )

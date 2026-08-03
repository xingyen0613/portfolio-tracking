"""
Internal endpoints for Cloud Scheduler to trigger batch jobs.
Auth: X-Scheduler-Secret header must match SCHEDULER_SECRET env var.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from config.settings import ENABLED_PLATFORMS, SCHEDULER_SECRET

router = APIRouter()
log = logging.getLogger(__name__)

_DAILY_PLATFORMS = {"binance", "okx", "mexc", "bybit", "sol_wallet", "sui_wallet", "ibkr", "evm_wallet", "hyperliquid", "sinopac", "fubon"}


class TriggerRequest(BaseModel):
    job: Literal["daily", "monthly_yuanta", "smoke"]


def _verify_secret(x_scheduler_secret: str | None) -> None:
    if not SCHEDULER_SECRET:
        raise HTTPException(status_code=503, detail="SCHEDULER_SECRET not configured")
    if x_scheduler_secret != SCHEDULER_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


@router.post("/trigger-batch")
def trigger_batch(
    body: TriggerRequest,
    x_scheduler_secret: str | None = Header(default=None),
):
    _verify_secret(x_scheduler_secret)

    from app.jobs.run_batch import _fetch_benchmarks, active_batch_user_ids, run_batch

    if body.job == "daily":
        # Realign ECPay subscriptions before gating, so a user whose payment
        # callback was missed gets their entitlement (and batch) back today.
        try:
            from app.services.ecpay_billing import reconcile_subscriptions
            log.info("billing reconcile: %s", reconcile_subscriptions())
        except Exception as e:
            log.error("billing reconcile failed: %s", e)

    user_ids = active_batch_user_ids()
    if not user_ids:
        log.warning("trigger-batch: no active users, skipping.")
        return {"status": "skipped", "reason": "no active users"}

    results = []

    batch_ids: list[str] = []

    if body.job == "daily":
        platforms = [p for p in ENABLED_PLATFORMS if p in _DAILY_PLATFORMS]
        log.info("Daily batch triggered for %d user(s)", len(user_ids))
        for user_id in user_ids:
            try:
                batch_id = run_batch(platforms, user_id)
                batch_ids.append(batch_id)
                results.append({"user_id": user_id, "batch_id": batch_id, "status": "ok"})
            except Exception as e:
                log.error("Daily batch failed for user %s: %s", user_id, e)
                results.append({"user_id": user_id, "status": f"error: {e}"})
        try:
            _fetch_benchmarks()
        except Exception as e:
            log.error("Benchmark fetch failed: %s", e)

    elif body.job == "monthly_yuanta":
        log.info("Monthly yuanta batch triggered for %d user(s)", len(user_ids))
        for user_id in user_ids:
            try:
                batch_id = run_batch(["yuanta"], user_id)
                batch_ids.append(batch_id)
                results.append({"user_id": user_id, "batch_id": batch_id, "status": "ok"})
            except Exception as e:
                log.error("Yuanta batch failed for user %s: %s", user_id, e)
                results.append({"user_id": user_id, "status": f"error: {e}"})

    elif body.job == "smoke":
        from config.settings import SYSTEM_OWNER_ID
        log.info("Smoke test triggered for system owner")
        try:
            batch_id = run_batch(["binance"], SYSTEM_OWNER_ID)
            batch_ids.append(batch_id)
            results.append({"user_id": SYSTEM_OWNER_ID, "batch_id": batch_id, "status": "ok"})
        except Exception as e:
            log.error("Smoke test failed: %s", e)
            results.append({"user_id": SYSTEM_OWNER_ID, "status": f"error: {e}"})

    try:
        from app.services.notifier import send_batch_summary
        send_batch_summary(body.job, batch_ids)
    except Exception as e:
        log.warning("notifier failed: %s", e)

    return {"status": "done", "job": body.job, "results": results}

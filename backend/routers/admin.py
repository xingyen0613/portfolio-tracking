from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.deps import get_current_user
from config.db import get_conn
from config.settings import ENABLED_PLATFORMS, SYSTEM_OWNER_ID

router = APIRouter()

_IMPLEMENTED = {
    "binance", "okx", "mexc", "bybit",
    "sui_wallet", "sol_wallet", "evm_wallet",
    "ibkr", "sinopac", "yuanta",
}


class AdminRunBatchRequest(BaseModel):
    platforms: list[str] | None = None  # None = 全部已實作平台
    user_id: str | None = None          # None = 所有 active 用戶
    skip_benchmarks: bool = False


class BatchResult(BaseModel):
    user_id: str
    batch_id: str
    status: str


class AdminRunBatchResponse(BaseModel):
    batches: list[BatchResult]
    benchmarks_updated: bool


def _active_user_ids() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM user_connectors WHERE status = 'active'"
        ).fetchall()
    return [row["user_id"] for row in rows]


@router.post("/run-batch", response_model=AdminRunBatchResponse)
def admin_run_batch(
    body: AdminRunBatchRequest,
    current_user: dict = Depends(get_current_user),
):
    if current_user["id"] != SYSTEM_OWNER_ID:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    from app.jobs.run_batch import _fetch_benchmarks, run_batch

    target_platforms = body.platforms or [p for p in ENABLED_PLATFORMS if p in _IMPLEMENTED]
    target_users = [body.user_id] if body.user_id else _active_user_ids()

    results: list[BatchResult] = []
    batch_ids: list[str] = []
    for uid in target_users:
        try:
            batch_id = run_batch(target_platforms, uid)
            batch_ids.append(batch_id)
            with get_conn() as conn:
                row = conn.execute(
                    "SELECT status FROM batches WHERE id = %s", (batch_id,)
                ).fetchone()
            batch_status = row["status"] if row else "unknown"
        except Exception as e:
            batch_id = ""
            batch_status = f"error: {e}"
        results.append(BatchResult(user_id=uid, batch_id=batch_id, status=batch_status))

    benchmarks_updated = False
    if not body.skip_benchmarks:
        try:
            _fetch_benchmarks()
            benchmarks_updated = True
        except Exception:
            benchmarks_updated = False

    try:
        from app.services.notifier import send_batch_summary
        send_batch_summary("admin", batch_ids)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("notifier failed: %s", e)

    return AdminRunBatchResponse(batches=results, benchmarks_updated=benchmarks_updated)

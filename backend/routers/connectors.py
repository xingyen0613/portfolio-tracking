"""User-managed connector CRUD."""
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.auth.encryption import encrypt
from config.db import get_conn

router = APIRouter()


# Platforms and their required credential fields.
PLATFORM_REQUIRED_FIELDS = {
    "binance": ["api_key", "secret"],
    "okx":     ["api_key", "secret", "passphrase"],
    "mexc":    ["api_key", "secret"],
    "bybit":   ["api_key", "secret"],
    "ibkr":    ["flex_token", "query_id"],
    "evm_wallet": ["api_key", "addresses"],
    "sol_wallet": ["api_key", "addresses"],
}

SUPPORTED_PLATFORMS = set(PLATFORM_REQUIRED_FIELDS.keys())


class ConnectorOut(BaseModel):
    id: str
    platform_name: str
    account_key: str
    account_label: str | None = None
    status: str
    last_sync_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None
    created_at: str | None = None


class ConnectorCreate(BaseModel):
    platform_name: str
    account_label: str = Field(..., min_length=1, max_length=64)
    credentials: dict


class ConnectorCreateResponse(BaseModel):
    connector: ConnectorOut
    fetch_status: str  # 'success' | 'partial' | 'failed'
    fetch_error: str | None = None
    batch_id: str | None = None


def _slugify(text: str) -> str:
    """Generate ASCII slug from a label. Falls back to 'account' if empty."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "account"


def _row_to_connector(row) -> ConnectorOut:
    return ConnectorOut(
        id=row["id"],
        platform_name=row["platform_name"],
        account_key=row["account_key"],
        account_label=row["label"],
        status=row["status"],
        last_sync_at=str(row["last_sync_at"]) if row["last_sync_at"] else None,
        last_error=row["last_error"],
        last_error_at=str(row["last_error_at"]) if row["last_error_at"] else None,
        created_at=str(row["created_at"]) if row["created_at"] else None,
    )


@router.get("", response_model=list[ConnectorOut])
def list_connectors(current_user: dict = Depends(get_current_user)):
    """Return all of the current user's connectors. Never returns credentials."""
    user_id = current_user["id"]
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, platform_name, account_key, label, status,
                      last_sync_at, last_error, last_error_at, created_at
               FROM user_connectors
               WHERE user_id=%s
               ORDER BY created_at""",
            (user_id,),
        ).fetchall()
    return [_row_to_connector(r) for r in rows]


@router.post("", response_model=ConnectorCreateResponse)
def create_connector(body: ConnectorCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    platform = body.platform_name

    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported platform: {platform}",
        )

    # Validate required fields
    missing = [f for f in PLATFORM_REQUIRED_FIELDS[platform]
               if not body.credentials.get(f)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {', '.join(missing)}",
        )

    account_key = _slugify(body.account_label)
    encrypted = encrypt(json.dumps(body.credentials))
    connector_id = str(uuid.uuid4())

    with get_conn() as conn:
        # Check for conflict
        existing = conn.execute(
            "SELECT id FROM user_connectors WHERE user_id=%s AND platform_name=%s AND account_key=%s",
            (user_id, platform, account_key),
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Connector with label '{body.account_label}' already exists for {platform}",
            )

        conn.execute(
            """INSERT INTO user_connectors
               (id, user_id, platform_name, account_key, label, credentials_json, status, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW())""",
            (connector_id, user_id, platform, account_key, body.account_label, encrypted),
        )

    # Immediate try-fetch for this single connector
    fetch_status = "success"
    fetch_error: str | None = None
    batch_id: str | None = None
    try:
        from app.jobs.run_batch import run_batch
        batch_id = run_batch([platform], user_id, connector_ids=[connector_id])

        # Read back batch status
        with get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM batches WHERE id=%s", (batch_id,)
            ).fetchone()
            if row:
                fetch_status = row["status"]
    except Exception as e:
        fetch_status = "failed"
        fetch_error = str(e)

    # Read back the connector row with updated last_sync/error fields
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, platform_name, account_key, label, status,
                      last_sync_at, last_error, last_error_at, created_at
               FROM user_connectors WHERE id=%s""",
            (connector_id,),
        ).fetchone()

    response = ConnectorCreateResponse(
        connector=_row_to_connector(row),
        fetch_status=fetch_status,
        fetch_error=fetch_error,
        batch_id=batch_id,
    )

    if fetch_status == "failed":
        # 502: credential saved but fetch failed
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=response.model_dump())

    return response


@router.delete("/{connector_id}")
def delete_connector(connector_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["id"]
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM user_connectors WHERE id=%s AND user_id=%s RETURNING id",
            (connector_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    return {"deleted": connector_id}


@router.post("/{connector_id}/refresh", response_model=ConnectorCreateResponse)
def refresh_connector(connector_id: str, current_user: dict = Depends(get_current_user)):
    """Manually trigger a re-fetch for a single connector."""
    user_id = current_user["id"]
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, platform_name, account_key, label, status,
                      last_sync_at, last_error, last_error_at, created_at
               FROM user_connectors WHERE id=%s AND user_id=%s""",
            (connector_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )

    platform = row["platform_name"]
    fetch_status = "success"
    fetch_error: str | None = None
    batch_id: str | None = None
    try:
        from app.jobs.run_batch import run_batch
        batch_id = run_batch([platform], user_id, connector_ids=[connector_id])
        with get_conn() as conn:
            brow = conn.execute(
                "SELECT status FROM batches WHERE id=%s", (batch_id,)
            ).fetchone()
            if brow:
                fetch_status = brow["status"]
    except Exception as e:
        fetch_status = "failed"
        fetch_error = str(e)

    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, platform_name, account_key, label, status,
                      last_sync_at, last_error, last_error_at, created_at
               FROM user_connectors WHERE id=%s""",
            (connector_id,),
        ).fetchone()

    return ConnectorCreateResponse(
        connector=_row_to_connector(row),
        fetch_status=fetch_status,
        fetch_error=fetch_error,
        batch_id=batch_id,
    )

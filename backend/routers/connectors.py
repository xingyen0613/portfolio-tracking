"""User-managed connector CRUD."""
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user
from app.auth.encryption import decrypt, encrypt
from config.db import get_conn

router = APIRouter()


# Platforms and their required credential fields.
PLATFORM_REQUIRED_FIELDS = {
    "binance": ["api_key", "secret"],
    "okx":     ["api_key", "secret", "passphrase"],
    "mexc":    ["api_key", "secret"],
    "bybit":   ["api_key", "secret"],
    "ibkr":    ["flex_token", "query_id"],
    # Alchemy API key is system-level (server ALCHEMY_API_KEY env), not per-user
    "evm_wallet": ["addresses"],
    "sol_wallet": ["addresses"],
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


EXCHANGE_LIKE_PLATFORMS = {"binance", "okx", "mexc", "bybit", "ibkr"}


def _resolve_account_ids(conn, platform: str, account_key: str, creds: dict, user_id: str) -> list[int]:
    """Find all `accounts.id` rows owned by this connector.

    Mapping rules differ per platform:
      - exchanges/IBKR: 1:1 by account_key
      - sol_wallet:     1:N by addresses (account_key = addr[:10])
      - evm_wallet:     1:N by addresses × chains (account_key = addr[:10] || '_' || short)
    """
    if platform in EXCHANGE_LIKE_PLATFORMS:
        rows = conn.execute(
            """SELECT a.id FROM accounts a
               JOIN platforms p ON a.platform_id = p.id
               WHERE p.name=%s AND a.account_key=%s AND a.user_id=%s""",
            (platform, account_key, user_id),
        ).fetchall()
        return [r["id"] for r in rows]

    addrs = creds.get("addresses") or []
    if platform == "sol_wallet":
        keys = [a[:10] if len(a) >= 10 else a for a in addrs]
        if not keys:
            return []
        rows = conn.execute(
            """SELECT a.id FROM accounts a
               JOIN platforms p ON a.platform_id = p.id
               WHERE p.name=%s AND a.user_id=%s AND a.account_key = ANY(%s)""",
            (platform, user_id, keys),
        ).fetchall()
        return [r["id"] for r in rows]

    if platform == "evm_wallet":
        # account_key = addr_lower[:10] || '_' || chain_short — match by prefix per addr
        prefixes = [f"{a.lower()[:10]}_%" for a in addrs if len(a) >= 10]
        if not prefixes:
            return []
        like_clause = " OR ".join(["a.account_key LIKE %s"] * len(prefixes))
        rows = conn.execute(
            f"""SELECT a.id FROM accounts a
                JOIN platforms p ON a.platform_id = p.id
                WHERE p.name='evm_wallet' AND a.user_id=%s AND ({like_clause})""",
            (user_id, *prefixes),
        ).fetchall()
        return [r["id"] for r in rows]

    return []


@router.delete("/{connector_id}")
def delete_connector(connector_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a connector and cascade-remove its historical data.

    Removed: user_connectors, accounts, source_runs, raw_payloads (DB row only),
             account_snapshots, normalized_holdings — for accounts owned by
             this connector only.
    Kept:    category_snapshots (user-level aggregate), batches (cross-platform),
             on-disk JSON files under data/raw/ (managed separately).
    """
    user_id = current_user["id"]

    with get_conn() as conn:
        row = conn.execute(
            """SELECT platform_name, account_key, credentials_json
               FROM user_connectors WHERE id=%s AND user_id=%s""",
            (connector_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connector not found",
            )

        creds: dict = {}
        if row["credentials_json"]:
            try:
                creds = json.loads(decrypt(row["credentials_json"]))
            except Exception:
                creds = {}

        account_ids = _resolve_account_ids(
            conn, row["platform_name"], row["account_key"], creds, user_id,
        )

        cascaded = {"accounts": len(account_ids), "source_runs": 0,
                    "normalized_holdings": 0, "raw_payloads": 0,
                    "account_snapshots": 0}

        if account_ids:
            cascaded["normalized_holdings"] = conn.execute(
                """DELETE FROM normalized_holdings
                   WHERE source_run_id IN (
                       SELECT id FROM source_runs WHERE account_id = ANY(%s)
                   )""",
                (account_ids,),
            ).rowcount
            cascaded["raw_payloads"] = conn.execute(
                """DELETE FROM raw_payloads
                   WHERE source_run_id IN (
                       SELECT id FROM source_runs WHERE account_id = ANY(%s)
                   )""",
                (account_ids,),
            ).rowcount
            cascaded["account_snapshots"] = conn.execute(
                "DELETE FROM account_snapshots WHERE account_id = ANY(%s)",
                (account_ids,),
            ).rowcount
            cascaded["source_runs"] = conn.execute(
                "DELETE FROM source_runs WHERE account_id = ANY(%s)",
                (account_ids,),
            ).rowcount
            conn.execute("DELETE FROM accounts WHERE id = ANY(%s)", (account_ids,))

        conn.execute(
            "DELETE FROM user_connectors WHERE id=%s AND user_id=%s",
            (connector_id, user_id),
        )

    return {"deleted": connector_id, "cascaded": cascaded}


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

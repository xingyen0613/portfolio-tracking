"""
One-time script: read API keys from env vars, encrypt with Fernet,
write into user_connectors for SYSTEM_OWNER_ID.

Usage:
    uv run python scripts/populate_user_connectors.py
"""

import sys
import os
import json
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config.settings  # triggers load_dotenv
from config.db import get_conn
from app.auth.encryption import encrypt

SYSTEM_OWNER_ID = config.settings.SYSTEM_OWNER_ID

PLATFORMS = [
    {
        "platform_name": "binance",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("BINANCE_API_KEY", ""),
            "secret": os.environ.get("BINANCE_API_SECRET", ""),
        },
    },
    {
        "platform_name": "okx",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("OKX_API_KEY", ""),
            "secret": os.environ.get("OKX_API_SECRET", ""),
            "passphrase": os.environ.get("OKX_PASSPHRASE", ""),
        },
    },
    {
        "platform_name": "mexc",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("MEXC_API_KEY", ""),
            "secret": os.environ.get("MEXC_API_SECRET", ""),
        },
    },
    {
        "platform_name": "bybit",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("BYBIT_API_KEY", ""),
            "secret": os.environ.get("BYBIT_API_SECRET", ""),
        },
    },
    {
        "platform_name": "ibkr",
        "account_key": "account_main",
        "credentials": {
            "flex_token": os.environ.get("IBKR_FLEX_TOKEN", ""),
            "query_id": os.environ.get("IBKR_FLEX_QUERY_ID", ""),
        },
    },
    {
        "platform_name": "evm_wallet",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("ALCHEMY_API_KEY", ""),
        },
    },
    {
        "platform_name": "sol_wallet",
        "account_key": "account_main",
        "credentials": {
            "api_key": os.environ.get("ALCHEMY_API_KEY", ""),
        },
    },
]


def main():
    with get_conn() as conn:
        for p in PLATFORMS:
            creds = {k: v for k, v in p["credentials"].items() if v}
            if not creds:
                print(f"  [skip] {p['platform_name']} — no env vars set")
                continue

            encrypted = encrypt(json.dumps(creds))

            conn.execute(
                """INSERT INTO user_connectors
                   (id, user_id, platform_name, account_key, credentials_json, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, 'active', NOW())
                   ON CONFLICT (user_id, platform_name, account_key)
                   DO UPDATE SET credentials_json = EXCLUDED.credentials_json""",
                (str(uuid.uuid4()), SYSTEM_OWNER_ID,
                 p["platform_name"], p["account_key"], encrypted),
            )
            print(f"  [ok] {p['platform_name']} — {list(creds.keys())}")

    print("\nDone.")


if __name__ == "__main__":
    main()

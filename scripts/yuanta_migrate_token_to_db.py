"""One-time migration: copy .secrets/gmail_token.json into user_connectors (owner only).

Run once after Phase 1 deployment to move the existing Gmail OAuth token from
the local filesystem into the DB, enabling the new YuantaConnector.

Usage:
    uv run python scripts/yuanta_migrate_token_to_db.py
    uv run python scripts/yuanta_migrate_token_to_db.py --pdf-password <PASSWORD>
    uv run python scripts/yuanta_migrate_token_to_db.py --dry-run
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = PROJECT_ROOT / ".secrets"
TOKEN_FILE = SECRETS_DIR / "gmail_token.json"

sys.path.insert(0, str(PROJECT_ROOT))
import config.settings  # triggers load_dotenv
from config.db import get_conn
from config.settings import SYSTEM_OWNER_ID
from app.auth.encryption import encrypt


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Yuanta Gmail token to DB")
    parser.add_argument("--pdf-password", default="", help="Yuanta PDF password")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen")
    args = parser.parse_args()

    if not TOKEN_FILE.exists():
        print(f"ERROR: token file not found: {TOKEN_FILE}", file=sys.stderr)
        print("  Run: uv run python scripts/yuanta_gmail_poc.py --auth", file=sys.stderr)
        return 1

    token_json = TOKEN_FILE.read_text(encoding="utf-8")
    try:
        json.loads(token_json)  # validate JSON
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid token JSON: {e}", file=sys.stderr)
        return 1

    pdf_password = args.pdf_password or ""

    credentials = {
        "gmail_token_json": token_json,
        "pdf_password": pdf_password,
    }

    print(f"Token file : {TOKEN_FILE}")
    print(f"PDF password: {'(set)' if pdf_password else '(empty — can update later)'}")
    print(f"User ID    : {SYSTEM_OWNER_ID}")
    print(f"Platform   : yuanta")
    print(f"Account key: yuanta_main")

    if args.dry_run:
        print("\n[dry-run] No changes written.")
        return 0

    # Check if connector already exists
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM user_connectors WHERE user_id=%s AND platform_name=%s AND account_key=%s",
            (SYSTEM_OWNER_ID, "yuanta", "yuanta_main"),
        ).fetchone()

    if row:
        connector_id = row["id"]
        print(f"\nExisting connector {connector_id[:8]} found — updating credentials...")
        encrypted = encrypt(json.dumps(credentials))
        with get_conn() as conn:
            conn.execute(
                "UPDATE user_connectors SET credentials_json=%s, status='active' "
                "WHERE id=%s",
                (encrypted, connector_id),
            )
        print("Done — credentials updated.")
    else:
        connector_id = str(uuid.uuid4())
        print(f"\nNo existing connector — creating {connector_id[:8]}...")
        encrypted = encrypt(json.dumps(credentials))
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO user_connectors
                   (id, user_id, platform_name, account_key, label, credentials_json, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (connector_id, SYSTEM_OWNER_ID, "yuanta", "yuanta_main",
                 "元大證券", encrypted, "active"),
            )

        # Also ensure accounts row exists
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (platform_id, account_key, label, user_id)
                   SELECT id, %s, %s, %s FROM platforms WHERE name = 'yuanta'
                   ON CONFLICT (platform_id, account_key, user_id) DO NOTHING""",
                ("yuanta_main", "元大證券", SYSTEM_OWNER_ID),
            )
        print("Done — connector and account created.")

    print("\nNext step: run_batch([\"yuanta\"], SYSTEM_OWNER_ID) to process new months.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

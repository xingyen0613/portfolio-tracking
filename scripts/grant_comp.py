"""Grant / revoke a complimentary (免費白名單) subscription by email.

Usage:
    uv run python scripts/grant_comp.py grant  someone@example.com
    uv run python scripts/grant_comp.py revoke someone@example.com
    uv run python scripts/grant_comp.py status someone@example.com
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.entitlements import get_entitlement, grant_comp, revoke_comp, _user_id_by_email


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in {"grant", "revoke", "status"}:
        print(__doc__)
        return 1

    action, email = sys.argv[1], sys.argv[2]
    try:
        user_id = _user_id_by_email(email)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    if action == "grant":
        grant_comp(email)
        print(f"granted comp → {email}")
    elif action == "revoke":
        revoke_comp(email)
        print(f"revoked comp → {email}")

    print(f"{email} ({user_id}): {get_entitlement(user_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

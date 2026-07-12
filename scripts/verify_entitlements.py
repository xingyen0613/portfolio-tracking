"""Phase 1 verification for the entitlement layer.

Exercises all four scenarios end-to-end against the DB and prints the real dicts.
Mutates ONLY the test account xingyen02@gmail.com (grant then revoke). Leaves it
revoked at the end (re-run `grant` via scripts/grant_comp.py if it should stay comp).

    uv run python scripts/verify_entitlements.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.entitlements import get_entitlement, grant_comp, revoke_comp, _user_id_by_email

OWNER_EMAIL = "xingyen0613@gmail.com"   # is_system=TRUE
TEST_EMAIL = "xingyen02@gmail.com"      # non-system test account


def check(label: str, got: dict, want_active: bool, want_statuses: set[str]) -> bool:
    ok = got["active"] is want_active and got["status"] in want_statuses
    print(f"[{'PASS' if ok else 'FAIL'}] {label}: {got}")
    return ok


def main() -> int:
    owner_id = _user_id_by_email(OWNER_EMAIL)
    test_id = _user_id_by_email(TEST_EMAIL)

    # Make sure the test account starts without an active comp record.
    revoke_comp(TEST_EMAIL)

    results = []
    # 1) owner (is_system) → always active
    results.append(check("owner is_system", get_entitlement(owner_id), True, {"active"}))
    # 2) non-system user, no active subscription → inactive
    #    ('none' on a fresh table, 'canceled' on a re-run — both inactive)
    results.append(check("no active sub", get_entitlement(test_id), False, {"none", "canceled"}))
    # 3) after grant_comp → active / comp
    grant_comp(TEST_EMAIL)
    got = get_entitlement(test_id)
    results.append(check("after grant_comp", got, True, {"active"}) and got["provider"] == "comp")
    # 4) after revoke_comp → canceled / inactive
    revoke_comp(TEST_EMAIL)
    results.append(check("after revoke_comp", get_entitlement(test_id), False, {"canceled"}))

    ok = all(results)
    print("\n=> ALL PASS" if ok else "\n=> SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

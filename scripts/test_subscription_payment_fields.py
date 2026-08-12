"""Verify migration 018 + the _upsert payment-field logic against the real database.

Run:  uv run python scripts/test_subscription_payment_fields.py

Everything runs inside one transaction that is ALWAYS rolled back, so existing
production rows (notably the ECPay verification evidence on the test account)
are untouched — the script re-reads and compares every row afterwards to prove
it. The real module functions are exercised: `execute` is redirected to the
transaction's cursor instead of the autocommitting pool helper.
"""
import sys
from pathlib import Path

import psycopg2.extras

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.db import get_pool  # noqa: E402
import app.services.ecpay_billing as eb  # noqa: E402

conn = get_pool().getconn()
conn.autocommit = False


def tx_execute(sql, params=()):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    return cur


def q(sql, params=()):
    return tx_execute(sql, params).fetchall()


eb.execute = tx_execute  # real code path, transactional writes

failures = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


def row(uid):
    return q("""SELECT amount, last_payment_at, started_at, current_period_end,
                       external_id, status
                  FROM subscriptions WHERE user_id = %s""", (uid,))[0]


try:
    print("=== schema after migration 018 ===")
    cols = q("""SELECT column_name, data_type, is_nullable
                  FROM information_schema.columns
                 WHERE table_name = 'subscriptions'
                   AND column_name IN ('amount','last_payment_at','started_at')
                 ORDER BY column_name""")
    for c in cols:
        print(f"  {c['column_name']:<18} {c['data_type']:<10} nullable={c['is_nullable']}")
    check("three columns exist", len(cols), 3)

    print("\n=== existing rows (before) ===")
    before = q("""SELECT provider, status, amount, last_payment_at, started_at
                    FROM subscriptions ORDER BY provider""")
    for r in before:
        print(f"  provider={r['provider']:<6} status={r['status']:<8} "
              f"amount={r['amount']} last_payment_at={r['last_payment_at']} "
              f"started_at={r['started_at']}")

    uid = q("SELECT id FROM users LIMIT 1")[0]["id"]
    tx_execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))

    T1 = "2026-08-13T02:00:00+00:00"
    T2 = "2026-09-13T02:00:00+00:00"
    T3 = "2026-11-01T02:00:00+00:00"

    print("\n=== 1. first subscription (order A, NT$99) ===")
    eb._upsert(uid, "ORDER_A", "active", "2026-09-13T02:00:00+00:00", amount=99, paid_at=T1)
    r = row(uid)
    check("amount recorded", r["amount"], 99)
    check("last_payment_at recorded", r["last_payment_at"], T1)
    check("started_at recorded", r["started_at"], T1)

    print("\n=== 2. monthly renewal, same order A ===")
    eb._upsert(uid, "ORDER_A", "active", "2026-10-13T02:00:00+00:00", amount=99, paid_at=T2)
    r = row(uid)
    check("started_at UNCHANGED (same order)", r["started_at"], T1)
    check("last_payment_at advanced", r["last_payment_at"], T2)
    check("period end advanced", r["current_period_end"], "2026-10-13T02:00:00+00:00")

    print("\n=== 3. cancel then resubscribe at a new price (order B, NT$120) ===")
    eb._upsert(uid, "ORDER_B", "active", "2026-12-01T02:00:00+00:00", amount=120, paid_at=T3)
    r = row(uid)
    check("started_at RESET (new order)", r["started_at"], T3)
    check("amount is the new price", r["amount"], 120)
    check("external_id switched", r["external_id"], "ORDER_B")

    print("\n=== 4. callback omitting amount must not wipe the stored one ===")
    eb._upsert(uid, "ORDER_B", "active", "2027-01-01T02:00:00+00:00", amount=None, paid_at=None)
    r = row(uid)
    check("amount preserved", r["amount"], 120)
    check("last_payment_at preserved", r["last_payment_at"], T3)

    print("\n=== 5. end-to-end: real handle_first_auth with a signed payload ===")
    tx_execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
    form = {
        "MerchantID": "TEST", "MerchantTradeNo": "ORDER_C", "RtnCode": "1",
        "RtnMsg": "Succeeded", "TradeNo": "T123", "TotalAmount": "99",
        "PaymentDate": "2026/08/13 10:00:00", "PaymentType": "Credit_CreditCard",
        "CustomField1": uid,
    }
    form["CheckMacValue"] = eb.generate_check_mac_value(form)
    eb.handle_first_auth(form)
    r = row(uid)
    check("amount parsed from TotalAmount", r["amount"], 99)
    # 2026/08/13 10:00 UTC+8 == 02:00 UTC
    check("paid_at converted UTC+8 → UTC", r["last_payment_at"], "2026-08-13T02:00:00+00:00")
    check("started_at set on first auth", r["started_at"], "2026-08-13T02:00:00+00:00")
    check("period end = +1 month", r["current_period_end"], "2026-09-13T02:00:00+00:00")

finally:
    conn.rollback()
    print("\n>>> transaction ROLLED BACK")

after = q("""SELECT provider, status, amount, last_payment_at, started_at
               FROM subscriptions ORDER BY provider""")
print("\n=== rows after rollback (must match 'before') ===")
for r in after:
    print(f"  provider={r['provider']:<6} status={r['status']:<8} "
          f"amount={r['amount']} last_payment_at={r['last_payment_at']} "
          f"started_at={r['started_at']}")
check("row count unchanged", len(after), len(before))
check("no row mutated", after, before)
conn.rollback()

print("\n" + ("ALL CHECKS PASSED" if not failures else f"FAILURES: {failures}"))
sys.exit(1 if failures else 0)

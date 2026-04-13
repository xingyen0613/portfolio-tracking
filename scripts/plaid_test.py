"""
Test script to fetch and display investment holdings from Plaid.
Run: uv run python scripts/plaid_test.py
Requires: .env.plaid with PLAID_ACCESS_TOKEN set (run plaid_link.py first)
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

import plaid
from plaid.api import plaid_api
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest

ENV_FILE = Path(__file__).parent.parent / ".env.plaid"
load_dotenv(ENV_FILE)

PLAID_CLIENT_ID = os.environ.get("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.environ.get("PLAID_SECRET", "")
PLAID_ENV = os.environ.get("PLAID_ENV", "sandbox")
PLAID_ACCESS_TOKEN = os.environ.get("PLAID_ACCESS_TOKEN", "")

ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": "https://development.plaid.com",
    "production": plaid.Environment.Production,
}

config = plaid.Configuration(
    host=ENV_MAP.get(PLAID_ENV, plaid.Environment.Sandbox),
    api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
)
api_client = plaid.ApiClient(config)
client = plaid_api.PlaidApi(api_client)


def main():
    if not PLAID_ACCESS_TOKEN:
        print("Error: PLAID_ACCESS_TOKEN not found in .env.plaid")
        print("Run plaid_link.py first to authorize and obtain the token.")
        raise SystemExit(1)

    print(f"Environment: {PLAID_ENV}")
    print(f"Fetching holdings...\n")

    try:
        req = InvestmentsHoldingsGetRequest(access_token=PLAID_ACCESS_TOKEN)
        response = client.investments_holdings_get(req)
    except plaid.ApiException as e:
        body = json.loads(e.body)
        print(f"Plaid API Error: {body.get('error_message', str(e))}")
        raise SystemExit(1)

    # Build security lookup
    securities = {s.security_id: s for s in response.securities}

    # Print accounts
    print("=" * 70)
    print("ACCOUNTS")
    print("=" * 70)
    for acct in response.accounts:
        bal = acct.balances
        print(f"  {acct.name or acct.official_name or 'N/A'}")
        print(f"    Type: {acct.type} / {acct.subtype}")
        print(f"    Current: ${bal.current:,.2f}" if bal.current else "    Current: N/A")
        print()

    # Print holdings
    print("=" * 70)
    print("HOLDINGS")
    print("=" * 70)
    print(f"  {'Ticker':<10} {'Name':<30} {'Qty':>10} {'Price':>12} {'Value':>12} {'Type':<12}")
    print(f"  {'-'*10} {'-'*30} {'-'*10} {'-'*12} {'-'*12} {'-'*12}")

    for h in sorted(response.holdings, key=lambda x: x.institution_value or 0, reverse=True):
        sec = securities.get(h.security_id)
        ticker = sec.ticker_symbol or "—" if sec else "—"
        name = (sec.name or "—")[:30] if sec else "—"
        sec_type = sec.type or "—" if sec else "—"
        qty = h.quantity or 0
        price = h.institution_price or 0
        value = h.institution_value or 0

        print(f"  {ticker:<10} {name:<30} {qty:>10.4f} {price:>11.2f} ${value:>11,.2f} {sec_type:<12}")

    print()
    print(f"  Total holdings: {len(response.holdings)}")

    # Dump raw JSON for inspection
    raw_path = Path(__file__).parent.parent / "data" / "raw" / "plaid_holdings_raw.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_data = response.to_dict()
    with open(raw_path, "w") as f:
        json.dump(raw_data, f, indent=2, default=str)
    print(f"  Raw response saved to: {raw_path}")


if __name__ == "__main__":
    main()

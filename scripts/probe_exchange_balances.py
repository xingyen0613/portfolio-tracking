"""
One-off probe: use SYSTEM_OWNER's stored credentials to query *every* relevant
sub-account on each exchange and report non-zero balances. Used to figure out
which sub-accounts our connectors need to cover.

Read-only — only calls balance / position endpoints.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings  # noqa: E402
from app.auth.encryption import decrypt  # noqa: E402
from config.db import get_conn  # noqa: E402
from config.settings import SYSTEM_OWNER_ID  # noqa: E402

import ccxt  # noqa: E402


def get_creds(platform: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT credentials_json FROM user_connectors WHERE user_id=%s AND platform_name=%s",
            (SYSTEM_OWNER_ID, platform),
        ).fetchone()
    return json.loads(decrypt(row["credentials_json"])) if row else {}


def show_nonzero(label: str, items: dict[str, float] | list, qty_key: str | None = None):
    """Print non-zero entries from a dict {symbol: qty} or list of dicts."""
    if isinstance(items, dict):
        nz = [(s, q) for s, q in items.items() if q and float(q) > 0]
    else:
        nz = []
        for it in items:
            if isinstance(it, dict):
                qty = float(it.get(qty_key, 0) or 0)
                if qty > 0:
                    sym = it.get("asset") or it.get("ccy") or it.get("coin") or it.get("symbol") or "?"
                    nz.append((sym, qty))
    if nz:
        print(f"  ✓ {label}: {len(nz)} 筆")
        for s, q in nz[:8]:
            print(f"     {s:10} {q}")
        if len(nz) > 8:
            print(f"     ...+{len(nz)-8} more")
    else:
        print(f"  · {label}: 空")


def probe_binance():
    print("\n=== BINANCE ===")
    creds = get_creds("binance")
    if not creds:
        print("  (no creds)")
        return
    ex = ccxt.binance({"apiKey": creds["api_key"], "secret": creds["secret"], "options": {"defaultType": "spot"}})

    # 1. 現貨 (spot wallet, excludes earn LD*)
    try:
        bal = ex.fetch_balance()
        spot = {k: v for k, v in bal.get("total", {}).items() if v and float(v) > 0 and not k.startswith("LD")}
        show_nonzero("現貨 (spot)", spot)
    except Exception as e:
        print(f"  ✗ 現貨: {e}")

    # 2. 槓桿 (cross margin)
    try:
        m = ex.sapiGetMarginAccount({})
        assets = m.get("userAssets", [])
        nz = {a["asset"]: float(a.get("netAsset", 0)) for a in assets if float(a.get("netAsset", 0)) != 0}
        show_nonzero("槓桿 (cross margin netAsset)", nz)
    except Exception as e:
        print(f"  ✗ 槓桿 cross: {e}")

    # 3. 槓桿 isolated
    try:
        m = ex.sapiGetMarginIsolatedAccount({})
        nz_pairs = []
        for asset in m.get("assets", []):
            tot = float(asset.get("baseAsset", {}).get("netAsset", 0)) + float(asset.get("quoteAsset", {}).get("netAsset", 0))
            if tot != 0:
                nz_pairs.append((asset.get("symbol", "?"), tot))
        if nz_pairs:
            print(f"  ✓ 槓桿 isolated: {len(nz_pairs)} 對")
            for s, q in nz_pairs[:5]: print(f"     {s} netAsset={q}")
        else:
            print("  · 槓桿 isolated: 空")
    except Exception as e:
        print(f"  ✗ 槓桿 isolated: {e}")

    # 4. U本位永續 (USD-M futures)
    try:
        f = ex.fapiPrivateV2GetAccount({})
        wb = float(f.get("totalWalletBalance", 0))
        upnl = float(f.get("totalUnrealizedProfit", 0))
        if wb or upnl:
            print(f"  ✓ U本位永續: wallet={wb} uPnL={upnl}")
            for a in f.get("assets", []):
                bal = float(a.get("walletBalance", 0))
                if bal: print(f"     {a['asset']:10} {bal}")
        else:
            print("  · U本位永續: 空")
    except Exception as e:
        print(f"  ✗ U本位永續: {e}")

    # 5. 幣本位永續 (Coin-M futures)
    try:
        f = ex.dapiPrivateGetAccount({})
        nz = []
        for a in f.get("assets", []):
            bal = float(a.get("walletBalance", 0))
            if bal: nz.append((a["asset"], bal))
        if nz:
            print(f"  ✓ 幣本位永續: {len(nz)} 筆")
            for s, q in nz: print(f"     {s} {q}")
        else:
            print("  · 幣本位永續: 空")
    except Exception as e:
        print(f"  ✗ 幣本位永續: {e}")

    # 6. 期權
    try:
        o = ex.eapiPrivateGetAccount({})
        bal = o.get("asset", [])
        nz = [(a["asset"], float(a.get("equity", 0))) for a in bal if float(a.get("equity", 0)) != 0]
        if nz:
            print(f"  ✓ 期權: {len(nz)} 筆")
            for s, q in nz: print(f"     {s} equity={q}")
        else:
            print("  · 期權: 空")
    except Exception as e:
        print(f"  ✗ 期權: {e}")

    # 7. 理財 (already in connector but verify)
    try:
        ef = ex.sapiGetSimpleEarnFlexiblePosition({"current": 1, "size": 100})
        rows = ef.get("rows", [])
        show_nonzero("理財 flexible", rows, "totalAmount")
    except Exception as e:
        print(f"  ✗ 理財 flex: {e}")

    try:
        el = ex.sapiGetSimpleEarnLockedPosition({"current": 1, "size": 100})
        show_nonzero("理財 locked", el.get("rows", []), "amount")
    except Exception as e:
        print(f"  ✗ 理財 locked: {e}")

    # 8. 資金 (funding wallet)
    try:
        f = ex.sapiPostAssetGetFundingAsset({})
        nz = []
        for a in f:
            qty = float(a.get("free", 0)) + float(a.get("locked", 0)) + float(a.get("freeze", 0))
            if qty > 0: nz.append((a["asset"], qty))
        if nz:
            print(f"  ✓ 資金 funding: {len(nz)} 筆")
            for s, q in nz: print(f"     {s} {q}")
        else:
            print("  · 資金 funding: 空")
    except Exception as e:
        print(f"  ✗ 資金 funding: {e}")


def probe_okx():
    print("\n=== OKX ===")
    creds = get_creds("okx")
    if not creds:
        print("  (no creds)")
        return
    ex = ccxt.okx({
        "apiKey": creds["api_key"], "secret": creds["secret"],
        "password": creds.get("passphrase", ""),
    })

    # 1. 交易 (trading account)
    try:
        bal = ex.fetch_balance()
        nz = {k: v for k, v in bal.get("total", {}).items() if v and float(v) > 0}
        show_nonzero("交易 (trading)", nz)
    except Exception as e:
        print(f"  ✗ 交易: {e}")

    # 2. 資金 (funding account)
    try:
        f = ex.privateGetAssetBalances({})
        rows = f.get("data", [])
        nz = []
        for r in rows:
            qty = float(r.get("bal", 0))
            if qty > 0: nz.append((r["ccy"], qty))
        if nz:
            print(f"  ✓ 資金 (funding): {len(nz)} 筆")
            for s, q in nz[:8]: print(f"     {s:8} {q}")
        else:
            print("  · 資金 (funding): 空")
    except Exception as e:
        print(f"  ✗ 資金: {e}")

    # 3. 金融 (savings)
    try:
        s = ex.privateGetFinanceSavingsBalance({})
        rows = s.get("data", [])
        nz = []
        for r in rows:
            qty = float(r.get("amt", 0)) + float(r.get("pendingAmt", 0))
            if qty > 0: nz.append((r["ccy"], qty))
        if nz:
            print(f"  ✓ 金融 (savings): {len(nz)} 筆")
            for s, q in nz[:8]: print(f"     {s:8} {q}")
        else:
            print("  · 金融 (savings): 空")
    except Exception as e:
        print(f"  ✗ 金融: {e}")


def probe_mexc():
    print("\n=== MEXC ===")
    creds = get_creds("mexc")
    if not creds:
        print("  (no creds)")
        return
    ex = ccxt.mexc({"apiKey": creds["api_key"], "secret": creds["secret"]})

    # 1. 現貨 (spot)
    try:
        bal = ex.fetch_balance()
        nz = {k: v for k, v in bal.get("total", {}).items() if v and float(v) > 0}
        show_nonzero("現貨 (spot)", nz)
    except Exception as e:
        print(f"  ✗ 現貨: {e}")

    # 2. 合約 (futures)
    try:
        bal = ex.fetch_balance({"type": "swap"})
        nz = {k: v for k, v in bal.get("total", {}).items() if v and float(v) > 0}
        show_nonzero("合約 (futures swap)", nz)
    except Exception as e:
        print(f"  ✗ 合約: {e}")

    # 3. 理財 — MEXC has Savings via private API (ccxt may not wrap it)
    try:
        # try MEXC savings/staking endpoints
        # GET /api/v3/savings/balance is not in CCXT, use sign-it-yourself or skip
        # Try ccxt's mexc endpoints
        if hasattr(ex, "spotPrivateGetMarginIsolatedSymbols"):
            print("  ? 理財：CCXT 沒有直接 wrapper，需手刻簽名")
        else:
            print("  ? 理財：未實作探測")
    except Exception as e:
        print(f"  ✗ 理財: {e}")


def probe_bybit():
    print("\n=== BYBIT ===")
    creds = get_creds("bybit")
    if not creds:
        print("  (no creds)")
        return
    ex = ccxt.bybit({"apiKey": creds["api_key"], "secret": creds["secret"]})

    # 1. UTA (Unified Trading Account — covers spot/derivatives)
    try:
        bal = ex.fetch_balance({"accountType": "UNIFIED"})
        nz = {k: v for k, v in bal.get("total", {}).items() if v and float(v) > 0}
        show_nonzero("UTA (spot+derivatives)", nz)
    except Exception as e:
        print(f"  ✗ UTA: {e}")

    # 2. Funding (資金帳戶)
    try:
        resp = ex.privateGetV5AssetTransferQueryAccountCoinsBalance({"accountType": "FUND"})
        rows = resp.get("result", {}).get("balance", [])
        nz = []
        for r in rows:
            qty = float(r.get("transferBalance", 0)) + float(r.get("walletBalance", 0))
            if qty > 0: nz.append((r["coin"], qty))
        if nz:
            print(f"  ✓ 資金 (funding): {len(nz)} 筆")
            for s, q in nz[:8]: print(f"     {s:8} {q}")
        else:
            print("  · 資金 (funding): 空")
    except Exception as e:
        print(f"  ✗ 資金: {e}")

    # 3. Earn (理財/質押)
    try:
        # Bybit Earn API: /v5/earn/position
        resp = ex.privateGetV5EarnPosition({"category": "FlexibleSaving"})
        rows = resp.get("result", {}).get("list", []) or []
        nz = []
        for r in rows:
            qty = float(r.get("amount", 0))
            if qty > 0: nz.append((r.get("coin", "?"), qty))
        if nz:
            print(f"  ✓ Earn FlexibleSaving: {len(nz)} 筆")
            for s, q in nz: print(f"     {s} {q}")
        else:
            print("  · Earn FlexibleSaving: 空")
    except Exception as e:
        print(f"  ✗ Earn FlexibleSaving: {e}")

    # 4. Try OnChain Earn category
    for cat in ("OnChain", "OptionsBackup", "Liquidity"):
        try:
            resp = ex.privateGetV5EarnPosition({"category": cat})
            rows = resp.get("result", {}).get("list", []) or []
            nz = [(r.get("coin", "?"), float(r.get("amount", 0))) for r in rows if float(r.get("amount", 0)) > 0]
            if nz:
                print(f"  ✓ Earn {cat}: {len(nz)} 筆")
                for s, q in nz: print(f"     {s} {q}")
        except Exception as e:
            pass  # endpoint may not exist


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target in ("all", "binance"):
        probe_binance()
    if target in ("all", "okx"):
        probe_okx()
    if target in ("all", "mexc"):
        probe_mexc()
    if target in ("all", "bybit"):
        probe_bybit()

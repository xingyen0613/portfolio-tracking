from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.dashboard.data import (
    get_holdings,
    get_latest_category_totals,
    get_yuanta_holdings_detail,
)
from app.utils.fx import get_latest_fx_rate
from config.settings import CATEGORY_LABEL

router = APIRouter()

ASSET_TYPE_LABEL = {
    "crypto":     "持幣",
    "stablecoin": "穩定幣",
    "stock":      "持股",
    "cash":       "現金",
    "spot":       "現貨",
    "earn":       "理財",
}

# resource_type → display label (more granular sub-account categories)
RESOURCE_TYPE_LABEL = {
    "spot":               "現貨",
    "earn_flexible":      "活期理財",
    "earn_locked":        "定期理財",
    "earn_flexiblesaving": "活期理財",
    "earn_onchain":       "鏈上 Earn",
    "savings":            "餘幣寶",
    "funding":            "資金帳戶",
    "margin_cross":       "槓桿",
    "futures_um":         "U本位永續",
    "futures_cm":         "幣本位永續",
    "futures":            "合約",
    "options":            "期權",
    "stock":              "持股",
    "cash":               "現金",
    "wallet":             "持幣",
}

# Display order — earlier entries appear first when sorting sections
RESOURCE_TYPE_ORDER = {
    "spot": 0, "wallet": 0, "stock": 0,
    "cash": 1,
    "savings": 2, "earn_flexible": 3, "earn_flexiblesaving": 3,
    "earn_locked": 4, "earn_onchain": 5,
    "funding": 6,
    "margin_cross": 7,
    "futures": 8, "futures_um": 8, "futures_cm": 9,
    "options": 10,
}

PLATFORM_META: dict[str, dict] = {
    "binance":    {"display": "Binance",           "abbr": "BN",  "color": "#F0B90B", "fg": "#000"},
    "okx":        {"display": "OKX",               "abbr": "OK",  "color": "#1a1a1a", "fg": "#fff"},
    "mexc":       {"display": "MEXC",              "abbr": "MX",  "color": "#0C94E4", "fg": "#fff"},
    "bybit":      {"display": "Bybit",             "abbr": "BY",  "color": "#F7A600", "fg": "#000"},
    "sui_wallet": {"display": "SUI Wallet",        "abbr": "SUI", "color": "#6fbcf0", "fg": "#000"},
    "sol_wallet": {"display": "Solana Wallet",     "abbr": "SOL", "color": "#9945FF", "fg": "#fff"},
    "evm_wallet": {"display": "EVM Wallet",        "abbr": "EVM", "color": "#627eea", "fg": "#fff"},
    "ibkr":       {"display": "IBKR（美股）",       "abbr": "IB",  "color": "#c0392b", "fg": "#fff"},
    "firsttrade": {"display": "Firsttrade（美股）", "abbr": "FT",  "color": "#2c8af8", "fg": "#fff"},
    "yuanta":     {"display": "元大證券（台股）",   "abbr": "元",  "color": "#27ae60", "fg": "#fff"},
}

CATEGORY_ORDER = {"crypto": 0, "us_stock": 1, "tw_stock": 2}

# Platforms where holdings should be grouped by wallet address
WALLET_PLATFORMS = {"sui_wallet", "sol_wallet", "evm_wallet"}


def _fmt_qty(q: float, decimals: int = 4) -> str:
    if q == 0:
        return "—"
    if q >= 1000:
        return f"{q:,.0f}"
    text = f"{q:.{decimals}f}".rstrip("0").rstrip(".")
    return text


def _fmt_price(p: float | None, currency: str = "USD") -> str:
    if p is None or p == 0:
        return "—"
    if currency == "TWD":
        return f"NT${p:,.1f}"
    return f"${p:,.2f}"


@router.get("")
def get_all_holdings(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    user_id = current_user["id"]
    df = get_holdings(user_id)
    cat_df = get_latest_category_totals(user_id)

    # ── Summary stat cards ────────────────────────────────────────────────────
    total = float(cat_df["value_usd"].sum())
    summary: dict[str, float] = {"total_usd": round(total, 2)}
    for _, row in cat_df.iterrows():
        summary[f"{row['category']}_usd"] = round(float(row["value_usd"]), 2)

    # ── Platforms from normalized_holdings ────────────────────────────────────
    platforms: list[dict] = []

    for platform_name, pf_df in df.groupby("platform"):
        platform_name = str(platform_name)
        meta = PLATFORM_META.get(platform_name, {
            "display": platform_name.title(),
            "abbr": platform_name[:2].upper(),
            "color": "#484f58",
            "fg": "#fff",
        })
        category = str(pf_df["category"].iloc[0])
        platform_total = float(pf_df["value_usd"].sum())

        def _build_sections(sub_df) -> list[dict]:
            """Group rows into sections by resource_type (spot / earn / futures
            etc.). Falls back to asset_type for legacy rows where
            resource_type is NULL (pre-migration 007 data).
            """
            # Use resource_type when present, fall back to asset_type for legacy rows
            sub_df = sub_df.copy()
            sub_df["section_key"] = sub_df["resource_type"].where(
                sub_df["resource_type"].notna() & (sub_df["resource_type"] != ""),
                sub_df["asset_type"],
            )

            sections = []
            for section_key, type_df in sub_df.groupby("section_key"):
                # Aggregate by symbol within each section
                agg = (
                    type_df.groupby("platform_symbol", dropna=False)
                    .agg(
                        platform_asset_name=("platform_asset_name", "first"),
                        quantity=("quantity", lambda s: pd.to_numeric(s, errors="coerce").sum()),
                        price=("price", lambda s: pd.to_numeric(s, errors="coerce").dropna().iloc[0] if pd.to_numeric(s, errors="coerce").notna().any() else None),
                        value_usd=("value_usd", "sum"),
                    )
                    .reset_index()
                    .sort_values("value_usd", ascending=False)
                )
                rows = []
                for _, row in agg.iterrows():
                    value_usd = round(float(row["value_usd"]), 2)
                    # Filter out dust (< $5)
                    if abs(value_usd) < 5:
                        continue
                    try:
                        qty = float(row["quantity"]) if row["quantity"] is not None else 0.0
                    except (ValueError, TypeError):
                        qty = 0.0
                    try:
                        price = float(row["price"]) if row["price"] is not None else None
                    except (ValueError, TypeError):
                        price = None
                    rows.append({
                        "symbol":    str(row["platform_symbol"] or "—"),
                        "name":      str(row["platform_asset_name"] or ""),
                        "quantity":  _fmt_qty(qty),
                        "price":     _fmt_price(price),
                        "value_usd": value_usd,
                    })
                if rows:
                    label = RESOURCE_TYPE_LABEL.get(
                        str(section_key),
                        ASSET_TYPE_LABEL.get(str(section_key), str(section_key)),
                    )
                    sections.append({
                        "label":     label,
                        "total_usd": round(sum(r["value_usd"] for r in rows), 2),
                        "rows":      rows,
                        "_order":    RESOURCE_TYPE_ORDER.get(str(section_key), 99),
                    })
            sections.sort(key=lambda s: (s["_order"], -abs(s["total_usd"])))
            for s in sections:
                s.pop("_order", None)
            return sections

        is_wallet = platform_name in WALLET_PLATFORMS
        unique_accounts = pf_df["account_key"].nunique()
        # Wallets always group by account (one address × chain per account).
        # Non-wallet platforms only split when the user actually has multiple
        # connectors on the same platform — single-account stays flat.
        needs_accounts = is_wallet or unique_accounts > 1

        if needs_accounts:
            accounts: list[dict] = []
            for account_key, acct_df in pf_df.groupby("account_key", sort=False):
                account_key = str(account_key)
                label = str(acct_df["account_label"].iloc[0] or account_key)

                # Wallet platforms derive a public address + chain for the badge.
                # Non-wallet platforms have no on-chain address — leave both null
                # and let the frontend fall back to displaying `label`.
                address_part: str | None = None
                chain_val = None
                if is_wallet:
                    chain_val = (
                        acct_df["chain"].dropna().iloc[0]
                        if "chain" in acct_df.columns and not acct_df["chain"].dropna().empty
                        else None
                    )
                    if platform_name == "evm_wallet":
                        # EVM label = "0xaddr... (chain)" — strip the suffix
                        address_part = label.split(" (")[0].strip()
                    else:
                        # SUI / SOL: label IS the full address
                        address_part = label

                acct_total = float(acct_df["value_usd"].sum())
                accounts.append({
                    "account_key": account_key,
                    "address":     address_part,
                    "chain":       chain_val,
                    "label":       label,
                    "total_usd":   round(acct_total, 2),
                    "sections":    _build_sections(acct_df),
                })
            accounts.sort(key=lambda a: -a["total_usd"])
            platforms.append({
                **meta,
                "name":      platform_name,
                "category":  category,
                "total_usd": round(platform_total, 2),
                "sections":  [],
                "accounts":  accounts,
            })
        else:
            sections = _build_sections(pf_df)
            platforms.append({
                **meta,
                "name":      platform_name,
                "category":  category,
                "total_usd": round(platform_total, 2),
                "sections":  sections,
            })

    # ── Yuanta: enrich with pledged + margin from parsed.json ─────────────────
    # Only show yuanta data to users who actually own a yuanta account in the DB
    # (currently only SYSTEM_OWNER, since yuanta_insert_poc.py writes under that user).
    # Without this guard, the JSON-based fallback would leak owner's data to any
    # logged-in user.
    from config.db import get_conn as _get_conn
    with _get_conn() as _conn:
        _row = _conn.execute(
            """SELECT 1 FROM accounts a
               JOIN platforms p ON a.platform_id = p.id
               WHERE p.name='yuanta' AND a.user_id=%s LIMIT 1""",
            (user_id,),
        ).fetchone()
    has_yuanta = _row is not None

    yuanta_detail = get_yuanta_holdings_detail() if has_yuanta else {}
    if yuanta_detail:
        fx = get_latest_fx_rate()
        net_asset_twd = float(yuanta_detail.get("net_asset") or 0)
        net_asset_usd = round(net_asset_twd / fx, 2)

        pledged_rows = []
        for h in yuanta_detail.get("pledged", []) or []:
            shares = h.get("shares_balance") or 0
            if shares <= 0:
                continue
            pledged_rows.append({
                "symbol":    h.get("symbol") or "—",
                "name":      h.get("name", ""),
                "quantity":  f"{int(shares):,} 股",
                "price":     "—",
                "value_usd": round(float(h.get("value_twd") or 0) / fx, 2),
            })

        margin_twd = float(yuanta_detail.get("margin_balance") or 0)
        margin_usd = round(-margin_twd / fx, 2) if margin_twd else 0
        margin_rows = [{
            "symbol":    "借款",
            "name":      "融資借款",
            "quantity":  "—",
            "price":     "—",
            "value_usd": margin_usd,
        }] if margin_twd else []

        # Other assets (futures equity etc.) from yuanta summary
        other_rows = []
        for oa in yuanta_detail.get("other_assets", []) or []:
            v = float(oa.get("value_twd") or 0)
            if v == 0:
                continue
            other_rows.append({
                "symbol":    oa.get("label", "—"),
                "name":      oa.get("label", ""),
                "quantity":  "—",
                "price":     "—",
                "value_usd": round(v / fx, 2),
            })

        existing_yuanta = next((p for p in platforms if p["name"] == "yuanta"), None)
        if existing_yuanta is not None:
            # Enrich the DB-derived yuanta entry with pledged + futures + margin sections
            if pledged_rows:
                existing_yuanta["sections"].append({
                    "label":     "擔保品",
                    "total_usd": round(sum(r["value_usd"] for r in pledged_rows), 2),
                    "rows":      pledged_rows,
                })
            if other_rows:
                existing_yuanta["sections"].append({
                    "label":     "期貨權益",
                    "total_usd": round(sum(r["value_usd"] for r in other_rows), 2),
                    "rows":      other_rows,
                })
            if margin_rows:
                existing_yuanta["sections"].append({
                    "label":     "融資負債",
                    "total_usd": margin_usd,
                    "rows":      margin_rows,
                })
            # Use parsed.json's net_asset as the platform total (covers owned + pledged + other − margin)
            existing_yuanta["total_usd"] = net_asset_usd
        else:
            # No DB rows — build the whole platform from JSON only
            owned_rows = [
                {
                    "symbol":    h["symbol"],
                    "name":      h.get("name", ""),
                    "quantity":  f"{h['shares']:,} 股",
                    "price":     "—",
                    "value_usd": round((h["value_twd"] or 0) / fx, 2),
                }
                for h in yuanta_detail.get("owned", []) if h.get("shares", 0) > 0
            ]
            sections = []
            if owned_rows:
                sections.append({
                    "label":     "自有持股",
                    "total_usd": round(sum(r["value_usd"] for r in owned_rows), 2),
                    "rows":      owned_rows,
                })
            if pledged_rows:
                sections.append({
                    "label":     "擔保品",
                    "total_usd": round(sum(r["value_usd"] for r in pledged_rows), 2),
                    "rows":      pledged_rows,
                })
            if margin_rows:
                sections.append({
                    "label":     "融資負債",
                    "total_usd": margin_usd,
                    "rows":      margin_rows,
                })

            platforms.append({
                **PLATFORM_META["yuanta"],
                "name":      "yuanta",
                "category":  "tw_stock",
                "total_usd": net_asset_usd,
                "sections":  sections,
            })

    # ── 過濾掉已歸零平台，排序 ────────────────────────────────────────────────
    platforms = [p for p in platforms if p["total_usd"] != 0]
    platforms.sort(key=lambda p: (
        CATEGORY_ORDER.get(p["category"], 9),
        -p["total_usd"],
    ))

    return {"summary": summary, "platforms": platforms}

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
            sections = []
            for asset_type, type_df in sub_df.groupby("asset_type"):
                # Aggregate by symbol within each asset_type. Connectors split a
                # holding across resource_types (spot / earn / funding ...) but
                # we don't surface that distinction; show one row per symbol.
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
                    sections.append({
                        "label":     ASSET_TYPE_LABEL.get(str(asset_type), str(asset_type)),
                        "total_usd": round(sum(r["value_usd"] for r in rows), 2),
                        "rows":      rows,
                    })
            sections.sort(key=lambda s: -abs(s["total_usd"]))
            return sections

        if platform_name in WALLET_PLATFORMS:
            # Group by account (each = one wallet address, or address+chain for EVM)
            accounts: list[dict] = []
            for account_key, acct_df in pf_df.groupby("account_key", sort=False):
                account_key = str(account_key)
                label = str(acct_df["account_label"].iloc[0] or account_key)
                chain_val = acct_df["chain"].dropna().iloc[0] if "chain" in acct_df.columns and not acct_df["chain"].dropna().empty else None
                # Full address from label:
                #   SUI label  = full address (e.g. "0x655b10ed73...")
                #   EVM label  = "0xaddr... (chain)" — strip the " (chain)" suffix
                if platform_name == "evm_wallet":
                    address_part = label.split(" (")[0].strip()
                else:
                    address_part = label  # SUI: label IS the full address
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
    yuanta_detail = get_yuanta_holdings_detail()
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

        existing_yuanta = next((p for p in platforms if p["name"] == "yuanta"), None)
        if existing_yuanta is not None:
            # Enrich the DB-derived yuanta entry with pledged + margin sections
            if pledged_rows:
                existing_yuanta["sections"].append({
                    "label":     "擔保品",
                    "total_usd": round(sum(r["value_usd"] for r in pledged_rows), 2),
                    "rows":      pledged_rows,
                })
            if margin_rows:
                existing_yuanta["sections"].append({
                    "label":     "融資負債",
                    "total_usd": margin_usd,
                    "rows":      margin_rows,
                })
            # Use parsed.json's net_asset as the platform total (covers owned + pledged − margin)
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

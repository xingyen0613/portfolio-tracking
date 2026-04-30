from typing import Any

from fastapi import APIRouter

from app.dashboard.data import (
    get_holdings,
    get_latest_category_totals,
    get_yuanta_holdings_detail,
)
from config.settings import CATEGORY_LABEL, TWD_PER_USD

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
    "ibkr":       {"display": "IBKR（美股）",       "abbr": "IB",  "color": "#c0392b", "fg": "#fff"},
    "firsttrade": {"display": "Firsttrade（美股）", "abbr": "FT",  "color": "#2c8af8", "fg": "#fff"},
    "yuanta":     {"display": "元大證券（台股）",   "abbr": "元",  "color": "#27ae60", "fg": "#fff"},
}

CATEGORY_ORDER = {"crypto": 0, "us_stock": 1, "tw_stock": 2}


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
def get_all_holdings() -> dict[str, Any]:
    df = get_holdings()
    cat_df = get_latest_category_totals()

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

        sections: list[dict] = []
        for asset_type, type_df in pf_df.groupby("asset_type"):
            type_df = type_df.sort_values("value_usd", ascending=False)
            rows = []
            for _, row in type_df.iterrows():
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
                    "value_usd": round(float(row["value_usd"]), 2),
                })

            sections.append({
                "label":     ASSET_TYPE_LABEL.get(str(asset_type), str(asset_type)),
                "total_usd": round(float(type_df["value_usd"].sum()), 2),
                "rows":      rows,
            })

        sections.sort(key=lambda s: -abs(s["total_usd"]))
        platforms.append({
            **meta,
            "name":      platform_name,
            "category":  category,
            "total_usd": round(platform_total, 2),
            "sections":  sections,
        })

    # ── Yuanta from JSON ──────────────────────────────────────────────────────
    yuanta_detail = get_yuanta_holdings_detail()
    if yuanta_detail and not any(p["name"] == "yuanta" for p in platforms):
        net_asset_twd  = float(yuanta_detail.get("net_asset") or 0)
        net_asset_usd  = round(net_asset_twd / TWD_PER_USD, 2)

        owned_rows = [
            {
                "symbol":    h["symbol"],
                "name":      h.get("name", ""),
                "quantity":  f"{h['shares']:,} 股",
                "price":     "—",
                "value_usd": round((h["value_twd"] or 0) / TWD_PER_USD, 2),
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

        margin_twd = float(yuanta_detail.get("margin_balance") or 0)
        if margin_twd != 0:
            sections.append({
                "label":     "融資餘額",
                "total_usd": round(-margin_twd / TWD_PER_USD, 2),
                "rows": [{
                    "symbol":    "借貸",
                    "name":      "融資借款",
                    "quantity":  "—",
                    "price":     "—",
                    "value_usd": round(-margin_twd / TWD_PER_USD, 2),
                }],
            })

        platforms.append({
            **PLATFORM_META["yuanta"],
            "name":      "yuanta",
            "category":  "tw_stock",
            "total_usd": net_asset_usd,
            "sections":  sections,
        })

    # ── Sort by category order → total_usd ───────────────────────────────────
    platforms.sort(key=lambda p: (
        CATEGORY_ORDER.get(p["category"], 9),
        -p["total_usd"],
    ))

    return {"summary": summary, "platforms": platforms}

"""
Portfolio Dashboard — Streamlit entry point.
Run: streamlit run app/dashboard/main.py --server.port 857
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.dashboard.data import (
    get_crypto_platform_daily,
    get_crypto_symbol_breakdown,
    get_holdings,
    get_latest_category_totals,
    get_latest_snapshot_date,
    get_platform_latest_account_snapshot,
    get_snapshot_history,
    get_tw_stock_platform_daily,
    get_tw_stock_symbol_breakdown,
    get_us_stock_platform_daily,
    get_us_stock_symbol_breakdown,
    get_yuanta_holdings_detail,
)
from app.dashboard.metrics import compute_metrics, filter_window
from config.settings import CATEGORY_LABEL, PLATFORM_CATEGORY, TWD_PER_USD

st.set_page_config(
    page_title="Portfolio",
    page_icon="📊",
    layout="wide",
)

# ── Load data ─────────────────────────────────────────────────────────────────

df = get_holdings()

if df.empty:
    st.error("No data found. Run the ingestion batch first.")
    st.stop()

snapshot_date = df["snapshot_date"].iloc[0]

# ── Header ────────────────────────────────────────────────────────────────────

cat_totals = get_latest_category_totals()
total_usd = cat_totals["value_usd"].sum() if not cat_totals.empty else df["value_usd"].sum()
total_twd = total_usd * TWD_PER_USD

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.title("📊 Portfolio")
    st.caption(f"快照日期：{snapshot_date}　｜　匯率：1 USD = {TWD_PER_USD} TWD（固定）")
with col2:
    st.metric("總資產（USD）", f"${total_usd:,.0f}")
with col3:
    st.metric("總資產（TWD）", f"NT${total_twd:,.0f}")

st.divider()

# ── Section 1: Hierarchical Holdings ─────────────────────────────────────────

st.subheader("資產明細")

PLATFORM_DISPLAY = {
    "binance": "Binance",
    "okx": "OKX",
    "mexc": "MEXC",
    "bybit": "Bybit",
    "sui_wallet": "SUI On-chain",
    "yuanta": "元大證券（台股）",
    "firsttrade": "FirstTrade（美股）",
    "ibkr": "IBKR（美股）",
}

RESOURCE_DISPLAY = {
    "spot": "現貨",
    "earn_flexible": "理財 — 活期",
    "earn_locked": "理財 — 定期",
    "savings": "理財",
    "tokens": "Token 餘額",
}


def _resource_label(rt: str) -> str:
    if rt in RESOURCE_DISPLAY:
        return RESOURCE_DISPLAY[rt]
    if rt.startswith("defi_"):
        return f"DeFi — {rt[5:].upper()}"
    return rt


def _fmt_qty(qty) -> str:
    if qty is None or qty != qty:
        return "—"
    if qty >= 1000:
        return f"{qty:,.2f}"
    if qty >= 1:
        return f"{qty:.4f}"
    return f"{qty:.6f}"


def _fmt_price(price) -> str:
    if price is None or price != price:
        return ""
    if price >= 1000:
        return f"@ ${price:,.2f}"
    if price >= 1:
        return f"@ ${price:.4f}"
    return f"@ ${price:.6f}"


def _fmt_val(val) -> str:
    if val is None or val != val:
        return "—"
    return f"${val:,.2f} USD"


def _display_holding(row, indent=True):
    val = row["value_usd"]
    # Skip holdings worth less than $1
    if val is None or val != val or val < 1:
        return

    sym = row["platform_symbol"]
    qty = row["quantity"]
    price = row["price"]

    c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
    with c1:
        st.markdown(f"`{sym}`")
    with c2:
        st.write(_fmt_qty(qty))
    with c3:
        st.write(_fmt_price(price))
    with c4:
        st.write(_fmt_val(val))


# Active platforms (those with data in this batch)
active_platforms = df["platform"].unique().tolist()
all_platforms = ["binance", "okx", "mexc", "bybit", "sui_wallet", "yuanta", "ibkr", "firsttrade"]

yuanta_detail = get_yuanta_holdings_detail()
platform_account_snapshots = get_platform_latest_account_snapshot()

for platform in all_platforms:
    display_name = PLATFORM_DISPLAY.get(platform, platform)

    # 若平台最新 account_snapshot 為 $0 且比 normalized_holdings 更新，顯示空持倉
    latest_snap = platform_account_snapshots.get(platform)
    if latest_snap and latest_snap["total_value"] == 0:
        holdings_latest = df[df["platform"] == platform]["snapshot_date"].max() if platform in df["platform"].values else None
        if holdings_latest is None or latest_snap["snapshot_date"] > str(holdings_latest):
            with st.expander(f"**{display_name}** — $0 USD　`{latest_snap['snapshot_date']}`", expanded=True):
                st.caption("目前無持倉。")
            continue

    # 元大：資料來自 JSON 檔案，不走 normalized_holdings
    if platform == "yuanta":
        if not yuanta_detail:
            with st.expander(f"▷ {display_name} — 尚未連接", expanded=False):
                st.caption("此平台尚未設定 connector。")
        else:
            net = yuanta_detail["net_asset"]
            usd = net / TWD_PER_USD
            date_label = yuanta_detail["date"]
            with st.expander(
                f"**{display_name}** — NT${net:,.0f}　`{date_label}`",
                expanded=True,
            ):
                # ── Summary ──────────────────────────────────────────────
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("持股市值", f"NT${yuanta_detail['market_value']:,.0f}")
                with c2:
                    margin = yuanta_detail["margin_balance"]
                    st.metric("融資餘額", f"NT${margin:,.0f}")
                with c3:
                    st.metric("淨資產", f"NT${net:,.0f}　≈ ${usd:,.0f} USD")

                # ── 自有持股 ──────────────────────────────────────────────
                owned = yuanta_detail["owned"]
                if owned:
                    st.markdown("**自有持股**")
                    hdr = st.columns([1, 2, 2, 2])
                    for col, label in zip(hdr, ["代碼", "名稱", "股數", "市值（TWD）"]):
                        col.caption(label)
                    for h in owned:
                        c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
                        with c1: st.markdown(f"`{h['symbol']}`")
                        with c2: st.write(h["name"])
                        with c3: st.write(f"{h['shares']:,} 股")
                        with c4: st.write(f"NT${h['value_twd']:,.0f}" if h["value_twd"] else "—")

                # ── 抵押品部位 ────────────────────────────────────────────
                pledged = yuanta_detail["pledged"]
                if pledged:
                    st.markdown("**抵押品部位**")
                    hdr = st.columns([1, 2, 2, 2, 2])
                    for col, label in zip(hdr, ["代碼", "名稱", "庫存股", "擔保使用", "剩餘可用"]):
                        col.caption(label)
                    for h in pledged:
                        c1, c2, c3, c4, c5 = st.columns([1, 2, 2, 2, 2])
                        with c1: st.markdown(f"`{h['symbol']}`")
                        with c2: st.write(h["name"])
                        with c3: st.write(f"{h['shares_balance']:,} 股")
                        with c4: st.write(f"{h['shares_used']:,} 股")
                        with c5: st.write(f"{h['shares_remaining']:,} 股")

                # ── 借貸部位 ──────────────────────────────────────────────
                if margin > 0:
                    st.markdown("**借貸部位（融資）**")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.metric("融資餘額", f"NT${margin:,.0f}")
                    pct = yuanta_detail.get("margin_maintenance_pct")
                    if pct:
                        with c2:
                            st.metric("維持率", f"{pct}%")
        continue

    if platform not in active_platforms:
        with st.expander(f"▷ {display_name} — 尚未連接", expanded=False):
            st.caption("此平台尚未設定 connector。")
        continue

    plat_df = df[df["platform"] == platform]
    plat_total = plat_df["value_usd"].sum()

    # Format fetch timestamp
    fetched_at_raw = plat_df["fetched_at"].iloc[0] if "fetched_at" in plat_df.columns else None
    if fetched_at_raw:
        try:
            import pandas as pd
            ts = pd.to_datetime(fetched_at_raw, utc=True).strftime("%m/%d %H:%M UTC")
            ts_label = f"　`{ts}`"
        except Exception:
            ts_label = ""
    else:
        ts_label = ""

    with st.expander(f"**{display_name}** — ${plat_total:,.0f} USD{ts_label}", expanded=True):

        if platform == "sui_wallet":
            # Group by account (wallet address)
            for account_key, acct_df in plat_df.groupby("account_key", sort=False):
                full_address = acct_df["account_label"].iloc[0] or account_key
                acct_total = acct_df["value_usd"].sum()
                with st.expander(f"🔑 `{full_address}` — ${acct_total:,.2f} USD", expanded=False):
                    # Tokens (value > $1)
                    tokens_df = acct_df[acct_df["source_run_id"].apply(
                        lambda _: True  # all token rows are already in df
                    )]
                    token_rows = acct_df[
                        acct_df["platform_symbol"].notna() &
                        (acct_df["value_usd"].fillna(0) > 1) &
                        ~acct_df["platform_asset_name"].str.contains("DeFi|defi", case=False, na=False)
                    ].sort_values("value_usd", ascending=False)

                    defi_rows = acct_df[
                        acct_df["platform_asset_name"].str.contains(r"\(", na=False)
                    ]

                    if not token_rows.empty:
                        st.markdown("**Token 餘額**（> $1）")
                        for _, row in token_rows.iterrows():
                            _display_holding(row)

                    if not defi_rows.empty:
                        st.markdown("**DeFi 倉位**")
                        for _, row in defi_rows.iterrows():
                            sym = row["platform_symbol"]
                            name = row["platform_asset_name"]
                            qty = row["quantity"]
                            val = row["value_usd"]
                            c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
                            with c1:
                                st.markdown(f"`{sym}`")
                            with c2:
                                st.write(_fmt_qty(qty))
                            with c3:
                                st.caption(name or "")
                            with c4:
                                st.write(_fmt_val(val) if (val and val == val) else "—")
        elif platform == "ibkr":
            # IBKR: stocks + cash (cash may be negative for margin)
            stock_df = plat_df[plat_df["asset_type"] == "stock"].sort_values("value_usd", ascending=False)
            cash_df = plat_df[plat_df["asset_type"] == "cash"]

            if not stock_df.empty:
                st.markdown("**持股**")
                hdr = st.columns([1, 3, 2, 2, 2])
                for col, label in zip(hdr, ["代碼", "名稱", "股數", "價格", "市值（USD）"]):
                    col.caption(label)
                for _, row in stock_df.iterrows():
                    c1, c2, c3, c4, c5 = st.columns([1, 3, 2, 2, 2])
                    with c1: st.markdown(f"`{row['platform_symbol']}`")
                    with c2: st.write(row["platform_asset_name"] or "")
                    with c3: st.write(f"{row['quantity']:,.4f}".rstrip("0").rstrip(".") + " 股")
                    with c4: st.write(f"${row['price']:,.2f}")
                    with c5: st.write(f"${row['value_usd']:,.2f}")

            if not cash_df.empty:
                st.markdown("**現金**")
                for _, row in cash_df.iterrows():
                    cash_val = row["value_usd"]
                    color = "red" if cash_val < 0 else "green"
                    st.markdown(
                        f"`USD` — <span style='color:{color}'>${cash_val:,.2f}</span>",
                        unsafe_allow_html=True,
                    )

        else:
            # CEX: split into 現貨 and 理財, show 現貨 first

            def _is_earn(name: str) -> bool:
                if not name:
                    return False
                return any(kw in name for kw in ("(Savings)", "(Locked)", "(Funding)", "Earn"))

            spot_df = plat_df[~plat_df["platform_asset_name"].apply(_is_earn)]
            earn_df = plat_df[plat_df["platform_asset_name"].apply(_is_earn)]

            for section_label, section_df in [("現貨", spot_df), ("理財", earn_df)]:
                section_df = section_df[section_df["value_usd"].fillna(0) >= 1]
                if section_df.empty:
                    continue
                section_total = section_df["value_usd"].sum()
                st.markdown(f"**{section_label}** — ${section_total:,.2f} USD")
                for _, row in section_df.sort_values("value_usd", ascending=False).iterrows():
                    _display_holding(row)

st.divider()

# ── Section 2: Pie Chart ──────────────────────────────────────────────────────

st.subheader("資產配置")

# Use category_snapshots latest values so tw_stock/us_stock appear even without connectors
cat_df = get_latest_category_totals()
cat_df["label"] = cat_df["category"].map(CATEGORY_LABEL).fillna(cat_df["category"])

# Build hover text: top 5 tokens per category (crypto only, from normalized_holdings)
token_by_cat = (
    df[df["value_usd"] > 0]
    .groupby(["category", "platform_symbol"])["value_usd"]
    .sum()
    .reset_index()
)


def _top5_hover(cat: str) -> str:
    sub = token_by_cat[token_by_cat["category"] == cat].nlargest(5, "value_usd")
    if sub.empty:
        return ""
    total = sub["value_usd"].sum()
    lines = []
    for _, r in sub.iterrows():
        pct = r["value_usd"] / total * 100 if total > 0 else 0
        lines.append(f"{r['platform_symbol']}: ${r['value_usd']:,.0f} ({pct:.1f}%)")
    return "<br>".join(lines)


cat_df["hover"] = cat_df["category"].apply(_top5_hover)

fig_pie = go.Figure(go.Pie(
    labels=cat_df["label"],
    values=cat_df["value_usd"],
    customdata=cat_df["hover"],
    hovertemplate="<b>%{label}</b><br>$%{value:,.0f} USD (%{percent})<br><br>%{customdata}<extra></extra>",
    textinfo="label+percent",
    hole=0.35,
))
fig_pie.update_layout(height=400, margin=dict(t=20, b=20))

st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ── Section 3: Time Series Chart ─────────────────────────────────────────────

st.subheader("資產走勢")

history_df = get_snapshot_history()

if history_df.empty or history_df["snapshot_date"].nunique() < 2:
    st.info("歷史資料不足（需要至少 2 天的快照）。請等待每日 batch 累積資料。")
else:
    mode = st.radio("顯示模式", ["絕對數值 (USD)", "報酬率 (%)"], horizontal=True)
    window = st.radio(
        "時間窗口",
        ["1W", "1M", "1Q", "1Y", "2Y", "4Y", "自訂"],
        index=1,
        horizontal=True,
    )

    custom_start = custom_end = None
    if window == "自訂":
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            custom_start = st.date_input(
                "開始日期",
                value=(pd.Timestamp.today() - pd.Timedelta(days=180)).date(),
            )
        with col_d2:
            custom_end = st.date_input("結束日期", value=pd.Timestamp.today().date())

    # category_snapshots is already aggregated; just ffill per-category and filter to window.
    cat_daily = history_df[["snapshot_date", "category", "value_usd"]].copy()

    if not cat_daily.empty:
        date_range = pd.date_range(cat_daily["snapshot_date"].min(), cat_daily["snapshot_date"].max(), freq="D")
        categories = cat_daily["category"].unique()
        full_idx = pd.MultiIndex.from_product([date_range, categories], names=["snapshot_date", "category"])
        cat_daily = (
            cat_daily
            .set_index(["snapshot_date", "category"])
            .reindex(full_idx)
            .groupby(level="category")["value_usd"]
            .ffill()
            .reset_index()
        )
        cat_daily = filter_window(cat_daily, "snapshot_date", window, custom_start, custom_end)

        daily_total = cat_daily.groupby("snapshot_date")["value_usd"].sum().reset_index()
        daily_total["category"] = "total"
        all_daily = pd.concat([cat_daily, daily_total], ignore_index=True)
    else:
        all_daily = pd.DataFrame(columns=["snapshot_date", "category", "value_usd"])

    # Per-platform daily for hover source breakdown (independent of category_snapshots)
    crypto_plat_raw = get_crypto_platform_daily()
    if not crypto_plat_raw.empty:
        date_range_p = pd.date_range(
            crypto_plat_raw["snapshot_date"].min(), crypto_plat_raw["snapshot_date"].max(), freq="D"
        )
        plats = crypto_plat_raw["platform"].unique()
        full_idx_p = pd.MultiIndex.from_product([date_range_p, plats], names=["snapshot_date", "platform"])
        crypto_plat_daily = (
            crypto_plat_raw
            .set_index(["snapshot_date", "platform"])
            .reindex(full_idx_p)
            .groupby(level="platform")["value_usd"]
            .ffill()
            .reset_index()
        )
        crypto_plat_daily = filter_window(crypto_plat_daily, "snapshot_date", window, custom_start, custom_end)
    else:
        crypto_plat_daily = pd.DataFrame()

    # Token breakdown by individual symbol (independent source: normalized_holdings)
    crypto_symbol_df = get_crypto_symbol_breakdown()
    if not crypto_symbol_df.empty:
        crypto_symbol_df = filter_window(crypto_symbol_df, "snapshot_date", window, custom_start, custom_end)

    # Per-platform daily for us_stock hover breakdown
    us_plat_raw = get_us_stock_platform_daily()
    if not us_plat_raw.empty:
        date_range_us = pd.date_range(
            us_plat_raw["snapshot_date"].min(), us_plat_raw["snapshot_date"].max(), freq="D"
        )
        us_plats = us_plat_raw["platform"].unique()
        full_idx_us = pd.MultiIndex.from_product(
            [date_range_us, us_plats], names=["snapshot_date", "platform"]
        )
        us_plat_daily = (
            us_plat_raw
            .set_index(["snapshot_date", "platform"])
            .reindex(full_idx_us)
            .groupby(level="platform")["value_usd"]
            .ffill()
            .reset_index()
        )
        us_plat_daily = filter_window(us_plat_daily, "snapshot_date", window, custom_start, custom_end)
    else:
        us_plat_daily = pd.DataFrame()

    us_symbol_df = get_us_stock_symbol_breakdown()
    if not us_symbol_df.empty:
        us_symbol_df = filter_window(us_symbol_df, "snapshot_date", window, custom_start, custom_end)

    # Per-platform daily for tw_stock hover breakdown
    tw_plat_raw = get_tw_stock_platform_daily()
    if not tw_plat_raw.empty:
        date_range_tw = pd.date_range(
            tw_plat_raw["snapshot_date"].min(), tw_plat_raw["snapshot_date"].max(), freq="D"
        )
        tw_plats = tw_plat_raw["platform"].unique()
        full_idx_tw = pd.MultiIndex.from_product(
            [date_range_tw, tw_plats], names=["snapshot_date", "platform"]
        )
        tw_plat_daily = (
            tw_plat_raw
            .set_index(["snapshot_date", "platform"])
            .reindex(full_idx_tw)
            .groupby(level="platform")["value_usd"]
            .ffill()
            .reset_index()
        )
        tw_plat_daily = filter_window(tw_plat_daily, "snapshot_date", window, custom_start, custom_end)
    else:
        tw_plat_daily = pd.DataFrame()

    tw_symbol_df = get_tw_stock_symbol_breakdown()
    if not tw_symbol_df.empty:
        tw_symbol_df = filter_window(tw_symbol_df, "snapshot_date", window, custom_start, custom_end)

    COLORS = {
        "total": "#636EFA",
        "crypto": "#F7C244",
        "tw_stock": "#00CC96",
        "us_stock": "#EF553B",
    }
    NAMES = {
        "total": "總資產",
        "crypto": "幣圈",
        "tw_stock": "台股",
        "us_stock": "美股",
    }

    selected_cats = [c for c in ["total", "crypto", "tw_stock", "us_stock"]
                     if not all_daily[all_daily["category"] == c].empty]

    show_breakdown = st.checkbox("顯示詳細分解（來源 + 個股/Token）", value=False)
    show_crypto_breakdown = show_breakdown
    show_us_stock_breakdown = show_breakdown
    show_tw_stock_breakdown = show_breakdown

    def _crypto_hover_texts(dates) -> list[str]:
        """Build per-date hover strings for the 幣圈 trace (stacked sections)."""
        TOP_N = 5
        texts = []
        for ts in dates:
            lines: list[str] = []

            if not crypto_plat_daily.empty:
                day = crypto_plat_daily[crypto_plat_daily["snapshot_date"] == ts]
                total = day["value_usd"].sum()
                if total > 0:
                    lines.append("<b>來源</b>")
                    for _, r in (
                        day[day["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        name = PLATFORM_DISPLAY.get(r["platform"], r["platform"])
                        lines.append(f"{name}: {r['value_usd']/total*100:.0f}%")

            if not crypto_symbol_df.empty:
                day_t = crypto_symbol_df[crypto_symbol_df["snapshot_date"] == ts]
                total_t = day_t["value_usd"].sum()
                if total_t > 0:
                    if lines:
                        lines.append("─────────────")
                    lines.append("<b>Token</b>")
                    for _, r in (
                        day_t[day_t["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        lines.append(f"{r['symbol']}: {r['value_usd']/total_t*100:.0f}%")

            texts.append("<br>".join(lines) if lines else "")
        return texts

    def _us_stock_hover_texts(dates) -> list[str]:
        """Build per-date hover strings for the 美股 trace (stacked sections)."""
        TOP_N = 5
        texts = []
        for ts in dates:
            lines: list[str] = []

            if not us_plat_daily.empty:
                day = us_plat_daily[us_plat_daily["snapshot_date"] == ts]
                total = day["value_usd"].sum()
                if total > 0:
                    lines.append("<b>來源</b>")
                    for _, r in (
                        day[day["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        name = PLATFORM_DISPLAY.get(r["platform"], r["platform"])
                        lines.append(f"{name}: {r['value_usd']/total*100:.0f}%")

            if not us_symbol_df.empty:
                day_t = us_symbol_df[us_symbol_df["snapshot_date"] == ts]
                total_t = day_t["value_usd"].sum()
                if total_t > 0:
                    if lines:
                        lines.append("─────────────")
                    lines.append("<b>個股</b>")
                    for _, r in (
                        day_t[day_t["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        lines.append(f"{r['symbol']}: {r['value_usd']/total_t*100:.0f}%")

            texts.append("<br>".join(lines) if lines else "")
        return texts

    def _tw_stock_hover_texts(dates) -> list[str]:
        """Build per-date hover strings for the 台股 trace (stacked sections)."""
        TOP_N = 5
        texts = []
        for ts in dates:
            lines: list[str] = []

            if not tw_plat_daily.empty:
                day = tw_plat_daily[tw_plat_daily["snapshot_date"] == ts]
                total = day["value_usd"].sum()
                if total > 0:
                    lines.append("<b>來源</b>")
                    for _, r in (
                        day[day["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        name = PLATFORM_DISPLAY.get(r["platform"], r["platform"])
                        lines.append(f"{name}: {r['value_usd']/total*100:.0f}%")

            if not tw_symbol_df.empty:
                day_t = tw_symbol_df[tw_symbol_df["snapshot_date"] == ts]
                total_t = day_t["value_usd"].sum()
                if total_t > 0:
                    if lines:
                        lines.append("─────────────")
                    lines.append("<b>個股</b>")
                    for _, r in (
                        day_t[day_t["value_usd"] > 0]
                        .sort_values("value_usd", ascending=False)
                        .head(TOP_N)
                        .iterrows()
                    ):
                        lines.append(f"{r['symbol']}: {r['value_usd']/total_t*100:.0f}%")

            texts.append("<br>".join(lines) if lines else "")
        return texts

    use_return = "報酬率" in mode

    fig_line = go.Figure()
    for cat in selected_cats:
        sub = all_daily[all_daily["category"] == cat].sort_values("snapshot_date")
        if sub.empty:
            continue

        y = sub["value_usd"]
        if use_return and y.iloc[0] > 0:
            y = (y - y.iloc[0]) / y.iloc[0] * 100

        if cat == "crypto" and show_crypto_breakdown:
            hover_texts = _crypto_hover_texts(sub["snapshot_date"])
            fig_line.add_trace(go.Scatter(
                x=sub["snapshot_date"],
                y=y,
                name=NAMES["crypto"],
                line=dict(color=COLORS["crypto"], width=2),
                mode="lines",
                customdata=hover_texts,
                hovertemplate=(
                    "<b>幣圈</b>: %{y:.2f}%<br>%{customdata}<extra></extra>"
                    if use_return else
                    "<b>幣圈</b>: $%{y:,.0f} USD<br>%{customdata}<extra></extra>"
                ),
            ))
        elif cat == "us_stock" and show_us_stock_breakdown:
            hover_texts = _us_stock_hover_texts(sub["snapshot_date"])
            fig_line.add_trace(go.Scatter(
                x=sub["snapshot_date"],
                y=y,
                name=NAMES["us_stock"],
                line=dict(color=COLORS["us_stock"], width=2),
                mode="lines",
                customdata=hover_texts,
                hovertemplate=(
                    "<b>美股</b>: %{y:.2f}%<br>%{customdata}<extra></extra>"
                    if use_return else
                    "<b>美股</b>: $%{y:,.0f} USD<br>%{customdata}<extra></extra>"
                ),
            ))
        elif cat == "tw_stock" and show_tw_stock_breakdown:
            hover_texts = _tw_stock_hover_texts(sub["snapshot_date"])
            fig_line.add_trace(go.Scatter(
                x=sub["snapshot_date"],
                y=y,
                name=NAMES["tw_stock"],
                line=dict(color=COLORS["tw_stock"], width=2),
                mode="lines",
                customdata=hover_texts,
                hovertemplate=(
                    "<b>台股</b>: %{y:.2f}%<br>%{customdata}<extra></extra>"
                    if use_return else
                    "<b>台股</b>: $%{y:,.0f} USD<br>%{customdata}<extra></extra>"
                ),
            ))
        else:
            fig_line.add_trace(go.Scatter(
                x=sub["snapshot_date"],
                y=y,
                name=NAMES.get(cat, cat),
                line=dict(color=COLORS.get(cat, "#888"), width=2),
                mode="lines",
            ))

    fig_line.update_layout(
        height=380,
        margin=dict(t=20, b=20),
        yaxis_title="報酬率 (%)" if use_return else "USD",
        xaxis_title="",
        legend=dict(orientation="h", y=-0.15),
        hovermode="x unified",
    )
    st.plotly_chart(fig_line, use_container_width=True)

    # Metrics row
    st.markdown("**績效指標**（選定時間窗口）")
    metric_cols = st.columns(4)
    for i, (cat, label) in enumerate([("total", "總資產"), ("crypto", "幣圈"), ("tw_stock", "台股"), ("us_stock", "美股")]):
        sub = all_daily[all_daily["category"] == cat].sort_values("snapshot_date")
        m = compute_metrics(sub.set_index("snapshot_date")["value_usd"])
        with metric_cols[i]:
            st.markdown(f"**{label}**")
            if m["total_return"] is not None:
                st.metric("報酬率", f"{m['total_return']*100:+.2f}%")
                sharpe_str = f"{m['sharpe']:.2f}" if m["sharpe"] is not None else "—"
                mdd_str = f"{m['mdd']*100:.2f}%" if m["mdd"] is not None else "—"
                sharpe_help = (
                    "Sharpe Ratio（年化，無風險利率=0）：每單位風險的報酬效率。"
                    "注意：Sharpe 與總報酬可能方向相反——前段穩定上漲末段急跌時，Sharpe 仍偏高但總報酬為負。"
                    "ffill 補值會壓低波動度使 Sharpe 偏高。"
                )
                st.markdown(
                    f'<small style="color:gray">Sharpe: {sharpe_str}&nbsp;'
                    f'<span title="{sharpe_help}" style="cursor:help">ⓘ</span></small><br>'
                    f'<small style="color:gray">MDD: {mdd_str}</small>',
                    unsafe_allow_html=True,
                )
            else:
                st.metric("報酬率", "—")
                st.caption("資料不足")

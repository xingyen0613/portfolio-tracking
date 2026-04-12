"""
Portfolio Dashboard — Streamlit entry point.
Run: streamlit run app/dashboard/main.py --server.port 857
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path when Streamlit runs this file directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.dashboard.data import get_holdings, get_latest_snapshot_date, get_snapshot_history
from app.dashboard.metrics import compute_metrics, filter_window
from config.settings import CATEGORY_LABEL, TWD_PER_USD

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

total_usd = df["value_usd"].sum()
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
    "sui_wallet": "SUI On-chain",
    "yuanta": "元大證券（台股）",
    "firsttrade": "FirstTrade（美股）",
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
all_platforms = ["binance", "okx", "sui_wallet", "yuanta", "firsttrade"]

for platform in all_platforms:
    display_name = PLATFORM_DISPLAY.get(platform, platform)

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
                label = acct_df["account_label"].iloc[0] or account_key
                acct_total = acct_df["value_usd"].sum()
                with st.expander(f"🔑 `{account_key}` — ${acct_total:,.2f} USD", expanded=False):
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

# Aggregate by category
cat_df = df.groupby("category")["value_usd"].sum().reset_index()
cat_df["label"] = cat_df["category"].map(CATEGORY_LABEL).fillna(cat_df["category"])
cat_df = cat_df[cat_df["value_usd"] > 0]

# Build hover text: top 5 tokens per category (merged across platforms)
token_by_cat = (
    df[df["value_usd"] > 0]
    .groupby(["category", "platform_symbol"])["value_usd"]
    .sum()
    .reset_index()
)


def _top5_hover(cat: str) -> str:
    sub = token_by_cat[token_by_cat["category"] == cat].nlargest(5, "value_usd")
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
    col_mode, col_window = st.columns([1, 1])
    with col_mode:
        mode = st.radio("顯示模式", ["絕對數值 (USD)", "報酬率 (%)"], horizontal=True)
    with col_window:
        window = st.selectbox("時間窗口", ["1W", "1M", "1Q", "1Y"], index=1)

    # Aggregate daily by category
    daily = (
        history_df.groupby(["snapshot_date", "category"])["value_usd"]
        .sum()
        .reset_index()
    )
    daily_total = daily.groupby("snapshot_date")["value_usd"].sum().reset_index()
    daily_total["category"] = "total"

    all_daily = pd.concat([daily, daily_total], ignore_index=True)
    all_daily = filter_window(all_daily, "snapshot_date", window)

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

    use_return = "報酬率" in mode

    fig_line = go.Figure()
    for cat in ["total", "crypto", "tw_stock", "us_stock"]:
        sub = all_daily[all_daily["category"] == cat].sort_values("snapshot_date")
        if sub.empty:
            continue

        y = sub["value_usd"]
        if use_return and y.iloc[0] > 0:
            y = (y - y.iloc[0]) / y.iloc[0] * 100

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
                st.caption(f"Sharpe: {sharpe_str}　MDD: {mdd_str}")
            else:
                st.metric("報酬率", "—")
                st.caption("資料不足")

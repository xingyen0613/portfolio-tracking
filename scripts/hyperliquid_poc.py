"""
Hyperliquid Info API PoC — 公開 endpoint，只需錢包地址，不需 API key。

抓四個 resource：
  clearinghouseState       — 永續帳戶總值 + 各倉位
  spotClearinghouseState   — 現貨餘額
  spotMetaAndAssetCtxs     — 現貨定價（把 balances 換算成 USD）
  portfolio                — 歷史資產曲線（day/week/month/allTime × spot/perp）

並實測三個文檔沒寫清楚、不能用假設帶過的問題：
  Q1  marginSummary.accountValue 是否已含未實現損益？
      → 對帳 accountValue vs totalRawUsd + Σ unrealizedPnl
  Q2  info endpoint 的 rate limit 實際行為？
      → --rate-probe N 連打 N 次，記錄 status / 耗時 / 429 header
  Q3  portfolio 歷史能回溯多久、取樣多密、尾端是否接得上當前 accountValue？
      → 印各 period 的時間跨度 / 資料點數 / 取樣間隔分佈 / 尾值對帳
      （官方警告：portfolio 圖表在出入金與每 15 分鐘取樣，"not recommended
        for precise accounting purposes" — 所以尾值對帳一定要看）

用法：
  uv run python scripts/hyperliquid_poc.py 0x<42-char-address>
  uv run python scripts/hyperliquid_poc.py 0x... --rate-probe 30
  uv run python scripts/hyperliquid_poc.py 0x... --out /path/to/dump.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api.hyperliquid.xyz/info"
DEFAULT_OUT = Path("/private/tmp/claude-501/-Users-yen-claude-Portfolio-Tracking"
                   "/c868ba32-33fd-4d8b-93c5-1216acef83bb/scratchpad/hyperliquid_poc_dump.json")


def info(req_type: str, **kwargs) -> tuple[dict | list | None, dict]:
    """回傳 (result, debug)；debug 含 status / elapsed_ms / error。"""
    body = {"type": req_type, **kwargs}
    t0 = time.time()
    try:
        resp = requests.post(API_URL, json=body, timeout=20)
        elapsed = int((time.time() - t0) * 1000)
        debug = {"status": resp.status_code, "elapsed_ms": elapsed}
        if resp.status_code != 200:
            debug["error"] = resp.text[:500]
            debug["headers"] = dict(resp.headers)
            return None, debug
        return resp.json(), debug
    except Exception as e:
        return None, {"status": None, "elapsed_ms": int((time.time() - t0) * 1000),
                      "error": f"{type(e).__name__}: {e}"}


def f(x, default=0.0) -> float:
    """Hyperliquid 所有數字都是 string，統一轉 float。"""
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def show_perps(state: dict) -> dict:
    """印永續帳戶摘要，回傳對帳用的數字。"""
    ms = state.get("marginSummary", {})
    cross = state.get("crossMarginSummary", {})
    positions = state.get("assetPositions", [])

    account_value = f(ms.get("accountValue"))
    total_raw_usd = f(ms.get("totalRawUsd"))

    print(f"  accountValue     : {account_value:,.6f}")
    print(f"  totalRawUsd      : {total_raw_usd:,.6f}")
    print(f"  totalNtlPos      : {f(ms.get('totalNtlPos')):,.6f}")
    print(f"  totalMarginUsed  : {f(ms.get('totalMarginUsed')):,.6f}")
    print(f"  withdrawable     : {f(state.get('withdrawable')):,.6f}")
    print(f"  crossMaintenance : {f(state.get('crossMaintenanceMarginUsed')):,.6f}")
    print(f"  crossAccountValue: {f(cross.get('accountValue')):,.6f}")
    print(f"  倉位數           : {len(positions)}")

    total_upnl = 0.0
    signed_pos = 0.0   # Σ sign(szi) × positionValue，帳戶淨值公式的部位項
    for ap in positions:
        p = ap.get("position", {})
        upnl = f(p.get("unrealizedPnl"))
        szi = f(p.get("szi"))
        pv = f(p.get("positionValue"))
        total_upnl += upnl
        signed_pos += pv if szi > 0 else -pv
        lev = p.get("leverage", {})
        print(f"    {p.get('coin', '?'):<10} szi={p.get('szi', '?'):>16}  "
              f"entry={p.get('entryPx', '-'):>12}  posValue={pv:>14,.2f}  "
              f"uPnL={upnl:>12,.2f}  lev={lev.get('value', '?')}x/{lev.get('type', '?')}  "
              f"liq={p.get('liquidationPx') or '-'}")

    return {"account_value": account_value, "total_raw_usd": total_raw_usd,
            "total_upnl": total_upnl, "signed_position_value": signed_pos,
            "position_count": len(positions)}


def build_spot_prices(spot_meta_ctxs) -> dict[str, float]:
    """從 spotMetaAndAssetCtxs 建 token name → USD 價格。

    回傳結構是 [meta, ctxs]：
      meta.tokens[]   — {name, index, szDecimals, weiDecimals, ...}
      meta.universe[] — {tokens: [baseIdx, quoteIdx], name, index}
      ctxs[i]         — 對應 universe[i] 的 {midPx, markPx, prevDayPx, ...}
    """
    if not isinstance(spot_meta_ctxs, list) or len(spot_meta_ctxs) < 2:
        return {}
    meta, ctxs = spot_meta_ctxs[0], spot_meta_ctxs[1]
    tokens = meta.get("tokens", [])
    universe = meta.get("universe", [])

    name_by_idx = {t.get("index"): t.get("name") for t in tokens}
    usdc_idx = next((t.get("index") for t in tokens if t.get("name") == "USDC"), None)

    prices: dict[str, float] = {"USDC": 1.0}
    for pair, ctx in zip(universe, ctxs):
        pair_tokens = pair.get("tokens") or []
        if len(pair_tokens) != 2:
            continue
        base_idx, quote_idx = pair_tokens
        if usdc_idx is not None and quote_idx != usdc_idx:
            continue  # 只認 USDC 計價對，其他要再換一手，PoC 階段先跳過
        px = ctx.get("midPx") or ctx.get("markPx")
        if px is None:
            continue
        base_name = name_by_idx.get(base_idx)
        if base_name:
            prices[base_name] = f(px)
    return prices


def show_spot(state: dict, prices: dict[str, float]) -> dict:
    balances = state.get("balances", [])
    print(f"  幣種數: {len(balances)}   可定價 token 數: {len(prices)}")

    total_usd = 0.0
    unpriced = []
    for b in balances:
        coin = b.get("coin", "?")
        total = f(b.get("total"))
        if total == 0:
            continue
        px = prices.get(coin)
        if px is None:
            unpriced.append(coin)
            print(f"    {coin:<12} total={total:>18,.8f}  hold={f(b.get('hold')):>14,.8f}  "
                  f"entryNtl={f(b.get('entryNtl')):>12,.2f}  px=<無 USDC 對>")
            continue
        usd = total * px
        total_usd += usd
        print(f"    {coin:<12} total={total:>18,.8f}  hold={f(b.get('hold')):>14,.8f}  "
              f"entryNtl={f(b.get('entryNtl')):>12,.2f}  px={px:>12,.6f}  USD={usd:>14,.2f}")

    return {"total_usd": total_usd, "coin_count": len(balances), "unpriced": unpriced}


def show_portfolio(portfolio, current_perp_av: float) -> dict:
    """印各時間區間的歷史曲線特徵，回答 Q3。

    回傳結構是 pair list：[[period_name, {accountValueHistory, pnlHistory, vlm}], ...]
    history 資料點為 [timestamp_ms, "value_string"]。
    """
    if not isinstance(portfolio, list):
        print(f"  非預期結構：{type(portfolio).__name__}")
        return {}

    out = {}
    for entry in portfolio:
        if not (isinstance(entry, list) and len(entry) == 2):
            continue
        period, data = entry
        if not isinstance(data, dict):
            continue
        avh = data.get("accountValueHistory") or []
        pnl = data.get("pnlHistory") or []

        if not avh:
            print(f"  {period:<14} 無資料點  vlm={data.get('vlm', '-')}")
            out[period] = {"points": 0}
            continue

        ts_first, ts_last = int(avh[0][0]), int(avh[-1][0])
        dt_first = datetime.fromtimestamp(ts_first / 1000, timezone.utc)
        dt_last = datetime.fromtimestamp(ts_last / 1000, timezone.utc)
        span_days = (ts_last - ts_first) / 86_400_000

        # 取樣間隔分佈
        gaps = [(int(avh[i + 1][0]) - int(avh[i][0])) / 60000 for i in range(len(avh) - 1)]
        gap_desc = "-"
        if gaps:
            gaps_sorted = sorted(gaps)
            median = gaps_sorted[len(gaps_sorted) // 2]
            gap_desc = f"median={median:.1f}min min={min(gaps):.1f} max={max(gaps):.1f}"

        v_first, v_last = f(avh[0][1]), f(avh[-1][1])
        print(f"  {period:<14} {len(avh):>5} 點  {dt_first:%Y-%m-%d %H:%M} → "
              f"{dt_last:%Y-%m-%d %H:%M}  ({span_days:.1f} 天)")
        print(f"  {'':<14} 首值={v_first:>14,.2f}  尾值={v_last:>14,.2f}  "
              f"pnl點數={len(pnl)}  vlm={data.get('vlm', '-')}")
        print(f"  {'':<14} 取樣間隔 {gap_desc}")

        out[period] = {"points": len(avh), "span_days": span_days,
                       "first_ts": ts_first, "last_ts": ts_last,
                       "first_value": v_first, "last_value": v_last,
                       "median_gap_min": (sorted(gaps)[len(gaps) // 2] if gaps else None)}

    # 尾值對帳：perpAllTime 的最後一點 vs 當前 clearinghouseState accountValue
    print("\n  ── Q3 尾值對帳（歷史曲線是否接得上當前狀態）──")
    for period in ("perpAllTime", "perpDay"):
        info_p = out.get(period)
        if not info_p or not info_p.get("points"):
            continue
        tail = info_p["last_value"]
        diff = tail - current_perp_av
        age_min = (time.time() * 1000 - info_p["last_ts"]) / 60000
        print(f"    {period:<14} 尾值={tail:,.2f}  當前 accountValue={current_perp_av:,.2f}  "
              f"差={diff:,.2f}  尾點距今 {age_min:.1f} 分鐘")
        info_p["tail_vs_current_diff"] = diff
        info_p["tail_age_min"] = age_min

    return out


def rate_probe(address: str, n: int) -> list[dict]:
    """連打 n 次 clearinghouseState，記錄每次 status / 耗時，遇 429 印出 header。"""
    print(f"\n═══ Rate limit probe（連打 {n} 次 clearinghouseState，無間隔）═══")
    records = []
    for i in range(n):
        _, dbg = info("clearinghouseState", user=address)
        records.append({"i": i + 1, **dbg})
        if dbg.get("status") != 200:
            print(f"  第 {i + 1} 次 非 200：status={dbg.get('status')} "
                  f"elapsed={dbg.get('elapsed_ms')}ms")
            print(f"    error  : {str(dbg.get('error'))[:300]}")
            if dbg.get("headers"):
                print(f"    headers: {json.dumps(dbg['headers'], ensure_ascii=False)[:500]}")
            break

    ok = [r for r in records if r.get("status") == 200]
    print(f"  結果：{len(ok)}/{len(records)} 次 200")
    if ok:
        times = [r["elapsed_ms"] for r in ok]
        print(f"  耗時 ms：min={min(times)} max={max(times)} "
              f"avg={sum(times) // len(times)}")
    if len(ok) == len(records):
        print(f"  → {n} 次連續請求全部通過，未觸發 rate limit")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address", help="Hyperliquid 錢包地址（0x + 40 hex）")
    ap.add_argument("--rate-probe", type=int, default=0, metavar="N",
                    help="額外連打 N 次 clearinghouseState 測 rate limit（預設不跑）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="完整 JSON dump 路徑")
    args = ap.parse_args()

    addr = args.address.strip()
    if not (addr.startswith("0x") and len(addr) == 42):
        print(f"位址格式不對：{addr!r}（需要 0x + 40 hex，共 42 字元）")
        sys.exit(1)

    dump = {"address": addr, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "api_url": API_URL}

    # ── 1. 永續帳戶 ────────────────────────────────────────────────
    print("\n═══ clearinghouseState（永續）═══")
    perp, dbg = info("clearinghouseState", user=addr)
    dump["clearinghouseState"] = {"result": perp, "debug": dbg}
    perp_summary = None
    if perp is None:
        print(f"  ERROR: {dbg}")
    else:
        print(f"  [{dbg['status']}] {dbg['elapsed_ms']}ms")
        perp_summary = show_perps(perp)

    # ── 2. 現貨餘額 ────────────────────────────────────────────────
    print("\n═══ spotClearinghouseState（現貨）═══")
    spot, dbg = info("spotClearinghouseState", user=addr)
    dump["spotClearinghouseState"] = {"result": spot, "debug": dbg}
    print(f"  [{dbg['status']}] {dbg['elapsed_ms']}ms" if spot is not None else f"  ERROR: {dbg}")

    # ── 3. 現貨定價 ────────────────────────────────────────────────
    print("\n═══ spotMetaAndAssetCtxs（現貨定價）═══")
    meta_ctxs, dbg = info("spotMetaAndAssetCtxs")
    dump["spotMetaAndAssetCtxs"] = {"debug": dbg}
    prices = {}
    if meta_ctxs is None:
        print(f"  ERROR: {dbg}")
    else:
        print(f"  [{dbg['status']}] {dbg['elapsed_ms']}ms")
        prices = build_spot_prices(meta_ctxs)
        dump["spot_prices_derived"] = prices
        # meta 全量很大（數百個 token），只留 token/universe 筆數與衍生價格
        if isinstance(meta_ctxs, list) and meta_ctxs:
            m = meta_ctxs[0]
            print(f"  tokens={len(m.get('tokens', []))}  universe={len(m.get('universe', []))}  "
                  f"→ 建出 {len(prices)} 個 USDC 計價")

    spot_summary = None
    if spot is not None:
        print("\n  ── 現貨餘額明細 ──")
        spot_summary = show_spot(spot, prices)

    # ── 4. 對帳：回答 Q1 ───────────────────────────────────────────
    print("\n═══ Q1 對帳：accountValue 的組成 ═══")
    if perp_summary:
        av = perp_summary["account_value"]
        raw = perp_summary["total_raw_usd"]
        upnl = perp_summary["total_upnl"]
        signed_pos = perp_summary["signed_position_value"]
        diff = av - (raw + signed_pos)
        print(f"  accountValue                   = {av:>18,.6f}")
        print(f"  totalRawUsd（純現金）           = {raw:>18,.6f}")
        print(f"  Σ sign(szi)×positionValue      = {signed_pos:>18,.6f}")
        print(f"  → raw + Σsign×posValue         = {raw + signed_pos:>18,.6f}")
        print(f"  差額                            = {diff:>18,.8f}")
        if perp_summary["position_count"] == 0:
            print("  → 無倉位，公式退化為 accountValue == totalRawUsd（驗不出部位項）")
        elif abs(diff) < 0.5:
            print("  → 成立。positionValue 以 markPx 計價，本身即含未實現損益，")
            print("    所以 accountValue 已包含未實現損益，可直接當永續 net asset。")
        else:
            print("  → 不成立：差額超過容忍值，需要進一步拆解欄位")
        print(f"\n  未實現損益子分類：Σ unrealizedPnl = {upnl:,.6f}")
        print("  （這是 accountValue 內含的一部分，單獨記錄用，不可再加總）")
        dump["q1_reconciliation"] = {
            "account_value": av, "total_raw_usd": raw,
            "signed_position_value": signed_pos,
            "sum_unrealized_pnl": upnl, "diff": diff,
            "position_count": perp_summary["position_count"],
        }
    else:
        print("  略過（永續資料抓取失敗）")

    # ── 5. 總資產 ──────────────────────────────────────────────────
    print("\n═══ 總資產估算 ═══")
    perp_usd = perp_summary["account_value"] if perp_summary else 0.0
    spot_usd = spot_summary["total_usd"] if spot_summary else 0.0
    print(f"  永續 accountValue : {perp_usd:>16,.2f} USD")
    print(f"  現貨 Σ(total×px)  : {spot_usd:>16,.2f} USD")
    print(f"  合計              : {perp_usd + spot_usd:>16,.2f} USD")
    if spot_summary and spot_summary["unpriced"]:
        print(f"  ⚠ 未定價幣種（未計入）: {', '.join(spot_summary['unpriced'])}")
    dump["totals"] = {"perp_usd": perp_usd, "spot_usd": spot_usd,
                      "total_usd": perp_usd + spot_usd}

    # ── 6. 歷史資產曲線：回答 Q3 ──────────────────────────────────
    print("\n═══ portfolio（歷史資產曲線）═══")
    portfolio, dbg = info("portfolio", user=addr)
    dump["portfolio"] = {"result": portfolio, "debug": dbg}
    if portfolio is None:
        print(f"  ERROR: {dbg}")
    else:
        print(f"  [{dbg['status']}] {dbg['elapsed_ms']}ms")
        dump["q3_portfolio_summary"] = show_portfolio(portfolio, perp_usd)

    # ── 7. Q2 rate limit ──────────────────────────────────────────
    if args.rate_probe > 0:
        dump["rate_probe"] = rate_probe(addr, args.rate_probe)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dump, ensure_ascii=False, indent=2))
    print(f"\n✓ 完整 dump 已寫入 {args.out}")


if __name__ == "__main__":
    main()

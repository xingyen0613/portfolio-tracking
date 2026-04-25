# 資料處理 Pipeline 說明

各平台從原始資料到資料庫的完整流程，以及每個儲存斷點的位置。

---

## 斷點設計概念

每個「斷點」代表該階段結束後資料有獨立儲存，可以單獨查看，或在不重跑前面步驟的情況下重新執行後面的步驟。

---

## CEX：Binance / OKX / MEXC / Bybit

**執行方式**：`uv run python -m app.jobs.run_batch --platform <name>`

```
API 呼叫 → [斷點 1] → 解析 → [斷點 2] → 補價格 → [斷點 3] → 加總 → [斷點 4]
```

| # | 做了什麼 | 儲存位置 |
|---|---------|---------|
| 1 | ccxt 抓原始餘額（spot / earn / funding 等各 resource 分開呼叫，回傳原始 JSON） | **磁碟**：`data/raw/YYYY-MM-DD/batch_xxx/{platform}/account_main/{resource_type}_yyyymmdd.json`<br>**DB**：`raw_payloads`（記 file_path + hash） |
| 2 | `parse_holdings()`：raw JSON → 統一格式（symbol、qty、value），`price = NULL`（CEX API 不帶市價） | **DB**：`normalized_holdings`（price 欄位此時為 NULL） |
| 3 | Pricer（`app/valuation/pricer.py`）：用 Binance ccxt 補齊所有 `price=NULL` 的 symbol，計算 value | 不額外存檔；直接更新記憶體，與斷點 2 同一批寫入 `normalized_holdings`（price_source='market'） |
| 4 | 帳戶總值加總、category 加總 | **DB**：`account_snapshots`（USD）、`category_snapshots`（crypto） |

**各平台 resource_type 對照：**

| 平台 | resource_type |
|------|--------------|
| Binance | spot、earn_flexible、earn_locked、funding |
| OKX | spot、savings |
| MEXC | spot、futures |
| Bybit | spot、funding |

---

## SUI 鏈上錢包

**執行方式**：`uv run python -m app.jobs.run_batch --platform sui_wallet`

```
RPC 查詢（3 次）→ [斷點 1] → 合併解析 → [斷點 2] → 加總 → [斷點 3]
```

| # | 做了什麼 | 儲存位置 |
|---|---------|---------|
| 1 | 三次查詢：(a) Sui 公共 RPC `suix_getAllBalances` 抓幣種餘額、(b) RPC `suix_getCoinMetadata` 抓 metadata、(c) Pyth Hermes API 抓即時報價。**三者皆免費、無需 API key、無用量限制** | **磁碟**：`data/raw/.../sui_wallet/{addr10}/balances_xxx.json`、`coin_metadata_xxx.json`、`pyth_prices_xxx.json`<br>**DB**：`raw_payloads`（3 筆） |
| 2 | 三份 raw 合併：餘額 × metadata × Pyth 價格，過濾白名單（COIN_FEED_MAP）且 USD value > $1 | **DB**：`normalized_holdings`（price_source='pyth' 或 'stable'） |
| 3 | 帳戶總值加總、category 加總 | **DB**：`account_snapshots`（USD）、`category_snapshots`（crypto） |

**定價邏輯：**
- 主流幣（SUI、ETH、BTC、USDC 等）→ Pyth Hermes 即時報價
- 已知穩定幣（BUCK、MUSD、AUSD 等）→ 固定 $1.0（price_source='stable'）
- 不在白名單的幣 → 過濾，不計入
- 白名單 key 使用完整 coin_type address，防止山寨幣偽造 symbol

> SUI connector 不走共用 pricer（`use_pricer = False`），價格在 fetch_raw 階段即取得。

---

## IBKR 美股

**執行方式**：`uv run python -m app.jobs.run_batch --platform ibkr`

```
Flex API（2 步驟）→ [斷點 1] → 解析 XML → [斷點 2] → 加總 → [斷點 3]
```

| # | 做了什麼 | 儲存位置 |
|---|---------|---------|
| 1 | SendRequest 取得 ReferenceCode，GetStatement 拿 XML 報表（IBKR Flex Web Service） | **磁碟**：`data/raw/.../ibkr/account_main/flex_report_xxx.json`（含完整 XML 字串）<br>**DB**：`raw_payloads` |
| 2 | 解析 XML：`OpenPosition`（levelOfDetail=SUMMARY）→ 股票持倉（markPrice 直接帶入）；`EquitySummaryByReportDateInBase` → 現金（可為負值，代表保證金借款）。**無需補價格，平台直接提供市價** | **DB**：`normalized_holdings`（price_source='platform'） |
| 3 | 帳戶總值加總、category 加總 | **DB**：`account_snapshots`（USD）、`category_snapshots`（us_stock） |

**設定**：`.env` 需填入 `IBKR_FLEX_TOKEN` 與 `IBKR_FLEX_QUERY_ID`（參考 `.env.example`）

---

## Firsttrade 美股（目前無 connector）

**執行方式**：手動 INSERT（見 `scripts/` 或直接寫 Python）

```
手動輸入 → [斷點 1] → 加總 → [斷點 2]
```

| # | 做了什麼 | 儲存位置 |
|---|---------|---------|
| 1 | 手動建立 source_run、raw_payload（placeholder）、每筆股票 INSERT | **磁碟**：`data/raw/firsttrade/manual_YYYY-MM-DD.json`<br>**DB**：`normalized_holdings`（price_source='manual'） |
| 2 | 帳戶總值加總、category 加總 | **DB**：`account_snapshots`（USD）、`category_snapshots`（us_stock） |

> 無 pricer 步驟，價格手動填入。Firsttrade connector 實作後此流程將替換為自動化。

---

## 元大台股

**執行方式**：`uv run python scripts/yuanta_run_pipeline.py`（或各步驟單獨執行）

```
Gmail → [斷點 1] → PDF 解析 → [斷點 2] → 日持股重建 → [斷點 3] → 收盤價抓取 → [斷點 4] → 每日淨資產 → [斷點 5] → 寫入 DB → [斷點 6]
```

| # | 做了什麼 | 儲存位置 |
|---|---------|---------|
| 1 | `yuanta_gmail_poc.py`：Gmail API 搜尋元大寄件，下載 PDF 附件 | **磁碟**：`data/raw/yuanta_poc/YYYY-MM/yuanta_statement.pdf` |
| 2 | `yuanta_pdf_parse_poc.py`：pdfplumber 解析 PDF，萃取自有持股、擔保品、融資餘額 | **磁碟**：`data/raw/yuanta_poc/YYYY-MM/parsed.json` |
| 3 | `yuanta_daily_reconstruct_poc.py`：從月底 ground truth 反推每天的持股數量與融資餘額 | **磁碟**：`data/derived/yuanta_poc/YYYY-MM/daily_holdings.json` |
| 4 | `yuanta_price_fetch_poc.py`：Yahoo Finance 抓各股歷史收盤價（只有交易日有值） | **磁碟**：`data/derived/yuanta_poc/prices/YYYY-MM.json` |
| 5 | `yuanta_net_asset_poc.py`：每日淨資產 = 持股市值（各股 × 收盤價）- 融資餘額；非交易日存 `null` | **磁碟**：`data/derived/yuanta_poc/YYYY-MM/daily_net_asset.json` |
| 6 | `yuanta_insert_poc.py`：寫入主系統 DB | **DB**：`account_snapshots`（TWD）、`category_snapshots`（tw_stock，TWD） |

> 元大目前沒有 `normalized_holdings` 這層，直接從 net_asset JSON 寫 account_snapshots。原始 PDF 是唯一的 source of truth，其餘斷點皆為衍生計算。

---

## 橫向比較

| 平台 | raw 磁碟檔 | normalized_holdings | pricer 步驟 | 價格來源 | account_snapshots | category |
|------|-----------|--------------------|-----------|---------|-----------------|----|
| Binance / OKX / MEXC / Bybit | ✓ | ✓（price 補齊後寫入） | 共用 Binance ccxt | market | ✓ USD | crypto |
| SUI | ✓（3 份） | ✓（Pyth 價格自帶） | 無（connector 自帶） | Pyth / stable | ✓ USD | crypto |
| IBKR | ✓（XML in JSON） | ✓（平台帶價格） | 無（connector 自帶） | platform | ✓ USD | us_stock |
| Firsttrade | ✓（手動 placeholder） | ✓（手動填價） | 無 | manual | ✓ USD | us_stock |
| 元大 | PDF → 5 層 JSON | **無** | Yahoo Finance（獨立腳本） | Yahoo Finance | ✓ TWD | tw_stock |

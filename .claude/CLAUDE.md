# Portfolio-Tracking 專案規則

## 敏感檔案限制

**禁止讀取以下檔案，無論任何情況：**
- `.env`
- `.env.*`（包含 `.env.ibkr`、`.env.local` 等所有變體）

需要知道某個環境變數的 key 名稱時，讀 `.env.example` 即可。

## 資料保護規則

以下資料屬於不可變的歷史紀錄，**禁止在未獲明確授權的情況下修改或刪除**：
- SQLite 中的 `normalized_holdings`、`account_snapshots`、`category_snapshots` 表的現有資料
- `data/raw/` 和 `data/derived/` 下的所有歷史快照 JSON 檔案
- `source_runs`、`batches` 等 audit trail 表的記錄

例外：用戶明確說「幫我修改/刪除這筆資料」時才可執行。

## 文件

- [資料處理 Pipeline 說明](../docs/data-pipeline.md) — 各平台斷點設計、儲存位置、定價來源
- [元大 cum_cash 限制](../docs/yuanta-cumcash-known-limitations.md) — 月底 anchor step 成因與未來解法

## 架構決策

### 美股 category（us_stock）資料來源
- 歷史手動輸入的資料（backfill-manual batch）代表的是 **us_stock category 的總和**，不是單一平台的帳戶資料
- 這些手動資料存在 `category_snapshots`（歷史折線圖用），不應存在 `account_snapshots` 的任何單一平台下
- Firsttrade 目前沒有 connector，`account_snapshots` 中無任何 firsttrade 資料；手動新增持倉時直接寫入 normalized_holdings + account_snapshots
- IBKR 有正式 connector（`app/connectors/ibkr_connector.py`），每日 batch 自動抓取

### IBKR Flex Web Service
- 正確 endpoint：`ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService`
- 必須帶 `User-Agent: Python/3` header
- 兩步驟：SendRequest（q=query_id）→ GetStatement（q=reference_code，非 referenceCode）
- 持倉：OpenPosition levelOfDetail=SUMMARY；現金：EquitySummaryByReportDateInBase 最新 reportDate 的 cash 欄（可為負值）
- GetStatement 一律用固定 `_BASE_URL/GetStatement`，不採用 SendRequest 回傳的動態 URL（避免 Zeabur 無法解析 `gdcdyn` 等其他 server node）

### 多租戶隔離（重要）
- **`get_account_id(platform, account_key, user_id)`** 必須帶 user_id 參數，否則跨用戶 account_id 會錯亂（`UNIQUE(platform_id, account_key, user_id)`）
- 所有寫入 `accounts / source_runs / account_snapshots / normalized_holdings / category_snapshots / batches` 都要帶 user_id
- `run_batch(platforms, user_id, connector_ids=None)` 一律 per-user 跑

### Yuanta net_asset 計算
- 公式：`market_value + other_assets + cum_cash − margin_balance`
  - `market_value`：自有 + 擔保品 × 每日股價
  - `other_assets`：parsed.json `summary.asset_categories` 中非股票/非擔保品的（期貨權益等）
  - `cum_cash`：transactions + margin_transactions 的 net_cashflow 累積，**跨月**
  - `margin_balance`：parsed.json 月底借款餘額
- 處理三種雙重計算：`repay_via_sell` / `advance_settlement_out` / `advance_settlement_in` 都要扣
- 月底 anchor 校準：`correction = official_net_asset − pre_anchor_calc`，結構上必然把 cum_cash 拉到 0
- yuanta 對帳單**沒有**現金存款餘額欄位、**沒有**外部出入金記錄 — 限制詳見 docs/yuanta-cumcash-known-limitations.md

### Holdings API dust 過濾
- `backend/routers/holdings.py:_build_sections` 在顯示層過濾 `|value_usd| < 5`
- DB 仍存全量；只有 API response 過濾

# 每次有新的開發進度完成，或是修正、優化後，且等用戶確認ok後，要更新相關文黨。包括但不限於@readme.md, @plan.md, etc.
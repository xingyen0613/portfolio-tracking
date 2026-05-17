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

## 部署注意事項

### DB Migration

**新增或修改以下內容時，必須在 push/部署前先執行 migration：**
- 新增 alembic migration 檔案（`alembic/versions/`）
- 新增資料表、欄位、index
- 新增 platform seed 資料（如 `009_seed_sinopac_platform.py`）

執行方式（本機連 Supabase）：
```bash
uv run alembic upgrade head
```

**背景說明：** `run_batch` 不再自動跑 migration（已從 `init_db()` 移除）。DB 更新與程式碼部署解耦，需手動確保兩者同步。若忘記執行，Zeabur batch 在用到新欄位時才會 crash，而不是在啟動時提早報錯。

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

### 鏈上錢包查詢（EVM / Solana / SUI）
- Alchemy API key 是**系統級共用資源**（server `ALCHEMY_API_KEY` env），所有用戶共用一把；不接受用戶在 credentials 自填（僅 EVM / Solana 需要）
- EVM Wallet 預設查全部支援 chain（`DEFAULT_EVM_CHAINS` = ethereum/bsc/arbitrum/optimism/base/avalanche/polygon/linea）
- Backend 仍接收 `credentials.chains`（fallback 順序：creds → `EVM_CHAINS` env → `DEFAULT_EVM_CHAINS`），未來放回前端讓用戶選 chain 時不需改 schema
- SUI Wallet 走公開 SUI RPC + Pyth oracle，**不需任何 API key**；地址只從 `credentials.addresses` 讀，**不再有 `SUI_WALLET_ADDRESSES` env fallback**（與 EVM / SOL 不同）
- 前端 textarea 用 local raw string state（非 list），避免 split/filter/join 把空行吃掉造成「按 Enter 不換行」的 bug

### Connector 刪除級聯
- `DELETE /api/connectors/{id}` 在單一 transaction 內級聯清掉該 connector 的歷史資料
- 清除：`accounts / source_runs / normalized_holdings / raw_payloads (DB) / account_snapshots`
- **保留**：`category_snapshots`（user-level 聚合，重算成本太高）、`batches`（cross-platform）、`data/raw/` JSON 檔（disk artifact，跨環境難一致管理）
- Connector → accounts 的對應關係按 platform 不同：
  - exchange / IBKR：1:1 by `account_key`
  - sol_wallet / sui_wallet：1:N by `addr[:10]`
  - evm_wallet：1:N by `addr[:10] || '_' || chain_short`（從 decrypted credentials.addresses 解出）

# 每次有新的開發進度完成，或是修正、優化後，且等用戶確認ok後，要更新相關文黨。包括但不限於@readme.md, @plan.md, etc.
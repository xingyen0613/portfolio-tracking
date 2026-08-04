# Portfolio-Tracking 專案規則

## 敏感檔案限制

**禁止讀取以下檔案／資料夾，無論任何情況：**
- `.env`
- `.env.*`（包含 `.env.ibkr`、`.env.local` 等所有變體）
- `.secrets/`（含所有子資料夾）— 存放憑證 .pfx、Gmail OAuth token 等，絕對不可讀取

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
- [Hyperliquid API PoC](../docs/hyperliquid-api-poc.md) — 淨值公式驗證、未實現損益拆分、歷史取樣限制

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

### 永豐證券（Sinopac / Shioaji）Connector
- 使用 `shioaji` SDK，以 `api_key + secret_key` 登入；**CA 不需要**（CA 只有下單才需要，查帳不需）
- 期貨選擇權帳戶整合在 `SinopacStockConnector` 內（非獨立 class），透過 `api.futopt_account is None` 判斷是否有期貨帳戶
- Login session 共用，整個 batch 只 login 一次（`_get_shioaji_api` 以 api_key 為 key cache）
- `SINOPAC_SIMULATION` env flag 可切換 simulation / production 模式（Zeabur 上不設則預設 production）

### 富邦證券（Fubon Neo API）Connector
- `apikey_login`（唯讀 API Key + .pfx 電子交易憑證），**電子平台密碼不進系統**；權限實測證據見 docs/fubon-api-poc.md（SDK 無出金介面、唯讀 key 下單被權限層拒絕）
- credentials schema：`{fubon_id, api_key, cert_pfx_b64, cert_password?}`（cert_password 空 = 身分證號）；憑證 base64 解回 0600 暫存檔登入，用畢即刪
- 範圍只做**現股+零股**：`inventories` 的 `today_qty + odd.today_qty` 相加；order_type 非 Stock（Margin/Short/DayTrade/SBL）略過並留 log
- 定價：`unrealized_gains_and_loses` 反推市值（cost×qty+損益），**不打外部查價**；platform 價格回存 price_cache；ENABLED_PLATFORMS 中 fubon 排在 sinopac 之後（cache 熱）
- SDK 回傳 pyo3 原生物件（無 `__dict__`/`model_dump`）：序列化用 `dir()+getattr`，enum 以 `str(v).startswith(型別名+'.')` 判別（dir() 展開 enum 會遞迴）
- `fubon-neo` 不在 PyPI：官方 binary whl 放 `vendor/`（Linux x86_64），Dockerfile 安裝；本機 macOS arm64 另裝
- 新增平台清單共**六處**：settings.py（ENABLED_PLATFORMS + PLATFORM_CATEGORY）、run_batch.py（dispatch + account tuple + implemented）、internal.py `_DAILY_PLATFORMS`、app/jobs/scheduler.py `implemented`、admin.py `_IMPLEMENTED`、holdings.py 顯示 meta；刪除級聯要加 connectors.py `EXCHANGE_LIKE_PLATFORMS`

### Yuanta net_asset 計算
- 公式：`market_value + other_assets + cum_cash − margin_balance`
  - `market_value`：自有 + 擔保品 × 每日股價
  - `other_assets`：parsed.json `summary.asset_categories` 中非股票/非擔保品的（期貨權益等）
  - `cum_cash`：transactions + margin_transactions 的 net_cashflow 累積，**跨月**
  - `margin_balance`：parsed.json 月底借款餘額
- 處理三種雙重計算：`repay_via_sell` / `advance_settlement_out` / `advance_settlement_in` 都要扣
- 月底 anchor 校準：`correction = official_net_asset − pre_anchor_calc`，結構上必然把 cum_cash 拉到 0
- yuanta 對帳單**沒有**現金存款餘額欄位、**沒有**外部出入金記錄 — 限制詳見 docs/yuanta-cumcash-known-limitations.md

### 預覽模式（demo）路由與登入 popup
- 前端無 router library，路由靠 `window.location.pathname` 判斷：legal 頁（`legal/content.ts`）、預覽頁（`frontend/src/preview.ts`）
- `/preview/<page>` 免登入直接進預覽模式並落在該分頁（settings / sources / dashboard / alerts，相容單數形）；預覽中切分頁會 `replaceState` 同步網址，退出預覽時還原 `/`
- 由網址進入**不跑導覽教學**（`DemoProvider initialDemo`），只有從登入頁按「預覽模式」才啟動 tour
- 預覽模式的訂閱按鈕不受 `SettingsTab.tsx` 的 `CHECKOUT_PENDING` 影響：一律顯示可點的「登入後訂閱」→ 開 `LoginPromptModal`（與登入頁相同的 GoogleLogin），登入成功即 `exitDemo()`
- 用途：可把 `https://allin-portfolio-tracking.pages.dev/preview/settings` 這種網址交給第三方（如金流服務商）審核，對方不需帳號即可看到訂閱方案頁
- Cloudflare Pages 靠 `frontend/public/_redirects` 的 `/* /index.html 200` 支援子路徑直開
- 導覽教學（`DemoTour.tsx`）共 6 步，每個 `TourStep` 帶 `route` 欄位；切到 Settings 的步驟由 `App.tsx` 傳入的 `setRoute` 換分頁，spotlight 目標靠 `data-tour` 屬性定位

### Settings 頁圖文使用說明
- `components/GuideSection.tsx`：Subscription 下方的 `Guide` 區塊，點按鈕開 modal（內容為六步驟圖文），點圖開 lightbox（z-index 300，疊在 modal 之上）
- 截圖存 `frontend/public/guide/step-01..16.jpg`（1440px 寬、全部 lazy load），非 bundler 資產，改圖直接換檔即可
- Settings 頁內容高於視窗，footer 以 `<Footer sticky>`（`route === 'settings'` 時）釘在視窗底部；其他頁維持隨內容捲動

### Hyperliquid Connector
- info endpoint **公開唯讀，不需 API key**，只要地址（同 sui_wallet 模式，1:N by `addr[:10]`）；下單才需私鑰，本專案不碰
- 淨值公式：`accountValue = totalRawUsd + Σ sign(szi) × positionValue`（實測差 0.00000000）
  - `totalRawUsd` 是**純現金**；開空會增加現金但部位計負值，故部位項必須帶正負號
  - `positionValue` 以 markPx 計價，**本身已含未實現損益**
- 未實現損益要「既是子分類又計入淨值」→ 拆兩段避免重複計算：
  `perp_position.value = sign(szi)×positionValue − uPnL`，`perp_upnl.value = ΣuPnL`，相加還原市值
- `perp_position` 的 `price` 是 entryPx 非市價，**price_source 不可設 "platform"**（會污染 price_cache）
- 歷史回補只在 `POST /api/connectors` 初次連接時跑一次（`hyperliquid_history.py`），取 `portfolio` 的 `allTime`
  - 取樣密度是 API 先天限制：近 30 天每日、更早每 7 天、三年帳戶可達 14 天一點
- 現貨 481 token 多為 meme，`USD_THRESHOLD = 1.0` 過濾粉塵；無 USDC 計價對的 token 直接略過

### 手動 CSV 來源（platform `manual` / category `other`）
- 給用戶登錄**不屬於台股/美股/幣圈**的資產（不動產、保單、現金），第四個 category `other`（label「其他」）
- **沒有 connector**：不進 `ENABLED_PLATFORMS`、不進 run_batch dispatch，因此新增平台的「六處清單」只需改 `PLATFORM_CATEGORY`；`connectors.py` 的 `NO_FETCH_PLATFORMS` 讓它跳過 try-fetch，`POST /refresh` 直接回 400
- 資料唯一入口是既有的 `POST /api/connectors/{id}/historical-import`（CSV `date,total_value` + 幣別 USD/TWD），credentials 為空 dict
- 新增來源時可**直接附 CSV**（選填）：`ConnectSourceModal` 的 mutationFn 串起 create → import 兩個呼叫，新來源必無舊資料所以固定用 `skip` 策略、不跑 dry-run；匯入失敗**不推翻**已建立的來源，只在成功畫面回報並請用戶到來源頁重試
- **不寫 `normalized_holdings`**（`raw_payload_id` NOT NULL，偽造 raw payload 成本過高）→ Holdings 頁改由 `get_manual_account_latest()` 直接讀 `account_snapshots`，在 `holdings.py` 尾端組成一張 accounts 卡片
- **carry forward**：`_aggregate_categories` 與 `rebuild_for_dates` 的聚合 SQL 本來就是「取 <= 該日最新一筆」，所以只要 category_snapshots 那天有被算過就會沿用；`historical_imports._fill_to_today()` 負責把最後一筆 CSV 之後補算到今天
- `other` 全為 0 時 `/api/portfolio/history` **不輸出這條序列**，前端 TrendTab / PerformanceMetrics 也據此隱藏 chip 與卡片 —— 沒有手動資產的用戶（含 demo）畫面完全不變
- `/api/portfolio/allocation/other` 下鑽顯示的是**各個手動來源**（公寓、保單…）而非標的
- `_slugify()` 對純中文標籤會 fallback 成 `acct_<sha1[:8]>`：中文名稱本來全被壓成 `"account"`，同用戶第二個中文來源會誤判 409

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

# xingyen0613是我的主帳號，xingyen02是測試帳號，開發功能與測試時已測試帳號xingyen02為主。
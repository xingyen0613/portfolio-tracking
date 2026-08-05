# Portfolio Tracker — 產品化 Roadmap

> 目標：將現有單用戶私有工具，轉型為可對外開放的訂閱制 SaaS 產品。
> 建立日期：2026-05-05

---

## 現況盤點

### 已完成的核心功能
- React 前端（持倉明細 / 資產配置 / 資產走勢 三個 Tab）
- FastAPI 後端
- 7 個 Connector：Bybit、OKX、MEXC、EVM 錢包（Alchemy）、SOL 錢包、IBKR、元大（PoC 階段）
- 歷史走勢 + Benchmark 比較（S&P 500、0050、BTC）

### 架構限制（產品化的天花板）

| 問題 | 影響 |
|------|------|
| SQLite 單一資料庫 | 多用戶並發讀寫會出問題 |
| API Keys 全部在 `.env` 檔案 | 無法讓不同用戶設定自己的帳戶 |
| 沒有 `user_id` 概念 | 所有資料混在一起，無法隔離 |
| `app/auth/` 目錄是空的 | Auth 尚未實作 |
| API baseURL 寫死 `localhost:8000` | 無法部署到生產環境 |
| 排程是本機 launchd | 多用戶後需要 server-side 排程 |
| 元大 connector 仍在 PoC 階段 | 尚未接入主系統 |

---

## Roadmap 總覽

```
Phase 0      Phase 1      Phase 2   Phase 3      Phase 4   Phase 5   Phase 6+
 ████         ████         ████      ████         ████      ████      ████
架構重構    Auth + 新UI    部署      連接器UI     CSV匯入   金流      擴充

 ████
UI Design ← 與 Phase 0 並行（不寫 code，出設計稿）

← 必須依序 ───────────────────────────────── →        ← 可並行/迭代 →
```

---

## Phase 0：架構重構
**優先度：最高 | 工期：2–3 週 | 必須完成才能推進後續**

這是最隱藏、最被低估的工程量。現在的系統是為「一個人用」設計的，要變成多用戶服務，底層必須先改。

### 0-A：資料庫從 SQLite 換成 PostgreSQL

SQLite 是單一檔案，多人同時讀寫會 lock，不適合生產環境。

新增 `user_id` 欄位到所有現有表：
- `normalized_holdings`
- `account_snapshots`
- `category_snapshots`
- `source_runs`
- `batches`

新增表：
```
users             （帳號資料：id, email, google_id, name, created_at）
user_connectors   （每個用戶設定哪些連接器 + 加密的 API Key）
subscriptions     （付費狀態：user_id, provider, external_id, status, current_period_end, cancel_at_period_end）
```

### 0-B：API Key 管理方式改變

現在：所有人的 API Key 都在 `.env`
之後：每個用戶的 API Key 加密後存在 `user_connectors` 表

```
user_connectors：
  user_id      → 屬於哪個用戶
  platform     → "bybit" / "okx" / "ibkr" ...
  credentials  → JSON，加密儲存（api_key, secret, passphrase 等）
  status       → active / error / syncing
  last_sync_at
```

### 0-C：清除技術債
- [ ] API `BASE_URL` 改成環境變數，移除 hardcoded `localhost:8000`
- [ ] 移除 Streamlit 舊版 Dashboard（`app/dashboard/main.py`）
- [ ] 元大 connector 完成 Gmail OAuth 接入主系統
- [ ] 排程從本機 launchd 改成 server-side（APScheduler 或 Railway Cron）

**完成條件：** PostgreSQL 跑起來、所有表有 user_id、本機能模擬兩個不同 user 的資料隔離

---

## Phase 0.5：UI Design Sprint（與 Phase 0 並行）
**優先度：高 | 工期：與 Phase 0 同步進行 | 不寫 code，純設計輸出**

Phase 0 是純後端/資料庫工作，前端不需要動。這段時間拿來完成設計稿，等 Phase 0 結束時設計也準備好，Phase 1 直接用新設計實作，不在舊 UI 上打補丁。

### 輸入資料（已備妥）
- `design-reference.html` — 現有 UI 靜態參考
- `FRONTEND_SPEC.md` — 現有功能完整規格
- `docs/product-roadmap.md` — 新版需要的頁面與功能清單

### 需要設計的頁面

| 頁面 | 說明 |
|------|------|
| Landing / Pricing | 對外說明功能、方案、CTA |
| 登入 / 註冊 | Google OAuth 登入流程 |
| Onboarding | 新用戶第一次設定引導（新增第一個連接器） |
| Dashboard（改版） | 現有三個 Tab 的視覺升級版 |
| 設定頁 | 連接器管理、帳戶資料、訂閱狀態 |
| 新增連接器 Wizard | 選平台 → 填資料 → 測試連線 → 完成 |
| CSV 匯入頁 | 上傳、預覽、確認流程 |
| 訂閱升級頁 | 方案比較、綠界付款頁入口 |

### 完成條件
設計稿涵蓋上述所有頁面，且主要互動流程（登入、新增連接器、CSV 匯入）有完整的 flow 可以參考。

---

## Phase 1：Auth + 新 UI 實作
**優先度：高 | 工期：2–3 週**

Phase 0 做完後，用 Phase 0.5 的設計稿直接重寫前端，同步接上 Auth。

### 技術選擇：Supabase Auth
- 免費額度：50,000 MAU
- 內建 PostgreSQL（可整合）
- 支援 Google OAuth 一鍵設定

### 需要做的事

**後端：**
- 每個 API endpoint 加上 token 驗證 middleware
- 所有查詢加上 `WHERE user_id = :current_user` 限制

**前端（依設計稿實作）：**
- 登入頁（Google 登入按鈕）
- 登入後導向 Dashboard
- 未登入時擋住所有 Tab
- Topbar 顯示用戶頭像 + 登出按鈕
- 設定頁骨架（連接器管理 UI 在 Phase 3 填入）

---

## Phase 2：部署到生產環境
**優先度：高 | 工期：1 週**

### 技術選擇

| 元件 | 推薦方案 |
|------|---------|
| 後端 + 前端 hosting | Railway 或 Render |
| 資料庫 | Supabase PostgreSQL |
| 域名 | 購買 `.com` |
| SSL | 平台內建，自動處理 |

### 需要做的事
- [ ] CI/CD 設定（推 code 自動部署，GitHub Actions）
- [ ] 環境變數改用平台 secret manager
- [ ] 基本監控（服務掛掉要收到通知）
- [ ] 排程改為 server-side

**里程碑：** 可以把網址給測試用戶，他能登入看到空的 Dashboard

---

## Phase 3：連接器管理 UI
**優先度：高 | 工期：2–3 週 | 讓用戶真正能「用起來」的關鍵**

### 設定頁設計

```
設定 > 我的帳戶 > 連接器

┌────────────────────────────────────────────┐
│ Bybit          ● 正常   上次同步 1h 前  [編輯][刪除] │
│ MetaMask       ● 正常   上次同步 2h 前  [編輯][刪除] │
│ IBKR           ✗ 失效   點擊重新設定               │
│                                                  │
│ [+ 新增帳戶]                                     │
└────────────────────────────────────────────┘
```

### 新增帳戶 Wizard
1. 選擇平台（Bybit / OKX / IBKR / 錢包地址 / ...）
2. 依平台類型填入資訊（API Key + Secret / 錢包地址 / IBKR Flex Token）
3. 測試連線
4. 確認，開始第一次同步

---

## Phase 4：CSV 匯入 / 歷史資料輸入
**優先度：中高 | 工期：2 週 | 解決新用戶冷啟動問題**

用戶剛加入時沒有歷史資料，折線圖是空的，體驗很差。

### 方式 A：CSV 批次匯入

標準格式：
```csv
date,platform,symbol,quantity,price_usd,category
2024-01-15,others,BTC,0.5,43000,crypto
2024-01-15,ibkr,AAPL,10,185.2,us_stock
2024-01-15,others,2330,1000,580,tw_stock
```
- 提供範本下載
- 上傳後預覽確認，錯誤行高亮
- 確認後批次插入

### 方式 B：手動逐筆輸入

- 選擇日期、來源（現有連接器 or Others）、類別、品種、數量、價格
- 適合補登少量歷史資料

---

## Phase 5：訂閱金流（綠界 ECPay）
**優先度：中 | 狀態：已上線，正式環境端到端驗證通過（2026-08-06）**

原訂 Stripe，因正式收款需台灣以外法律實體而改用綠界 ECPay（台灣本地）。PayPal 亦評估後放棄。

### 實際方案

單一方案，非 Free / Pro 分層：

```
訂閱（NT$50 / 月，AIO 定期定額信用卡）：
  - 每日自動跨平台紀錄資產變化
  - 細部持倉明細
  - 各項 benchmark 回測比較

未訂閱：
  - 不能新增來源（backend/routers/connectors.py:128）
  - 每日 batch 不跑（app/jobs/run_batch.py:60）
```

Gating 一律走 `app/services/entitlements.py` 的 `get_entitlement` / `is_active`，該層不認識任何金流商 —— ECPay、comp 白名單、`is_system` 都只是往 `subscriptions` 寫一個 `status`。

### 已完成
- [x] 綠界正式特店申請 + 信用卡收款服務審核通過
- [x] 後端 `/api/billing/checkout` → 組 AIO 定期定額參數 + CheckMacValue，前端隱藏 form POST 跳綠界付款頁（綠界禁 iframe，故非 redirect URL）
- [x] 兩個 callback 取代 webhook：`ReturnURL`（首刷）、`PeriodReturnURL`（第 2 期起每月），CMV 驗簽後寫 `subscriptions`
- [x] 每日對帳兜底：`reconcile_subscriptions()` 掛在 `/internal/trigger-batch` daily 最前，打 `QueryCreditCardPeriodInfo` 補漏掉的 callback
- [x] 取消訂閱：綠界無 Customer Portal，自建按鈕 → `CreditCardPeriodAction`（僅終止後續扣款，本期照常可用到期）
- [x] 前端訂閱區塊（`SettingsTab.tsx`）+ 免登入預覽頁 `/preview/settings`（送審用）
- [x] 功能 gate：新增來源、每日 batch

### 未決 / 已知問題
- [ ] `BILLING_ENFORCED` 尚未開啟 —— 開了會立刻斷掉 5 位無 subscription 的既有用戶，建議先 `grant_comp` 給他們當老用戶優待
- [ ] `BILLING_ENFORCED=false` 時 `get_entitlement` 在讀 `subscriptions` 前就短路，導致**已付費用戶前端仍顯示未訂閱、且無法取消**（`is_system` 那一半已於 PR #20 解掉）
- [ ] 定價 NT$50 硬編碼在 `SettingsTab.tsx`，未從 API 取；調價要同時改前端與 `ECPAY_PERIOD_AMOUNT`

---

## Phase 6+：上線後持續迭代

| 功能 | 重要性 | 說明 |
|------|--------|------|
| 更多台股券商 | 低 | 永豐、富邦、凱基等 |
| 更多交易所 | 低 | Binance connector 狀態待確認 |
| 行動版 RWD 優化 | 中 | 目前無響應式設計 |
| 資料導出（用戶下載自己的資料） | 中 | 建立用戶信任感 |
| 通知/警報 | 低 | 大幅波動 email 通知 |
| Sui wallet 完整實作 | 低 | 已有 connector 骨架 |
| 共享/公開 Portfolio | 低 | 讓用戶可以分享連結 |

---

## 時間線

| 週次 | Phase | 里程碑 |
|------|-------|--------|
| Week 1–3 | Phase 0 | 架構重構完成，本機多用戶測試通過 |
| Week 1–3 | Phase 0.5 | UI 設計稿完成（與 Phase 0 並行） |
| Week 4–6 | Phase 1 | 新 UI 上線 + Google 登入可用 |
| Week 7 | Phase 2 | 部署上線，可給測試用戶網址 ← **Alpha** |
| Week 8–10 | Phase 3 | 用戶可自行新增連接器 |
| Week 11–12 | Phase 4 | CSV 匯入可用 ← **Beta** |
| Week 13–14 | Phase 5 | 綠界 ECPay 訂閱上線 ← **正式收費** |
| Week 15+ | Phase 6+ | 持續迭代 |

---

## 最大風險

**Phase 0 是整個計劃最危險的地方。** 架構重構碰到的問題通常比預期多，且如果 Phase 0 做一半就推進 Phase 1，後面會非常痛苦。

**原則：Phase 0 做完，本機能模擬多用戶資料隔離之後，才推進 Phase 1。**

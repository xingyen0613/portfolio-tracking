# Portfolio Tracking

個人資產追蹤系統，整合 CEX（Binance、OKX、MEXC、Bybit）、EVM 多鏈錢包、Solana 錢包、SUI 鏈上錢包、IBKR 美股、Firsttrade 美股，以及元大證券（台股）資料，每日快照存入 SQLite。

## 文件

- [資料處理 Pipeline 說明](docs/data-pipeline.md) — 各平台從原始資料到 DB 的完整流程與儲存斷點

## 資料來源

| 平台 | 資料類型 | 方式 | 幣別 |
|------|---------|------|------|
| Binance | Spot + Earn（Flexible/Locked）+ Funding | ccxt API | USD |
| OKX | Spot + Savings | ccxt API | USD |
| MEXC | Spot + Futures（合約帳戶） | ccxt API | USD |
| Bybit | UNIFIED（現貨/衍生品）+ Funding | ccxt API | USD |
| EVM Wallet | 原生幣 + ERC-20 token（9 條鏈：ETH、BNB、Arbitrum、Optimism、Base、Avalanche、Polygon、Linea、Stable） | Alchemy RPC + CoinGecko | USD |
| Solana Wallet | SOL + SPL token | Helius RPC + CoinGecko | USD |
| SUI Wallet | Token 餘額 | Sui 公鏈 RPC + Pyth oracle | USD |
| IBKR | 美股持倉 + 現金（含負值保證金） | Flex Web Service API | USD |
| Firsttrade | 美股持倉 | 手動輸入（connector 待實作） | USD |
| 元大證券 | 台股每日淨資產（持股市值 + 擔保品 + 複委託 + 期貨權益 - 融資餘額） | 月對帳單 PDF 解析 | TWD |
| 手動輸入 | 不屬於台股/美股/幣圈的任意資產估值（不動產、保單、現金…），歸入「其他」類別 | 使用者自行上傳 CSV（`date, total_value`），匯入時選擇幣別 | USD / TWD |

## EVM 多鏈錢包 Pipeline

透過 Alchemy 自動探索每個地址下的 token 持倉，不需白名單：

- 設定：`ALCHEMY_API_KEY` 填入 `.env`；地址填入 `config/.env.wallets`（格式：`EVM_ADDRESS_<NAME>=0x...`）
- 每個地址可指定鏈（`EVM_CHAIN_<NAME>=eth`），預設跑所有 9 條鏈
- Token 自動探索 via `alchemy_getTokenBalances`；定價 via CoinGecko by contract address
- Stable chain（Stability Network）所有 token 固定 $1

## Solana 錢包 Pipeline

- 設定：地址填入 `config/.env.wallets`（格式：`SOL_ADDRESS_<NAME>=...`）
- 原生 SOL + 所有 SPL token 持倉自動抓取；定價 via CoinGecko
- `asset_type` 區分 `native`（SOL）與 `token`（SPL）

## IBKR 美股 Pipeline

IBKR 透過 Flex Web Service 每日自動抓取，與其他 CEX 平台一起走 `run_batch`：

- 持倉：OpenPosition（SUMMARY level）→ `normalized_holdings` asset_type=`stock`
- 現金：EquitySummaryByReportDateInBase.cash → asset_type=`cash`（保證金為負值）
- 設定：`IBKR_FLEX_TOKEN` 與 `IBKR_FLEX_QUERY_ID` 填入 `.env`

## Firsttrade 美股 Pipeline

Firsttrade 目前無 connector，持倉以手動方式寫入：直接 INSERT 進 `normalized_holdings` + `account_snapshots`，再呼叫 `_aggregate_categories()` 更新 `category_snapshots`。

## 元大台股 Pipeline

元大每月電子對帳單 PDF → 解析 → 日重建 → 收盤價抓取 → 每日淨資產 → 寫入主系統 DB

每月 5 日 cron 自動執行。需要手動觸發時：

```bash
# 一鍵執行（自動判斷哪些月份需要處理、哪些步驟可以 skip）
uv run python scripts/yuanta_run_pipeline.py

# 指定月份
uv run python scripts/yuanta_run_pipeline.py --month 2026-04

# 強制重跑（忽略所有 checkpoint）
uv run python scripts/yuanta_run_pipeline.py --force

# 確認會跑哪些步驟（不真的執行）
uv run python scripts/yuanta_run_pipeline.py --dry-run
```

#### Gmail PDF 下載（手動）

自動流程找不到 PDF 時，可以單獨觸發 Gmail 下載：

```bash
# 下載所有未下載的月份
uv run python scripts/yuanta_gmail_poc.py --fetch --all

# 只下載特定月份
uv run python scripts/yuanta_gmail_poc.py --fetch --month 2026-04

# 列出可下載的信件（不下載）
uv run python scripts/yuanta_gmail_poc.py --list --all
```

> **初次設定 Gmail OAuth**（只需做一次）：
> 1. GCP Console → 啟用 Gmail API → 建立 OAuth 2.0 Desktop 憑證
> 2. 下載 `credentials.json` → 放到 `.secrets/gmail_credentials.json`
> 3. 執行 `uv run python scripts/yuanta_gmail_poc.py --auth` 完成瀏覽器授權

- 收盤價只有交易日有值，非交易日 net_asset 存 `null`（不 forward-fill，留給前端處理）
- 幣別：TWD（不換算 USD，category_snapshots tw_stock 亦以 TWD 儲存）
- 股票代號自動解析：遇到 PDF 無代號的持股（如質押擔保品），自動查 TWSE/TPEX 官方清單，結果 cache 於 `data/derived/yuanta_poc/name_to_symbol_cache.json`

## 執行

> 所有指令都需要在專案根目錄執行：`cd /Users/yen/claude/Portfolio-Tracking`

### 資料抓取（Batch）

```bash
# 所有平台
uv run python -m app.jobs.run_batch

# 單一平台
uv run python -m app.jobs.run_batch --platform binance
uv run python -m app.jobs.run_batch --platform okx
uv run python -m app.jobs.run_batch --platform mexc
uv run python -m app.jobs.run_batch --platform bybit
uv run python -m app.jobs.run_batch --platform sui_wallet
uv run python -m app.jobs.run_batch --platform evm_wallet
uv run python -m app.jobs.run_batch --platform sol_wallet
uv run python -m app.jobs.run_batch --platform ibkr
```

### Dashboard（React + FastAPI）

Dashboard 為 React 前端 + FastAPI 後端，**開機自動啟動**（launchd 管理）。

瀏覽器開 `http://localhost:5173` 即可使用，不需要手動啟動任何指令。

每次開頁面都會從 SQLite 讀取最新資料。

> 首次安裝需先執行：`cd frontend && npm install`

---

### Dashboard（Streamlit，舊版，暫時保留）

```bash
uv run streamlit run app/dashboard/main.py --server.port 857
```

瀏覽器開 `http://localhost:857`

> ⚠️ 舊版 Streamlit Dashboard 目前仍可用，但後續維護以 React 版為主。是否永久移除待評估。

---

## 自動化設定

### 目前已設定的自動化

| 觸發方式 | 內容 |
|---------|------|
| 每天 23:00（cron） | `run_batch`（所有平台）+ benchmark 增量更新 |
| 每月 5 日 09:00（cron） | 元大 PDF pipeline |
| 開機自動（launchd） | FastAPI port 8000 + React dev server port 5173 |

### Cron（定時資料抓取）

#### 查看目前設定

```bash
crontab -l
```

#### 新增 / 修改排程

```bash
crontab -e
```

這會在終端機開啟 vi 編輯器，操作如下：

| 動作 | 按鍵 |
|------|------|
| 進入編輯模式 | `i` |
| 退出編輯模式（回到命令模式） | `Esc` |
| 儲存並退出 | `:wq` 再按 Enter |
| 不儲存退出 | `:q!` 再按 Enter |

#### 目前排程

```
# 每天 23:00 執行（所有平台 + benchmark）
0 23 * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1

# 每月 5 日 09:00 執行元大 PDF pipeline
0 9 5 * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python scripts/yuanta_run_pipeline.py >> data/logs/yuanta.log 2>&1
```

#### 其他常用排程範例

Cron 格式：`分 時 日 月 星期`

```
# 每小時整點執行
0 * * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1

# 每 6 小時執行（0:00、6:00、12:00、18:00）
0 0,6,12,18 * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1

# 只抓 SUI（較輕量，可以跑更頻繁）
0 * * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch --platform sui_wallet >> data/logs/cron.log 2>&1

# 元大台股（每月 5 號 09:00，自動判斷是否有新對帳單）
0 9 5 * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python scripts/yuanta_run_pipeline.py >> data/logs/yuanta.log 2>&1
```

#### 驗證設定是否生效

儲存後確認排程是否已寫入：

```bash
crontab -l
```

#### 確認是否有正常執行

每次 cron 執行後，log 會寫入 `data/logs/cron.log`：

```bash
# 查看最新幾行 log
tail -50 data/logs/cron.log

# 持續追蹤 log
tail -f data/logs/cron.log
```

成功執行的 log 會像這樣：

```
[Batch xxxxxxxx] Starting — 2026-04-13T15:00:00+00:00
Platforms: binance, okx, mexc, bybit, sui_wallet
  ✓ [binance/account_main] Success
  ✓ [okx/account_main] Success
  ✓ [mexc/account_main] Success
  ✓ [bybit/account_main] Success
  ...
[Batch xxxxxxxx] Done — status: success
```

如果 log 檔不存在或排程後沒有新記錄，可能原因：
- 電腦在排程時間關機或睡眠（cron 不會補跑）
- `data/logs/` 目錄不存在 → `mkdir -p data/logs`

---

### launchd（開機自動啟動 FastAPI + React）

launchd 是 macOS 原生服務管理器，讓服務在開機後自動在背景常駐。與 cron 無關，兩者並行：

| | cron | launchd |
|---|---|---|
| 用途 | 定時執行一次後結束 | 常駐服務，掛掉自動重啟 |
| 設定方式 | `crontab -e` | `~/Library/LaunchAgents/*.plist` |

目前管理兩個服務：

| plist 檔案 | 服務 | Port |
|-----------|------|------|
| `com.portfolio.dashboard.plist` | FastAPI 後端 | 8000 |
| `com.portfolio.frontend.plist` | React dev server | 5173 |

#### 確認狀態

```bash
launchctl list | grep portfolio
```

兩個都有 PID（不是 `-`）表示正常運行。

#### 停止 / 重啟

```bash
# FastAPI
launchctl unload ~/Library/LaunchAgents/com.portfolio.dashboard.plist
launchctl load   ~/Library/LaunchAgents/com.portfolio.dashboard.plist

# React frontend
launchctl unload ~/Library/LaunchAgents/com.portfolio.frontend.plist
launchctl load   ~/Library/LaunchAgents/com.portfolio.frontend.plist
```

#### 更新 plist 後重新載入

```bash
launchctl unload ~/Library/LaunchAgents/com.portfolio.dashboard.plist
cp /Users/yen/claude/Portfolio-Tracking/com.portfolio.dashboard.plist ~/Library/LaunchAgents/
launchctl load   ~/Library/LaunchAgents/com.portfolio.dashboard.plist
```

#### Logs

```
data/logs/dashboard.log        FastAPI stdout
data/logs/dashboard.error.log  FastAPI stderr
data/logs/frontend.log         React stdout
data/logs/frontend.error.log   React stderr
```

---

## 定價說明與已知近似值

### SUI Liquid Staking Token（LST）

以下 token 目前以對應底層資產價格計算，實際價值可能因質押收益略有差異：

| Token | 計價依據 | 說明 |
|-------|---------|------|
| vSUI | SUI 價格 | Volo 質押 SUI |
| xSUI | SUI 價格 | Aftermath 質押 SUI |

### SUI Token 過濾規則

SUI 鏈上 token 透過以下條件過濾垃圾幣：

1. **coin_type 必須在白名單（COIN_FEED_MAP）**：只收錄有對應 Pyth price feed 或已知穩定幣的 coin type
2. **USD value > $1**：低於門檻的持倉不計入

白名單以 coin_type address（非 symbol 字串）為 key，防止山寨幣偽造 symbol 混入。

### SUI 定價來源

| 類型 | 定價方式 |
|------|---------|
| 主流幣（SUI、ETH、BTC、USDT、USDC 等） | Pyth on-chain oracle（via Hermes 公共 API） |
| 已知穩定幣（BUCK、MUSD 等） | 固定 $1 |
| 其他 token | 過濾，不計入 |

### DeFi 倉位

目前版本尚未支援 DeFi 倉位查詢，待後續版本加入。

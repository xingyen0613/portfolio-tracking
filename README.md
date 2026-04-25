# Portfolio Tracking

個人資產追蹤系統，整合 CEX（Binance、OKX、MEXC、Bybit）、SUI 鏈上錢包、IBKR 美股、Firsttrade 美股，以及元大證券（台股）資料，每日快照存入 SQLite。

## 文件

- [資料處理 Pipeline 說明](docs/data-pipeline.md) — 各平台從原始資料到 DB 的完整流程與儲存斷點

## 資料來源

| 平台 | 資料類型 | 方式 | 幣別 |
|------|---------|------|------|
| Binance | Spot + Earn（Flexible/Locked）+ Funding | ccxt API | USD |
| OKX | Spot + Savings | ccxt API | USD |
| MEXC | Spot + Futures（合約帳戶） | ccxt API | USD |
| Bybit | UNIFIED（現貨/衍生品）+ Funding | ccxt API | USD |
| SUI Wallet | Token 餘額 | Sui 公鏈 RPC + Pyth oracle | USD |
| IBKR | 美股持倉 + 現金（含負值保證金） | Flex Web Service API | USD |
| Firsttrade | 美股持倉 | 手動輸入（connector 待實作） | USD |
| 元大證券 | 台股每日淨資產（持股市值 - 融資餘額） | 月對帳單 PDF 解析 | TWD |

## IBKR 美股 Pipeline

IBKR 透過 Flex Web Service 每日自動抓取，與其他 CEX 平台一起走 `run_batch`：

- 持倉：OpenPosition（SUMMARY level）→ `normalized_holdings` asset_type=`stock`
- 現金：EquitySummaryByReportDateInBase.cash → asset_type=`cash`（保證金為負值）
- 設定：`IBKR_FLEX_TOKEN` 與 `IBKR_FLEX_QUERY_ID` 填入 `.env`

## Firsttrade 美股 Pipeline

Firsttrade 目前無 connector，持倉以手動方式寫入：直接 INSERT 進 `normalized_holdings` + `account_snapshots`，再呼叫 `_aggregate_categories()` 更新 `category_snapshots`。

## 元大台股 Pipeline

元大每月電子對帳單 PDF → 解析 → 日重建 → 收盤價抓取 → 每日淨資產 → 寫入主系統 DB

```
Gmail 下載 PDF          scripts/yuanta_gmail_poc.py --fetch --all
PDF 解析                scripts/yuanta_pdf_parse_poc.py --batch
日持股重建              scripts/yuanta_daily_reconstruct_poc.py --batch
收盤價抓取（Yahoo）     scripts/yuanta_price_fetch_poc.py --batch
每日淨資產計算          scripts/yuanta_net_asset_poc.py --batch
寫入主系統 DB           scripts/yuanta_insert_poc.py --batch
```

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
uv run python -m app.jobs.run_batch --platform ibkr
```

### Dashboard

```bash
uv run streamlit run app/dashboard/main.py --server.port 857
```

瀏覽器開 `http://localhost:857`

每次開頁面都會從 SQLite 讀取最新資料，不需要重跑指令。

---

## 自動化設定

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

#### 常用排程範例

Cron 格式：`分 時 日 月 星期`

```
# 每天 23:00 執行一次（幣圈）
0 23 * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1

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

### launchd（Dashboard 開機自動啟動）

launchd 是 macOS 原生服務管理器，用來讓 Dashboard 開機後自動在背景跑。與 cron 無關，兩者並行：

| | cron | launchd |
|---|---|---|
| 用途 | 定時執行 batch | 開機啟動、常駐 dashboard |
| 設定方式 | `crontab -e` | `~/Library/LaunchAgents/*.plist` |

#### 初次設定

**Step 1：產生 plist 設定檔**（只需做一次）

```bash
cd /Users/yen/claude/Portfolio-Tracking

sed \
  -e 's|/YOUR_HOME|'"$HOME"'|g' \
  -e 's|/YOUR_PROJECT_PATH|'"$(pwd)"'|g' \
  com.portfolio.dashboard.plist.example > com.portfolio.dashboard.plist
```

確認內容是否正確（路徑應全部是絕對路徑）：

```bash
cat com.portfolio.dashboard.plist
```

**Step 2：安裝到 LaunchAgents**

```bash
cd /Users/yen/claude/Portfolio-Tracking

cp com.portfolio.dashboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.portfolio.dashboard.plist
```

> ⚠️ `cp` 指令必須在專案根目錄執行，或改用絕對路徑：
> ```bash
> cp /Users/yen/claude/Portfolio-Tracking/com.portfolio.dashboard.plist ~/Library/LaunchAgents/
> ```

**確認是否在跑：**

```bash
launchctl list | grep portfolio
```

有輸出（PID 不是 `-`）表示正在運行。

#### 停止 / 重啟

```bash
launchctl unload ~/Library/LaunchAgents/com.portfolio.dashboard.plist   # 停止
launchctl load   ~/Library/LaunchAgents/com.portfolio.dashboard.plist   # 啟動
```

#### 更新設定後重新載入

```bash
launchctl unload ~/Library/LaunchAgents/com.portfolio.dashboard.plist
cp /Users/yen/claude/Portfolio-Tracking/com.portfolio.dashboard.plist ~/Library/LaunchAgents/
launchctl load   ~/Library/LaunchAgents/com.portfolio.dashboard.plist
```

Dashboard log：`data/logs/dashboard.log`

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

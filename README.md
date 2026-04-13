# Portfolio Tracking

個人資產追蹤系統，整合 CEX（Binance、OKX）與 SUI 鏈上錢包資料，每日快照存入 SQLite。

## 資料來源

| 平台 | 資料類型 | API |
|------|---------|-----|
| Binance | Spot + Earn（Flexible/Locked） | ccxt |
| OKX | Spot + Savings | ccxt |
| SUI Wallet | Token 餘額 + DeFi 倉位 | BlockVision v2 |

## 執行

> 所有指令都需要在專案根目錄執行：`cd /Users/yen/claude/Portfolio-Tracking`

### 資料抓取（Batch）

```bash
# 所有平台
uv run python -m app.jobs.run_batch

# 單一平台
uv run python -m app.jobs.run_batch --platform sui_wallet
```

### Dashboard

```bash
uv run streamlit run app/dashboard/main.py --server.port 857
```

瀏覽器開 `http://localhost:857`

每次開頁面都會從 SQLite 讀取最新資料，不需要重跑指令。

---

## 自動化設定

### Cron（每日資料抓取）

目前設定每天 23:00 自動執行一次資料抓取。

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

在編輯模式下，貼上（或手動輸入）以下排程設定：

```
0 23 * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1
```

格式說明：`分 時 日 月 星期` — `0 23 * * *` 代表每天 23:00

#### 驗證設定是否生效

儲存後，確認排程是否已寫入：

```bash
crontab -l
```

應該可以看到剛才貼上的那行。

#### 確認是否有正常執行

每次 cron 執行後，log 會寫入 `data/logs/cron.log`：

```bash
# 查看最新幾行 log
tail -50 data/logs/cron.log

# 持續追蹤 log（等 23:00 跑完後觀察）
tail -f data/logs/cron.log
```

成功執行的 log 會像這樣：

```
[Batch xxxxxxxx] Starting — 2026-04-13T15:00:00+00:00
Platforms: binance, okx, sui_wallet
  ✓ [binance/account_main] Success
  ✓ [okx/account_main] Success
  ...
[Batch xxxxxxxx] Done — status: success
```

如果 log 檔不存在或 23:00 後沒有新記錄，可能原因：
- 電腦在 23:00 時關機或睡眠（cron 不會補跑）
- `data/logs/` 目錄不存在 → `mkdir -p data/logs`

### launchd（Dashboard 開機自動啟動）

launchd 是 macOS 原生服務管理器，用來讓 Dashboard 開機後自動在背景跑。與 cron 無關，兩者並行：

| | cron | launchd |
|---|---|---|
| 用途 | 定時執行 batch | 開機啟動、常駐 dashboard |
| 設定方式 | `crontab -e` | `~/Library/LaunchAgents/*.plist` |

**安裝 Dashboard 自動啟動：**

```bash
cp com.portfolio.dashboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.portfolio.dashboard.plist
```

**確認是否在跑：**

```bash
launchctl list | grep portfolio
```

**停止 / 重啟：**

```bash
launchctl unload ~/Library/LaunchAgents/com.portfolio.dashboard.plist   # 停止
launchctl load   ~/Library/LaunchAgents/com.portfolio.dashboard.plist   # 啟動
```

Dashboard log：`data/logs/dashboard.log`

## 定價說明與已知近似值

### SUI Liquid Staking Token（LST）

以下 token 目前以對應底層資產價格計算，實際價值可能因質押收益略有差異：

| Token | 計價依據 | 說明 |
|-------|---------|------|
| vSUI | SUI 價格 | Volo 質押 SUI |
| xSUI | SUI 價格 | Aftermath 質押 SUI |

### SUI Token 驗證規則

只有 BlockVision 標記 `verified: true` 且 `scam: false` 的 token 才會被記錄。
未驗證或被標記為詐騙的 token 一律過濾，不計入資產總值。

### DeFi 倉位

DeFi 倉位（借貸、LP、質押）若 BlockVision 無 USD 報價，由 Binance/OKX 市場價補充。
無法取得報價的倉位僅記錄數量，value 留空。

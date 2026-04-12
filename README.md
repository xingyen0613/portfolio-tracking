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

使用 `crontab -e` 查看或編輯排程（目前設定為每天 23:00 執行）：

```bash
crontab -l          # 查看現有排程
crontab -e          # 編輯排程
```

範例 crontab 設定：

```
0 23 * * * cd /Users/yen/claude/Portfolio-Tracking && /Users/yen/.local/bin/uv run python -m app.jobs.run_batch >> data/logs/cron.log 2>&1
```

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

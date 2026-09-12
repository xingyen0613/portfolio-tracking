# 通知系統涵蓋範圍

本文件說明 Portfolio Tracking 系統的主動通知機制：觸發情境、通知對象、訊息格式，以及明確標注 MVP 範圍外的項目。

---

## 通知對象

| 對象 | 管道 | 說明 |
|------|------|------|
| 系統管理員（xingyen0613） | Telegram Bot | 所有用戶的 batch 執行結果統一推播給管理員 |

> 用戶端 Telegram 綁定不在 MVP 範圍內。

---

## 觸發情境

### 1. Batch 執行結束（每次觸發）

每次 Cloud Scheduler 或手動觸發 batch 執行完成後，無論成功或失敗，皆發送一則通知。

**觸發位置：** `backend/routers/internal.py`（Cloud Scheduler 觸發）與 `backend/routers/admin.py`（手動觸發），兩者都跑在 Cloud Run 上。

> 本機 crontab 那條 `python -m app.jobs.run_batch` **不發任何通知**，它只跑 `SYSTEM_OWNER_ID`。

| 狀態 | 觸發條件 |
|------|---------|
| `success` | 所有 connector 全部執行成功 |
| `partial` | 部分 connector 失敗 |
| `failed` | 全部 connector 失敗，或 batch 本身 crash |

### 2. 雲端 batch 整條沒跑（本機守門員）

上面那則通知是「Cloud Run 活著才發得出來」。Cloud Run 整個掛掉時 Cloud Scheduler 打不進去，**一則通知都發不出來**——2026-08-30 → 09-10 GCP billing 停擺 12 天就是這樣靜默過去的。

`scripts/cloud_health_check.py` 從**本機 crontab**（獨立故障域）每天 09:00 檢查前一天：若 `category_snapshots` 沒有任何非 system 用戶的資料，就發 TG 警報。正常時完全安靜。

判準之所以成立，是因為本機那條 batch 只跑 `SYSTEM_OWNER_ID`，所以「有非 system 用戶的當日資料」= 雲端軌道確實動過。

檢查的是**前一天**而非當天：雲端 batch 實測 23:30 → 23:42 台北時間，到午夜只剩 13 分鐘餘裕，查當天容易誤報。

```
🔴 雲端 batch 沒有跑
2026-09-10 的 category_snapshots 沒有任何非 system 用戶資料（預期 5 位）。
Cloud Run 或 Cloud Scheduler 可能已停擺 — 請檢查 GCP billing 與服務狀態。
```

---

## 通知訊息格式

### 全部成功（daily job）

```
✅ Daily Batch 完成
平台：11/11 正常
用戶：6 位（5 位有來源 · 6 位訂閱中）
GCP 免費額度（9月已過 11/30 天）
• 本月已用：CPU 0.4% ｜ 記憶體 0.2% ｜ 請求 0.0%
• 依目前速率整月：CPU 13%
09/11 23:42 UTC+8
```

> 「用戶」與「GCP 免費額度」兩個區塊**只有 daily job 會帶**；admin / smoke / monthly_yuanta 維持精簡。
>
> 「本月已用」是這個月實際累積的量；「依目前速率整月」取**有流量那些日子的中位數** × 當月天數。刻意不用月均——剛發生停擺時月均會報出安心的 1%，而那正是最需要看準數字的時候。

### 部分失敗

```
⚠️ Daily Batch 部分失敗
成功：6/8 平台
失敗：
• binance — 認證失效（2 位用戶）
• ibkr — 連線超時（1 位用戶）
2026-06-01 23:30 UTC+8
```

### 全部失敗

```
🔴 Daily Batch 全部失敗
• binance — Connection refused
• okx — Rate limit exceeded
2026-06-01 23:30 UTC+8
```

---

## 錯誤分類

失敗訊息依 `error_message` 關鍵字自動分類：

| 類型 | 判斷關鍵字 | 顯示文字 |
|------|-----------|---------|
| 認證失效 | `401`, `403`, `Invalid API key`, `Authentication`, `Unauthorized`, `invalid signature` | 認證失效 |
| 連線問題 | `timeout`, `Connection refused`, `ConnectionError`, `ReadTimeout` | 連線超時 / 連線失敗 |
| 其他 | 其餘 | 執行失敗 |

---

## 環境變數

| 變數名稱 | 說明 |
|---------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token（由系統管理員提供） |
| `TELEGRAM_CHAT_ID` | 管理員的 Telegram chat ID |

> 未設定時系統不會 crash，僅記錄 warning log，通知功能靜默停用。
>
> **本機守門員也需要這兩個變數**（寫在本機 `.env`）。只設在 Cloud Run 的話，守門員偵測到異常時會印 `not set — skipping` 而不會真的發出警報。

---

## GCP 免費額度用量

`app/services/gcp_usage.py` 從 Cloud Monitoring 讀 Cloud Run 的用量，換算成免費額度佔比。

| 指標 | Cloud Run 指標名稱 | 每月免費額度 |
|------|------------------|-------------|
| CPU | `container/cpu/allocation_time` | 180,000 vCPU-s |
| 記憶體 | `container/memory/allocation_time` | 360,000 GiB-s |
| 請求數 | `request_count` | 2,000,000 |

來源：[Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features)（額度以每個帳單帳戶每月計）。

**認證**：project id 與 access token 都走 GCE metadata server，不需要任何金鑰。離開 Cloud Run（本機 cron、測試）時 `collect()` 回 `None`，呼叫端自動略過該區塊。Cloud Run 的預設 compute service account 已有 `roles/editor`，不需額外授權。

**成本**：零。Cloud Monitoring read API 的免費額度是每個帳單帳戶每月首 100 萬筆 time series，這裡一天 3 次。

**實作上的坑**（改動前務必先讀）：查詢用**每日 bucket 自行加總**，不要圖方便設一個涵蓋整月的 `alignmentPeriod`——alignmentPeriod 比 interval 長時，Monitoring API 會把窗口**往回擴張**，於是「本月至今」會回報成「近 31 天」。實測差了 20 倍（776 vs 15,843 vCPU-s）而且完全不報錯。

---

## MVP 範圍外（未實作）

以下情境目前不在通知涵蓋範圍內：

| 情境 | 說明 |
|------|------|
| 用戶端通知 | 各用戶自行綁定 Telegram 接收自己的失敗通知 |
| 資料新鮮度 | 某平台超過 N 天未成功 sync 時通知（整條 batch 沒跑已由本機守門員涵蓋） |
| 財務異常 | 資產總值單日大幅波動時通知 |
| 通知歷史 | DB 中記錄每筆通知的發送記錄 |
| 重複通知 cooldown | 同一錯誤在 24hr 內只通知一次 |
| Email 通知 | 目前僅支援 Telegram，不支援 Email |

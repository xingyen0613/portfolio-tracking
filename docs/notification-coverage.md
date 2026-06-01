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

**觸發位置：** `app/jobs/run_batch.py` → `run_batch()` 函數結束前

| 狀態 | 觸發條件 |
|------|---------|
| `success` | 所有 connector 全部執行成功 |
| `partial` | 部分 connector 失敗 |
| `failed` | 全部 connector 失敗，或 batch 本身 crash |

---

## 通知訊息格式

### 全部成功

```
✅ Daily Batch 完成
平台：8/8 正常
2026-06-01 23:30 UTC+8
```

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

---

## MVP 範圍外（未實作）

以下情境目前不在通知涵蓋範圍內：

| 情境 | 說明 |
|------|------|
| 用戶端通知 | 各用戶自行綁定 Telegram 接收自己的失敗通知 |
| 資料新鮮度 | 某平台超過 N 天未成功 sync 時通知 |
| 財務異常 | 資產總值單日大幅波動時通知 |
| 通知歷史 | DB 中記錄每筆通知的發送記錄 |
| 重複通知 cooldown | 同一錯誤在 24hr 內只通知一次 |
| Email 通知 | 目前僅支援 Telegram，不支援 Email |

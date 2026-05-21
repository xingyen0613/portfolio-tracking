# 測試指南

## 概述

本文件記錄無法從前端直接驗證的功能，以及對應的手動測試方式。

---

## 1. Admin Batch Trigger

### 用途
手動觸發資料擷取 batch，用於：
- 部署後立即驗證 Zeabur 環境是否正常
- 修改特定 connector 後針對性測試
- 不想等每日 UTC 15:30 排程

### Endpoint
```
POST /api/admin/run-batch
```

**環境 URL：**
- Zeabur（Production）：`https://allin-pt.zeabur.app`
- 本地開發：`http://localhost:8000`

**權限**：需要主帳號（SYSTEM_OWNER_ID）的 JWT token。

---

### 取得 JWT Token

**方式 A：本地 mint（推薦，不需瀏覽器）**
```bash
uv run python - <<'EOF'
from app.auth.jwt_utils import create_jwt
from config.settings import SYSTEM_OWNER_ID
print(create_jwt(SYSTEM_OWNER_ID))
EOF
```

**方式 B：從瀏覽器複製**
登入前端 → DevTools（F12）→ Network → 任意 `/api/` 請求 → Request Headers → `Authorization: Bearer <token>`

---

### Request Body

| 欄位 | 型別 | 預設 | 說明 |
|------|------|------|------|
| `platforms` | `list[str] \| null` | null（全部） | 指定要跑的平台，null = 全部已實作平台 |
| `user_id` | `str \| null` | null（全部） | 指定用戶，null = 所有 active 用戶 |
| `skip_benchmarks` | `bool` | false | true = 跳過基準價格更新（S&P500 / 0050 / BTC） |

---

### 重要：這不是 Dry Run

**所有測試都是真實執行，會實際寫入 DB。** 每次觸發都會：

1. 打指定平台的外部 API（IBKR / 交易所 / 鏈上 RPC）
2. 寫入 `account_snapshots`（今天的資產快照，重複執行會覆蓋當日資料）
3. 寫入 `source_runs`（本次執行紀錄）
4. 寫入 `batches`（batch 紀錄，有唯一 batch_id）
5. 更新 `category_snapshots`（各類別總資產聚合）
6. 更新 `user_connectors.last_sync_at`（connector 健康狀態）

**重複執行安全嗎？** 是。所有寫入都是冪等的（`ON CONFLICT DO UPDATE`），同一天跑多次只會覆蓋當日資料，不會重複累加。

---

### 常用測試組合

**快速驗證（~15 秒）— 部署後首選**

測試內容：IBKR Flex Web Service 連線 → 拉持倉 + 現金 → 寫入今日 account_snapshots
```bash
curl -s -X POST https://allin-pt.zeabur.app/api/admin/run-batch \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "platforms": ["ibkr"],
    "user_id": "00000000-0000-0000-0000-000000000001",
    "skip_benchmarks": true
  }' | python3 -m json.tool
```

**測試特定平台（改動某個 connector 後）**

測試內容：只跑指定平台，驗證 connector 邏輯改動是否正常
```bash
# 改動 sinopac 後
-d '{"platforms": ["sinopac"], "skip_benchmarks": true}'

# 改動 yuanta 後
-d '{"platforms": ["yuanta"], "skip_benchmarks": true}'
```

**測試所有加密貨幣交易所**

測試內容：binance / okx / mexc / bybit 各自 auth + 拉 spot balance → 寫入 account_snapshots
```bash
-d '{"platforms": ["binance", "okx", "mexc", "bybit"], "skip_benchmarks": true}'
```

**全量跑（同 scheduler，約 10-15 分鐘）**

測試內容：完整模擬每日排程，含所有平台 + 基準價格更新
```bash
-d '{}'
```
> ⚠️ 全量跑時間較長，建議只在確認各平台都正常時使用。HTTP 連線可能因 timeout 中斷，但 batch 仍會在後端繼續執行，可查 DB 確認最終結果。

---

### 預期回傳

```json
{
  "batches": [
    {
      "user_id": "00000000-0000-0000-0000-000000000001",
      "batch_id": "35497156-a271-4862-a3c4-6fa9df67b9d5",
      "status": "success"
    }
  ],
  "benchmarks_updated": false
}
```

`status` 可能值：`success` / `partial`（部分 connector 失敗）/ `failed` / `error: <訊息>`

---

### 查 DB 確認寫入

```bash
uv run python - <<'EOF'
from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, status, started_at, finished_at
        FROM batches ORDER BY started_at DESC LIMIT 5
    """)).fetchall()
    for r in rows:
        print(dict(r._mapping))
EOF
```

---

### 各平台預期執行時間

| Platform | 預估時間 | 備註 |
|---|---|---|
| ibkr | ~15s | IBKR Flex Web Service，穩定 |
| binance / okx / mexc / bybit | ~10-15s 各 | ccxt API |
| sinopac | ~30-60s | shioaji SDK 登入較慢 |
| yuanta | ~30s | Gmail OAuth 讀取對帳單 |
| evm_wallet | ~5-10 min | 多地址 × 多 chain，最慢 |
| sui_wallet / sol_wallet | ~30-60s | 依地址數量 |

---

## 2. 常見問題排查

### Batch status = "partial"
部分 connector 失敗。查 `source_runs` 找原因：
```bash
uv run python - <<'EOF'
from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT sr.status, sr.error_message, a.platform_id, a.account_key
        FROM source_runs sr
        JOIN accounts a ON a.id = sr.account_id
        WHERE sr.batch_id = '<your-batch-id>'
        ORDER BY sr.started_at
    """)).fetchall()
    for r in rows: print(dict(r._mapping))
EOF
```

### 清除殭屍 running batch
若 DB 有 `status = 'running'` 但已知失敗的 batch，手動修正：
```bash
uv run python - <<'EOF'
from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL
engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    conn.execute(text("""
        UPDATE batches SET status = 'failed', finished_at = NOW()
        WHERE status = 'running'
          AND started_at < NOW() - INTERVAL '1 hour'
    """))
    conn.commit()
    print("done")
EOF
```

---

## 未來待補

- [ ] Pricer smoke check：驗證 BTC / 台積電 / AAPL 報價是否合理
- [ ] Zeabur post-deploy 自動觸發（B 方案）

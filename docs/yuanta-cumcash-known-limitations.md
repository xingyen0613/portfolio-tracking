# 元大 cum_cash 與出入金限制（待優化）

## 背景

元大月對帳單只記載：
- 股票部位（自有 + 擔保品）市值
- 期貨權益（如有）
- 融資借款餘額
- 月內 transactions（股票交易）/ margin_transactions（融資、提前結算等）

**完全不記載：**
- 帳戶現金存款餘額
- 銀行 ↔ yuanta 的入金 / 出金

## 現行 net_asset 計算

依「有無擔保品（融資抵押）」分兩條路徑。`app/connectors/yuanta_connector.py:_write_month_to_db` 與 `scripts/yuanta_net_asset_poc.py` 都實作同一套邏輯。

### Path A：有擔保品（has_collateral=True）

```
net_asset = market_value + collateral + other_assets − margin_balance
```

**不加 cum_cash**：借款已反映在擔保品市值，加 cum_cash 會雙重計算。也**不做 anchor**。

### Path B：無擔保品（has_collateral=False）

```
net_asset = market_value + other_assets + cum_cash − margin_balance
```

需做月底 anchor 校準（見下），否則 cum_cash 會累積偏離。

| 項目 | 來源 |
|---|---|
| `market_value` | 自有股 + 擔保品（如有） × 每日價 |
| `other_assets` | parsed.json `summary.asset_categories` 非股票/非擔保品的項目，依 label 分類：期貨權益、複委託（海外有價證券）、其他 |
| `cum_cash` | transactions + margin_transactions 的 `net_cashflow` 累積，跨月承接 |
| `margin_balance` | parsed.json 月底借款餘額 |

處理三種雙重計算：
- `repay_via_sell`：賣股款直接還融資（扣，避免雙重）
- `advance_settlement_out`：T+0 提前結算（扣，跟 sell tx 重複）
- `advance_settlement_in`：歸帳事件（不動，已被 out 抵銷）

## 月底 anchor correction（Path B only）

每月最後交易日校正：
```
correction = yuanta_official_net_asset − pre_anchor_net_asset
```

把 correction 加進該日 `account_snapshots.total_value`、`yuanta_cash` row 的 value，並讓 `cum_cash += correction` 後傳遞給下月當起點。

對於沒有外部出入金的帳戶，correction 結構上會把 cum_cash 拉到 0；有出入金的帳戶則 correction 反映「沒被 PDF 記錄的轉帳金額」。

## 已知限制

對帳單沒出入金紀錄，也不記載「自有股票 → 複委託 / 期貨子帳戶」的內部轉帳，所以 anchor 把 cum_cash 強制拉到對齊 official，等於假設「月底以外的所有未記載金流」都發生在月底那一刻。

四種實際情境的處理：

| pre-anchor cum_cash | 真實原因 | 目前處理 | 影響 |
|---|---|---|---|
| **正 (+)** | 賣股 > 買股，款項離開 yuanta 視野（提現 / 漏抓 / 轉到複委託 / 轉到期貨等）| anchor 抵掉 | 月底 step down |
| **正 (+) 留在 yuanta 集保** | 賣股款放著沒花 | anchor 仍抵掉 | 真實現金被忽略 |
| **負 (−)** | 買股 > 賣股，需要外部現金支撐（入金或原有現金）| anchor 補上 | 月底 step up（默認補上）|
| **負 (−) 漏抓 asset** | parser 漏掉某 asset_category | anchor 補上 | 真實 net_asset 被低估 |

**典型範例（複委託情境）**：用戶在元大有自有股 + 複委託海外 ETF。每月把賣股款轉到複委託買美股，PDF transactions 只記股票交易（cum_cash 上升），但複委託買入是「海外有價證券」asset_category 的存量變化，沒進 transactions。月底 anchor 把多累積的 cum_cash 抵掉，曲線會出現 step down。

## Chart 上的觀察

trend 線在月底可能出現 step：
- step down：當月有賣股款「離開 yuanta 視野」（最常見：提現）
- step up：當月有外部入金（買股 > 賣股）

中間狀態（賣完股還沒買回）chart 在月內可能短暫偏高，月底 anchor 修正回 yuanta 對帳單值。

## 未來優化方案

### A. 接受現況（目前）
- 工作量：0
- 缺點：月底 step 看起來怪、報酬率計算可能微誤

### B. 校正分散到整月
- 把 month_end_correction 平均分到 30 天
- 工作量：30 分鐘
- 優點：chart 平滑無 step
- 缺點：把 step 改成「每天微漂移」也不真實

### C. 用戶手動補出入金紀錄（推薦）
- 新建 `yuanta_cashflows` table（user_id, date, amount, type=deposit/withdrawal, note）
- 前端 Sources / Settings 加 UI 讓用戶輸入歷史出入金
- cum_cash 計算加上手動 cashflows
- 工作量：~4 小時（schema + API + UI）
- 優點：根本解法，accurate
- 缺點：需用戶手動記錄

### D. Parse 元大「資金往來明細」頁
- 確認 yuanta 月對帳單有沒有這頁（部分券商有，部分沒有）
- 如果有 → 加 parser
- 工作量：~2 小時
- 優點：自動化
- 缺點：依 yuanta 對帳單格式而定

## 推薦執行順序

1. 先確認元大 PDF 是否有「資金往來明細」頁（D 路徑可行性）
2. 沒有 → 走 C（手動 UI）
3. 短期：接受 A，看用戶是否覺得 step 困擾

## 相關檔案

- `app/connectors/yuanta_connector.py:_write_month_to_db`：production connector，含 cum_cash 累積與月底 anchor 校準
- `scripts/yuanta_net_asset_poc.py`：等價的 PoC 實作，用於離線驗證
- `scripts/yuanta_backfill_from_db.py`：從 raw_payloads 重跑歷史月份（connector 邏輯改動時用）
- `backend/routers/holdings.py`：yuanta sections — 自有股 / 擔保品 / **複委託** / 期貨權益 / 其他資產 / 現金 / 融資

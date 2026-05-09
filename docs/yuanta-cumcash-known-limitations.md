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

```
net_asset = market_value + other_assets + cum_cash − margin_balance
```

| 項目 | 來源 |
|---|---|
| `market_value` | daily_holdings.json：自有 + 擔保品 × 每日價 |
| `other_assets` | parsed.json `summary.asset_categories`（期貨等）|
| `cum_cash` | transactions + margin_transactions 的 `net_cashflow` 累積 |
| `margin_balance` | parsed.json 月底借款餘額 |

`scripts/yuanta_net_asset_poc.py` 處理三種雙重計算：
- `repay_via_sell`：賣股款直接還融資（扣，避免雙重）
- `advance_settlement_out`：T+0 提前結算（扣，跟 sell tx 重複）
- `advance_settlement_in`：歸帳事件（不動，已被 out 抵銷）

## 月底 anchor correction

每月最後交易日校正：
```
correction = yuanta_official_net_asset − pre_anchor_net_asset
        = − cum_cash（結構上必然成立）
```

於是 cum_cash 月底永遠歸 0。

## 已知限制

對帳單沒出入金紀錄，所以 anchor 把 cum_cash 一刀切歸 0，等於假設「月底沒留現金、沒外部轉帳」。

四種實際情境的處理：

| pre-anchor cum_cash | 真實原因 | 目前處理 | 影響 |
|---|---|---|---|
| **正 (+)** | 賣股 > 買股，款項離開 yuanta 視野（提現 / 漏抓 / 移轉到期貨等）| anchor 強制歸 0 | 月底 step down |
| **正 (+) 留在 yuanta 集保** | 賣股款放著沒花 | anchor 仍歸 0 | 真實現金被忽略 |
| **負 (−)** | 買股 > 賣股，需要外部現金支撐（入金或原有現金）| anchor 強制歸 0 | 月底 step up（默認補上）|
| **負 (−) 漏抓 asset** | parser 漏掉某 asset_category | anchor 歸 0 | 真實 net_asset 被低估 |

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

- `scripts/yuanta_net_asset_poc.py`：cum_cash 計算與 anchor
- `scripts/yuanta_insert_poc.py`：寫進 account_snapshots
- `app/dashboard/data.py:get_yuanta_holdings_detail`：holdings 詳情
- `backend/routers/holdings.py`：四個 yuanta sections（自有/擔保品/期貨/融資）

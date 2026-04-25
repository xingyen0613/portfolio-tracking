# Portfolio-Tracking 專案規則

## 敏感檔案限制

**禁止讀取以下檔案，無論任何情況：**
- `.env`
- `.env.*`（包含 `.env.ibkr`、`.env.local` 等所有變體）

需要知道某個環境變數的 key 名稱時，讀 `.env.example` 即可。

## 文件

- [資料處理 Pipeline 說明](../docs/data-pipeline.md) — 各平台斷點設計、儲存位置、定價來源

## 架構決策

### 美股 category（us_stock）資料來源
- 歷史手動輸入的資料（backfill-manual batch）代表的是 **us_stock category 的總和**，不是單一平台的帳戶資料
- 這些手動資料存在 `category_snapshots`（歷史折線圖用），不應存在 `account_snapshots` 的任何單一平台下
- Firsttrade 目前沒有 connector，`account_snapshots` 中無任何 firsttrade 資料；手動新增持倉時直接寫入 normalized_holdings + account_snapshots
- IBKR 有正式 connector（`app/connectors/ibkr_connector.py`），每日 batch 自動抓取

### IBKR Flex Web Service
- 正確 endpoint：`ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService`
- 必須帶 `User-Agent: Python/3` header
- 兩步驟：SendRequest（q=query_id）→ GetStatement（q=reference_code，非 referenceCode）
- 持倉：OpenPosition levelOfDetail=SUMMARY；現金：EquitySummaryByReportDateInBase 最新 reportDate 的 cash 欄（可為負值）

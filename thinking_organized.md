# 個人資產管理系統規劃
## 第一階段：資料獲取層（Data Ingestion Layer）

## 1. 系統定位

本規劃文件目前只聚焦於整個資產管理系統中的「資料獲取層」。

這一層的核心任務是：
- 從不同平台穩定取得資產資料
- 保留原始資料（raw data）
- 轉成最小可用的結構化資料
- 形成每日可追溯的資產快照（snapshot）

這一層**不負責**的事情包括：
- 資產主檔統一
- 跨平台資產映射
- 完整帳務還原
- 報酬率、年化報酬、IRR、MDD 等計算
- 全域 base currency 統一換算
- 視覺化 dashboard 與分析報表

這些會屬於後續層級處理：
1. 資料處理層（Normalization / Processing Layer）
2. 資產映射與主檔層（Asset Mapping / Master Layer）
3. 帳務與事件層（Ledger / Event Layer）
4. 估值與價格層（Valuation / Pricing Layer）
5. 分析與指標層（Analytics Layer）
6. 展示與查詢層（Dashboard / Query Layer）

---

## 2. 最終目標與 MVP 範圍

### 最終目標
系統最終希望發展成「資產全景系統」，可以整合不同平台的持倉、歷史變化、後續估值、報酬與分析能力。

### MVP 範圍
第一階段先只做「資產快照系統」，也就是：
- 每日固定時間抓取各平台資產
- 記錄每個平台帳戶底下持有哪些資產
- 記錄數量、價格、估值與必要 metadata
- 保留歷史快照資料

後續再逐步加入：
- 入金 / 出金
- 買進 / 賣出
- 平台間轉帳
- 股利 / 利息 / 手續費
- 成本與報酬計算

---

## 3. 設計原則

### 3.1 模組化開發
系統採模組化開發，資料獲取層先獨立完成，避免一開始把價格、映射、報酬計算全部綁在一起。

### 3.2 Keep it simple
在資料收集階段，盡量保持簡單：
- 先把資料穩定拿進來
- 不急著做複雜計算
- 不在取得層做過多商業判斷
- 不強制先做全域統一幣別

### 3.3 Raw data 必須保留
所有來源都要保留原始資料，方便：
- debug
- parser 重跑
- 邏輯調整後重新 normalize
- 驗證與追溯

### 3.4 平台原始資訊優先保留
在資料獲取層，不先強行做資產統一與語意對齊，而是保留平台原始資料：
- 平台 symbol
- 平台 asset name
- 原始 quantity
- 原始 price / value
- 原始 currency

---

## 4. 第一階段資料範圍

### 4.1 納入的資料來源
目前規劃範圍包含：
- 美股：FirstTrade
- 台股：元大證券
- 加密貨幣交易所：Binance、OKX

### 4.2 暫緩的資料來源
- 鏈上 Wallet 模組先暫緩
- 未來可獨立成新模組處理

### 4.3 第一波優先順序
採分波段推進，不一次全做：

1. Binance
2. OKX
3. 元大
4. FirstTrade
5. Wallet（後補）

---

## 5. 資料模型主視角

### 5.1 主視角
系統以「平台帳戶」為主視角。

也就是：
- 第一層：平台 / 帳戶
- 第二層：帳戶底下的資產持倉

### 5.2 為何不用純資產視角
因為資料本身就是從不同平台抓取而來，先以平台帳戶為主比較符合來源結構，也方便後續對帳與 debug。

### 5.3 模型要求
資料模型從一開始就要支援：
- 多平台
- 多帳戶
- 多地址（未來 wallet 用）
- 同一平台多個帳戶

---

## 6. 快照設計

### 6.1 快照內容
每次快照不只存總資產，而是同時保存：
- 資產數量
- 當下價格
- 估值結果
- 報價時間
- 報價來源（若有）
- 幣別
- 平台原生估值（若有）

### 6.2 明細與彙總都存
每日快照同時保存兩類資料：

#### 明細快照
每個帳戶下每個資產一筆資料，例如：
- Binance / BTC / 0.1
- Binance / USDT / 500
- 元大 / 0050 / 3 張

#### 彙總快照
每個帳戶一筆彙總資料，例如：
- Binance 帳戶總值
- OKX 帳戶總值
- 元大帳戶總值

原則上：
- 明細為真實來源
- 彙總為衍生資料

### 6.3 納入現金與穩定幣
MVP 就要把下列內容納入正式資產：
- 券商現金餘額
- 交易所法幣餘額
- 穩定幣餘額
- 尚未投入的可用資金

---

## 7. 幣別與估值策略

### 7.1 不強制統一 base currency
資料獲取層先不做全域統一換算。

### 7.2 原幣別優先
目前採原幣別保存：
- 台股 / 元大：以 TWD 為主
- 美股 / FirstTrade：以 USD 為主
- 加密貨幣交易所：以 USD 為主

### 7.3 未來再擴充
若未來需要：
- 全域資產總額
- 跨幣別統一估值
- FX 換算
- 單一 base currency dashboard

則於後續 valuation / pricing layer 處理。

---

## 8. 資料取得策略

### 8.1 目標
目標是全自動直連。

### 8.2 優先順序
資料取得策略優先順序如下：
1. 正規 API / 官方介面
2. 網頁自動化
3. 檔案匯入
4. 手動補錄

### 8.3 實作原則
雖然目標是全自動，但架構上必須允許 fallback，避免單一來源卡住整體進度。

---

## 9. 價格與持倉的分工

### 9.1 核心原則
持倉與價格邏輯分離，但實務上允許保留平台原生估值。

### 9.2 在 MVP 中的做法
MVP 先採以下做法：
- Connector 抓 raw holdings
- 若平台有提供估值，一起保留
- 在 holdings snapshot 中存 price / value
- 但未來保留獨立 price module / price history 的空間

### 9.3 為何不急著獨立 price_history
因為第一階段重點是先把資料穩定收進來，而不是先建立完整價格服務。

---

## 10. 錢包模組策略

目前決策：
- Wallet 模組獨立
- 第一波先暫緩
- 未來若要做，再先從 wallet balance 開始
- 後續才擴充到 staking / LP / lending / vault

---

## 11. 排程與時間設計

### 11.1 每日固定排程
系統採每日固定時間排程抓取。

### 11.2 Batch 概念
每一天的一輪抓取任務視為一個 batch。

例如：
- 晚上 11:00 開始跑 Binance
- 11:01 跑 OKX
- 11:03 跑元大
- 11:05 跑 FirstTrade

這些雖然不是同一秒完成，但都屬於同一個 batch。

### 11.3 為何需要 batch
batch 用來：
- 把同一輪快照資料綁在一起
- 記錄哪些來源成功、哪些失敗
- 對應 raw、normalized、snapshot 的來源關係
- 讓每日快照具備一致性

---

## 12. 失敗處理策略

### 12.1 Batch 可部分完成
若某個來源失敗，不讓整個 batch 報廢。

### 12.2 策略
- 成功來源先寫入
- 失敗來源記錄 error 與 status
- batch 可為 partial success

### 12.3 好處
這樣可以最大化保留歷史資料，不會因為單一平台失敗導致整天資料全空。

---

## 13. 儲存方案

### 13.1 主資料庫
MVP 主資料庫採用 SQLite。

### 13.2 原因
SQLite 適合目前需求：
- 本地運行
- 結構化查詢方便
- 不需額外架服務
- 後續可升級到 PostgreSQL

### 13.3 Raw data 儲存
raw data 不只放在資料庫，也要保留成原始檔案。

原則：
- SQLite：存 metadata、normalized data、snapshot data
- 檔案系統：存 raw payload

---

## 14. Raw data 設計

### 14.1 核心原則
raw data 採分層保留，但 MVP 先做到：
- 完整 payload
- 必要 metadata

### 14.2 檔案分類原則
raw data 採「一次抓取，一個檔案」的方式保存。

不是：
- 一個平台永遠一個檔案
- 或每天只留一個大檔

而是：
- 每次 run 產生自己的 raw 檔案
- 方便追溯、debug、重跑 parser

### 14.3 建議檔案結構
```text
data/
  raw/
    2026-04-10/
      batch_20260410_230000/
        binance/
          account_main/
            balances_20260410T230102Z.json
        okx/
          account_main/
            balances_20260410T230201Z.json
        yuanta/
          account_main/
            holdings_20260410T230701Z.json
        firstrade/
          account_main/
            positions_20260410T230901Z.json
```
### 14.4 必要 metadata

每份 raw data 至少要記錄：
- batch_id
- platform
- account_id
- resource_type
- fetched_at
- file_path
- status
- payload_hash
- parser_status

### 14.5 Raw 不可變

raw data 視為原始證據，原則上不可修改。

---

## 15. Parser / Normalizer 版本管理

### 15.1 原則

同一份 raw data 未來可能會用不同 parser 重新解析，因此需要記錄版本資訊。

### 15.2 要記錄的內容
- parser_version
- normalizer_version

### 15.3 原則說明
- raw immutable
- parser 可更新
- normalized 結果可重建

---

## 16. Platform 與 Account 建模

### 16.1 分開建模

平台與帳戶要分開建模：
- platform：Binance / OKX / 元大 / FirstTrade
- account：各平台底下的實際帳戶

### 16.2 原因

這樣才能支援：
- 同平台多帳戶
- 多個 wallet address
- 未來帳戶擴充
- 更清楚的權責與資料關聯

---

## 17. 資產識別策略

### 17.1 本階段不做完整資產主檔統一

在資料獲取層，先不做完整的 asset master 與 mapping。

### 17.2 本階段只保留原始識別資訊

至少保留：
- platform_symbol
- platform_asset_name
- asset_type
- quantity
- price
- value
- currency

### 17.3 後續再處理

資產映射、alias、wrapped asset、跨平台同資產對齊，放到後續 processing layer。

---

## 18. 資產類型策略

### 18.1 資料獲取層做最小分類

先做最小可用分類，不建立完整金融分類體系。

### 18.2 建議分類
- cash
- stock / ETF
- crypto
- stablecoin
- wallet token
- unknown

### 18.3 原則
- 能分就分
- 分不出來就 unknown
- 不因分類不明而阻擋 ingest

---

## 19. Connector 介面設計

### 19.1 需要最小標準介面

每個 connector 都應遵守最小共同介面。

### 19.2 建議責任
- fetch_raw()
- store_raw()
- parse_minimal_holdings()
- report_status()

### 19.3 原則

先有共同 contract，但不要過度框架化。

---

## 20. Auth / Fetch / Ingest 分層

### 20.1 分層原則

第一版就要拆成三層：
- auth
- fetch
- ingest

### 20.2 職責

auth
- 讀取 .env
- 建立 API client / session
- 處理簽名、headers、token

fetch
- 呼叫平台 API
- 拿回 raw response

ingest
- 保存 raw payload
- 記錄 metadata
- 做最小驗證
- 輸出最小 normalized holdings

---

## 21. 設定與 secrets 管理

### 21.1 敏感資訊與一般設定分開

MVP 先採：
- .env：放 API key / session / secrets
- config 檔：放非敏感設定

### 21.2 非敏感設定可包含
- 啟用哪些平台
- 帳戶 alias
- 排程時間
- 資料路徑
- connector 開關

---

## 22. 驗證策略

### 22.1 Ingest 階段做最小驗證

只做技術正確性驗證，不做太多商業判斷。

### 22.2 最低限度驗證
- response 是否成功
- payload 是否存在
- 關鍵欄位是否存在
- quantity / price / value 是否可解析
- timestamp 是否合理
- account / platform / resource type 是否可識別

### 22.3 不在這層做的事
- 資產跳動合理性判斷
- 異常波動攔截
- 持倉是否符合預期
- 跨平台資產一致性檢查

---

## 23. 重跑與冪等性

### 23.1 原則

若同一天同平台重抓資料：
- raw payload 全部保留
- run 全部記錄
- normalized / snapshot 以最後一次成功結果為主

### 23.2 好處
- 可追溯
- 可 debug
- 查詢邏輯不混亂
- 保留重跑空間

---

## 24. 建議的核心資料表

以下為第一階段可考慮的核心資料表：
- platforms
- accounts
- batches
- source_runs
- raw_payloads
- normalized_holdings
- account_snapshots
- portfolio_snapshots（可先預留）

## 25. 建議專案結構
```text
project/
  app/
    auth/
    connectors/
    ingest/
    jobs/
    models/
    storage/
    utils/
  config/
  data/
    raw/
    sqlite/
  scripts/
  tests/
  .env
  README.md
```
## 26. 第一階段的完成定義

若第一階段完成，應至少達成：
1. 可在本地排程執行
2. 可接 Binance
3. 可接 OKX
4. 可保存 raw payload
5. 可把 raw 轉成最小 normalized holdings
6. 可形成每日 account snapshot
7. 可查到某一天某平台帳戶底下有哪些資產、數量與價格
8. 失敗來源不影響其他來源落地
9. 可重跑 parser
10. 資料結構可支援後續擴充元大、FirstTrade 與 wallet

---

## 27. 後續可執行項目

以下屬於下一步可執行的工作清單。

### 27.1 立即可做
1. 定義 SQLite schema
2. 定義 raw payload metadata schema
3. 定義 connector 最小介面
4. 建立專案目錄結構
5. 建立 .env 與 config 範本
6. 先完成 Binance connector MVP
7. 再完成 OKX connector MVP
8. 實作 batch / source run / raw ingest 流程
9. 實作每日排程 job
10. 產出第一版每日快照

### 27.2 第二波
1. 接入元大
2. 研究 FirstTrade 的自動化可行性
3. 加入 wallet module
4. 把價格模組逐步獨立
5. 補 portfolio_snapshot
6. 增加資料品質檢查

### 27.3 更後面的層
1. 資產 mapping / asset master
2. ledger / event 模組
3. 入金、出金、轉帳、買賣事件
4. 報酬率與年化報酬
5. FX 換算與全域 base currency
6. 歷史價格表
7. dashboard 與查詢介面

---

## 28. 總結

這一版規劃明確聚焦在「資料獲取層」，目標不是一次完成整個資產管理系統，而是先把最重要的底座搭起來：
- 來源可擴充
- raw 可追溯
- 快照可累積
- 結構可演進
- 後面要做計算、映射、分析時不用重做整套底層

目前最正確的開發順序不是先做分析，而是先把「穩定取得資料、保存 raw、形成每日快照」這件事做好。

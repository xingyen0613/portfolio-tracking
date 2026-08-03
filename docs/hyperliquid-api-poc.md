# Hyperliquid API PoC 與 Connector 設計

驗證腳本：`scripts/hyperliquid_poc.py`
Connector：`app/connectors/hyperliquid_connector.py`、`app/connectors/hyperliquid_history.py`

## API 基本事實（實測）

- Endpoint：`POST https://api.hyperliquid.xyz/info`，JSON body 以 `type` 欄位分流
- **查詢完全公開，不需 API key**，只要錢包地址（與 `sui_wallet` 同類，非交易所 key/secret 模式）
- Rate limit：**1200 weight/分鐘 per IP**（info 是 IP-based，address-based 只適用於 actions）
  - `clearinghouseState` / `spotClearinghouseState` 各 weight **2** → 等於每分鐘 600 次
  - 實測連打 30 次全 200，平均 110ms
- 無效的 `type` 回 **422**
- 所有數值以 **string** 回傳，需自行轉 float

用到的四個 type：

| type | 用途 | 關鍵欄位 |
|---|---|---|
| `clearinghouseState` | 永續帳戶 | `marginSummary.{accountValue,totalRawUsd,totalNtlPos}`、`assetPositions[]`、`withdrawable` |
| `spotClearinghouseState` | 現貨餘額 | `balances[]`：`coin`、`total`、`hold`、`entryNtl` |
| `spotMetaAndAssetCtxs` | 現貨定價 | `[meta, ctxs]`，`meta.universe[i]` 交易對對應 `ctxs[i].midPx` |
| `portfolio` | 歷史資產曲線 | 8 組 `[timestamp_ms, value]` 序列 |

## 淨值公式（關鍵，實測驗證）

```
accountValue = totalRawUsd + Σ sign(szi) × positionValue
```

在兩個各有 175 個未平倉部位的公開帳戶（HLP-A / HLP-B）上驗證，**差額 0.00000000**。

曾嘗試但**否定**的假設：`accountValue = totalRawUsd + Σ unrealizedPnl` —— 差了一百多萬。
原因：`totalRawUsd` 是**純現金**，開多會花掉現金換得部位、開空則收到現金而部位計負值，
因此部位項必須帶正負號，不能用未實現損益代替。

`positionValue` 以 `markPx` 計價，**本身已含未實現損益**。

## 未實現損益的記錄方式

需求是「未實現損益要能當獨立子分類，又要計入淨值」。直接把 `ΣuPnL` 當成一筆
holding 加總會**重複計算**（它已含在 `positionValue` 內）。因此拆成兩段：

```
perp_position.value = sign(szi) × positionValue − unrealizedPnl   ← 部位成本基礎
perp_upnl.value     = Σ unrealizedPnl                             ← 獨立子分類
```

兩者相加還原成 `Σ sign(szi) × positionValue`，故 holdings 總和精確等於
`accountValue`，與官網一致，同時未實現損益在 UI 上是獨立一列。

resource_type 對照：

| resource_type | 顯示名稱 | value |
|---|---|---|
| `spot` | 現貨 | `total × midPx` |
| `perp_cash` | 永續保證金 | `totalRawUsd` |
| `perp_position` | 永續部位 | `sign(szi) × positionValue − uPnL` |
| `perp_upnl` | 未實現損益 | `Σ unrealizedPnl` |

## 歷史回補

`portfolio` endpoint 回傳 8 組曲線：`day` / `week` / `month` / `allTime` 為**帳戶總值**
（現貨＋永續），`perpDay` 等四組為**僅永續**。回補採 `allTime`，因為只有它涵蓋一年範圍；
實測其尾值與 `clearinghouseState` + 現貨市值算出的總資產一致。

**取樣密度是 API 的先天限制**：`allTime` 約固定回傳 ~100 個點，帳戶越老間隔越稀，
且近期密、早期疏。實測某 75 天帳戶回補結果：

- 2026-07-03 之後：**每日一點**（32 天）
- 2026-07-03 之前：**每 7 天一點**（7 個點）
- 三年期帳戶的 `allTime` 中位間隔可達 14 天

官方另註明 portfolio 曲線在出入金時與每 15 分鐘取樣，
*"not recommended for precise accounting purposes"* —— 適合畫歷史折線圖，不適合當精算帳本。

**觸發時機**：僅在 `POST /api/connectors` 建立 hyperliquid connector 時跑一次
（`backend/routers/connectors.py`）。已存在的日期一律跳過；之後的每日數值由日常 batch 累積。

## 垃圾幣過濾

Hyperliquid 現貨有 481 個 token / 321 個交易對，絕大多數是 meme。以零地址
（`0x000...0`，公開黑洞地址）測試時，其持有的天量空投幣按官方報價可算出 **2 兆美元**
名目價值。因此 connector 設 `USD_THRESHOLD = 1.0`，低於此值視為粉塵過濾，
且無 USDC 計價對的 token 一律略過。

## 下單所需權限（僅記錄，本專案不使用）

交易類 action（下單/撤單/轉帳）需以 EIP-712 簽章，**必須持有私鑰**。
官網可產生 **API Wallet（agent wallet）**——獨立授權私鑰，能下單但**不能提幣**。
本專案只做唯讀查詢，不觸及任何簽章路徑，系統內不存私鑰。

# Sui 錢包資料來源比較

測試日期：2026-04-14  
測試地址：`0x655b10ed73bebf45a96e910ecfd159f276071b944dd1e84137bc22270e73119a`

---

## 方法一：BlockVision API（目前使用中）

**端點：** `https://api.blockvision.org/v2/sui`  
**需要 API key：** 是  
**免費額度：** 僅 30 次 request（已耗盡，不會重置，需升級 Pro）  
**測試腳本：** `scripts/blockvision/blockvision_test.py`  
**原始輸出：** `scripts/blockvision/raw/`（全為 HTTP 403）  
**測試結果：** ❌ 全部 403 — `"Your 30 trial requests have been used. The Sui Indexing API is available only to Pro-tier users."`

### 優點
- Token 有 `verified` / `scam` 標記，可自動過濾垃圾幣
- 回傳 `usdValue`，免接外部 price feed
- DeFi portfolio 端點（`/account/defiPortfolio`）可依協議查詢，直接拿到人類可讀的部位（symbol、balance、type）
- 資料已做 off-chain enrichment，開發成本最低

### 缺點
- 付費服務，免費額度少且不重置
- 有速率限制，大量批次查詢容易撞牆
- 依賴第三方可用性，若 BlockVision 掛掉會影響整個 pipeline

---

## 方法二：Sui 公鏈 RPC（直接打節點）

**端點：** `https://fullnode.mainnet.sui.io:443`  
**需要 API key：** 否（完全免費）  
**測試腳本：** `scripts/sui_rpc_test.py`  
**原始輸出：** `scripts/sui_rpc_output.json`

### 使用的 RPC 方法

| Method | 用途 | 回傳 |
|--------|------|------|
| `suix_getAllBalances` | 所有 coin 類型餘額匯總 | 132 種（含垃圾幣） |
| `suix_getAllCoins` | 每個 coin object 明細 | 分頁，50筆/頁 |
| `suix_getOwnedObjects` | 所有 Move objects（含 DeFi NFT）| 分頁，50筆/頁，hasNextPage: true |

### 優點
- 完全免費，無額度限制
- 資料直接來自鏈上，最即時、最權威
- 無第三方依賴

### 缺點
- **無垃圾幣過濾**：`getAllBalances` 回傳 132 種 coin，無 `verified` / `scam` 欄位，需自己維護白名單或串接 Sui coin registry
- **無 USD 價格**：只有 raw balance（最小單位整數），需另接 CoinGecko / CoinMarketCap / DEX price feed
- **DeFi 部位難以解析**：`getOwnedObjects` 回傳各協議的 position NFT（Move struct），欄位定義各協議不同，每個協議需單獨寫 decoder（Scallop、Navi、Suilend、Cetus、Bluefin... 各自一套）
- **分頁遍歷成本高**：一個地址可能有上百個 objects，需多次呼叫才能拿完整資料

---

## 方法三：Surflux NFT Indexing API

**端點：** `https://api.surflux.dev`  
**需要 API key：** 是  
**免費額度：** 有（credit 制，詳見 dashboard）  
**測試腳本：** `scripts/surflux/surflux_test.py`  
**原始輸出：** `scripts/surflux/raw/`（address_nfts.json、kiosk_nfts.json、summary.json）

### 使用的端點

| Endpoint | 用途 | 結果 |
|----------|------|------|
| `GET /nfts/address/{address}` | 地址持有的所有 Move objects | 50 筆（isLastPage: false，實際更多） |
| `GET /nfts/kiosk/{address}` | Kiosk 內的 NFT | HTTP 404（endpoint 路徑待確認） |

### 實際回傳的資料（測試地址）

這個端點雖然叫「NFT」，實際上索引了**所有 owned Move objects**，包含：

| object_type | 內容 | 可用欄位 |
|-------------|------|----------|
| `cetus::position::Position` | Cetus LP 流動性部位 | `pool`、`liquidity`、`coin_type_a`、`coin_type_b`、`tick_lower_index/upper_index` |
| `typus::vault::TypusDepositReceipt` | Typus 期權部位 | `vid`（vault id）、`index`、`metadata`（如 SUI-Daily-CappedCall） |
| `staked_wal::StakedWal` | Walrus 質押部位 | （見 raw） |
| 各種 NFT / receipt | 空投、會員證等 | `decoded_display.name`、`image_url` |

**關鍵優勢**：每個 object 回傳 `decoded_fields`（Move struct 自動解碼成 JSON）與 `decoded_display`（人類可讀名稱），**免自寫 Move struct decoder**。

### 優點
- `decoded_fields` 自動解碼 Move struct，不需要各協議的 parser
- `decoded_display` 提供協議名稱與描述（如 "Cetus LP | Pool23626-89"）
- 有 `created_at` / `updated_at` 時間戳，可追蹤部位異動
- 分頁設計清楚（`isLastPage`、`currentPage`）

### 缺點
- **無 token balance**：不查 coin 餘額，只查 Move objects
- **無 USD 價格**：`listed_value` 只適用於 Kiosk 上架的 NFT，DeFi 部位無價值估算
- **DeFi 部位量化需二次計算**：Cetus LP 有 `liquidity`，但換算成 token 數量需另打 pool 合約；Typus 期權只有 receipt index，無倉位價值
- **Kiosk 端點 404**：`/nfts/kiosk/{address}` 路徑待確認，可能需不同格式
- **索引有延遲**：非即時鏈上資料，有 checkpoint_id 標注，最新 `updated_at` 是近期但非 real-time
- **不含垃圾幣過濾**：本身不查 coin，此問題不適用

---

## 方法四：Birdeye

**端點：** `https://public-api.birdeye.so`  
**需要 API key：** 是（`https://bds.birdeye.so` 申請）  
**免費額度：** Standard 30,000 CU / 月，1 rps，**僅限特定 endpoint**  
**測試腳本：** `scripts/birdeye/birdeye_test.py`  
**原始輸出：** `scripts/birdeye/raw/`

### 測試結果

| Endpoint | 用途 | 結果 |
|----------|------|------|
| `GET /defi/price` | Token 價格 | ✅ SUI = $0.943（10 CU/次） |
| `GET /v1/wallet/token_list` | 錢包 token 列表 | ❌ 401 需付費方案 |
| `GET /v1/wallet/portfolio` | 錢包 portfolio | ❌ 401 需付費方案 |

### 優點
- Token price 免費可用，資料即時（SUI 原生支援，`x-chain: sui`）
- 有 `priceChange24h` 等市場資料

### 缺點
- **Wallet 功能需付費**：token list / portfolio 免費方案無法使用
- 對 portfolio tracking 用途而言，只能當 price feed，無法查持倉
- 免費方案僅 3 個 endpoint（未明列哪些）

---

---

## 最終決策

**採用：方法二（公鏈 RPC）+ Pyth oracle**

整合進 `app/connectors/sui_wallet_connector.py`（2026-04-14）。

| 組件 | 用途 | 實作位置 |
|------|------|---------|
| `suix_getAllBalances` | Token 餘額 | connector.fetch_raw |
| `suix_getCoinMetadata` | Symbol / decimals | connector.fetch_raw（module-level cache）|
| Pyth Hermes | USD 價格 | connector.fetch_raw |
| `COIN_FEED_MAP`（coin_type key） | 白名單過濾 + feed 對應 | connector 常數 |

過濾條件：coin_type 在白名單 AND USD value > $1

---

## 總結

| 維度 | BlockVision | 公鏈 RPC | Surflux | Birdeye |
|------|-------------|----------|---------|---------|
| 費用 | 付費（額度耗盡） | 免費 | 有免費 credit | 免費（price only） |
| Token balance | ✅ 完整 | ✅ raw（無過濾） | ❌ 不支援 | ❌ 付費才有 |
| Token 過濾 | ✅ verified 標記 | ❌ 需自建 | ❌ 不適用 | ❌ 付費才有 |
| USD 價格 | ✅ 內建 | ❌ 需另接 | ❌ 不支援 | ✅ 免費可用 |
| DeFi 部位識別 | ✅ 依協議解析 | ❌ raw bytes | ✅ decoded_fields | ❌ 不支援 |
| DeFi 部位估值 | ✅ 直接可用 | ❌ 需自算 | ❌ 需二次計算 | ❌ 不支援 |
| NFT 查詢 | ❌ 不支援 | ⚠️ 有但難辨識 | ✅ 強項 | ❌ 不支援 |
| 資料即時性 | 接近即時 | 鏈上即時 | 索引（有延遲） | 即時 |
| 第三方依賴 | 高 | 無 | 中 | 中 |
| 開發成本 | 低 | 高 | 中 | 低（price only） |

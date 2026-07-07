# 富邦證券（Fubon Neo API）PoC 調查紀錄

> PoC 分支：`feature/fubon-connector`　腳本：`scripts/fubon_poc.py`
> 目的：評估富邦新一代 API 能否接入 portfolio-tracking，以及產品化的憑證託管風險。
> 狀態：登入 + 帳務查詢實測通過（唯讀 API Key 路線）。

## 1. 可取得的資料

實測帳戶（唯讀 API Key + 憑證）跑過以下查詢，✅ 為已驗證回傳真實資料：

| 需求 | API | 結果 | 關鍵欄位 |
|--|--|--|--|
| 現金 | `accounting.bank_remain(acc)` | ✅ | `currency`、`balance`、`available_balance` |
| 部位（庫存）| `accounting.inventories(acc)` | ✅ | `stock_no`、`order_type`（現股/融資/融券/當沖/借券）、`today_qty`、`lastday_qty`、`tradable_qty`、`odd`（零股，含同結構欄位）|
| 部位損益+成本 | `accounting.unrealized_gains_and_loses(acc)` | ✅ | `stock_no`、`cost_price`、`today_qty`、`tradable_qty`、`unrealized_profit`、`unrealized_loss` |
| 交割款 | `accounting.query_settlement(acc, "3d")` | ✅ | 買賣金額、手續費、交易稅、`total_settlement_amount`；區間僅 `0d`/`3d` |
| 已實現損益 | `accounting.realized_gains_and_loses(acc)` / `_summary` | ✅ | 逐筆 / 彙總損益 |
| 負債/維持率 | `accounting.maintenance(acc)` | ⚠️ 權限未開 | 整戶 `margin_loan_amt`、`shortsell_margin`、`collateral`、`maintenance_ratio` + 逐檔明細 |
| 歷史成交 | `stock.filled_history(acc, start, end)` | ⚠️ 權限未開 | 長天期，**單次最多 30 天區間**（v2.1.1+）|
| 歷史委託 | `stock.order_history(acc, start, end)` | ⚠️ 權限未開 | 同上 |

⚠️ 三項回的是 API Key **權限未授權**（`Marketplace 權限錯誤` / `此 API KEY 未授權該功能`），功能存在，需到富邦後台把該把 key 的 scope 補開。

### 重要資料建模注意事項
- **零股**：實測持倉的整股 `today_qty=0`、股數在 `odd.lastday_qty`。connector 算部位時整股 + 零股（`odd`）要相加，不能只看 `today_qty`。
- **沒有「歷史每日資產淨值」API**：跟元大/永豐一樣，富邦只給「當下」快照。歷史資產曲線需靠本系統每日 batch snapshot 累積（沿用 `category_snapshots`/`account_snapshots`）。
- **市值**：`inventories` 不含現價。可用 `unrealized` 的 `cost_price + qty + profit/loss` 反推市值，或用 SDK 內建 `stock.query_symbol_snapshot` 取即時報價（免外接 pricer）。

## 2. 安裝與認證

- **`fubon-neo` 不在 PyPI**，是富邦官方平台專屬 `.whl` binary（[SDK 下載](https://www.fbs.com.tw/TradeAPI/docs/download/download-sdk)）。本機 macOS arm64 與部署 Linux x86_64 各一個。目前版本 **2.2.8**。
- 三種登入（皆需身分證作第一因子）：
  | 方法 | 參數 | 憑證 | 備註 |
  |--|--|--|--|
  | `login` | 身分證 + **電子平台密碼** + 憑證 + 憑證密碼 | 必要 | 全權限 |
  | `apikey_login` | 身分證 + **API Key** + 憑證 + 憑證密碼 | 必要 | **本專案採用**，可設唯讀 |
  | `apikey_dma_login` | 身分證 + API Key | 免 | ❌ 需另向營業員申請 DMA 權限，一般戶不可用 |
- 憑證預設密碼 = 身分證號（`scripts/fubon_poc.py` 於 `FUBON_CERT_PASSWORD` 留空時自動 fallback）。
- 憑證存放於 `.secrets/fubon/`（git 忽略，且 `.claude/CLAUDE.md` 列為禁止讀取）。

### 憑證躲不掉 —— 這是券商/法規限制，非 SDK 選型
- 富邦 API 分兩套：**行情 Web API**（大盤公開資料，REST，只要 key，不需憑證）與**帳務/交易**（你的私人帳戶，**只有 SDK、無 REST endpoint**，法規強制電子交易憑證）。
- 富邦開通交易 API 三步驟：開戶 → **電子交易憑證申請** → 簽署 API 使用聲明。憑證是開通時強制，屬金管會/證交所「不可否認性」要求（同永豐下單需 CA）。
- 手寫 Python 只能繞過「行情」，帳務資料換寫法一樣要憑證握手。

## 3. 產品化安全分析（憑證託管風險）

### 實測：憑證 + 身分證「單獨」無法登入
| 組合 | 富邦回應 |
|--|--|
| 真憑證 + 真身分證 + 假 API Key | ❌ `API認證，APIKEY尚未申請` |
| 真憑證 + 真身分證 + 空 API Key | ❌ `多因子認證資料輸入不完整` |

富邦定位為「多因子認證」，憑證+身分證只是兩個因子，缺第三因子（API Key 或密碼）進不去。

### 最壞情況：整個 DB 被拖走（憑證+身分證+唯讀Key 全洩）
| 攻擊者能否… | 結果 | 依據 |
|--|--|--|
| 查該用戶持倉/現金 | ⚠️ 可以（隱私洩漏）| — |
| 下單交易 | ❌ | 唯讀 key，伺服器實測會擋越權功能 |
| 出金領錢 | ❌（見殘留風險）| 需電子平台密碼+另驗證，出金限綁定銀行帳戶 |
| 建立新的可下單 key | ❌ | 建 key 需登入金鑰後台：身分證+**電子平台密碼**+**OTP 簡訊** |
| 改密碼 | ❌ | 同上 |

### 關鍵護城河
**最敏感的「電子平台密碼」不進系統。** `apikey_login` 只需身分證/API Key/憑證/憑證密碼，密碼從頭到尾不經手 → DB 外洩也拿不到能下單、能進金鑰後台的密碼。

### 建議防護層
1. **API Key 綁 IP 白名單**（鎖伺服器出口 IP）→ 三樣全洩，從別的 IP 也用不了（最強一層）。
2. 憑證+密鑰**加密儲存**（沿用系統現有 credentials 加密）。
3. API Key 設**僅查詢**權限；憑證有**效期**（約 1 年）、key **可隨時撤銷**。

### 殘留風險（待正式上線前確認）
- **出金能力**：無法從文件 100% 確認「API 是否可能出金 / 唯讀 key 是否徹底無此能力」。牽涉資金，上線前應請用戶或本方**直接向富邦書面確認**。
- 憑證有效期內三樣全洩 → 攻擊者可見持倉（隱私洩漏），但動不了資金；撤銷 key 即失效。

**結論**：走「唯讀 API Key + IP 白名單 + 不存電子平台密碼 + 加密儲存」，憑證託管屬**可控的隱私風險，非資金風險**。是否接入為商業/風險決策。

## 4. 待辦（若決定正式接入）
- [ ] 用戶到富邦後台補開 API Key 的 `maintenance`（維持率/負債）與歷史查詢 scope，再驗證這兩塊
- [ ] 向富邦確認出金風險（見殘留風險）
- [ ] 取得 Linux x86_64 `.whl` 供 GCP Cloud Run 部署
- [ ] 寫正式 `FubonConnector`（處理整股+零股相加、市值來源、多用戶憑證加密儲存）

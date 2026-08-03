# 元大證券 Spark API PoC

目標：用官方 API 直接查帳，取代目前「Gmail 抓 PDF 對帳單 → 解析」的元大流程
（`app/connectors/yuanta_connector.py` + `scripts/yuanta_pdf_parse_poc.py`）。

官方文檔：<https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/1.前言/1.簡介/index.html>

---

## 一、這個 API 能給我們什麼

只需三支唯讀帳務函式，就覆蓋目前 PDF 流程的全部欄位，而且**多補上兩塊 PDF 沒有的資料**：

| 函式 | 回傳 | 對應現況 |
|---|---|---|
| `GetStoreSummary(account, lng)` | 台股持倉（含 `MarketAmt` 市值、`ReturnAmt` 未實現損益）、國外股票持倉 | 取代 PDF 持倉解析；**市值由元大算好，不必再打外部查價**（同富邦作法） |
| `GetBankBalance(account, lng)` | `AvailableBalance` 銀行可用餘額 | **PDF 對帳單沒有這個欄位**，正是 `docs/yuanta-cumcash-known-limitations.md` 裡 cum_cash 推算誤差的根源 |
| `GetFutInterestStore(acct, '1', 'TWD', lng)` | 期貨 `TotalValue` 權益總值 | 取代目前從 `summary.asset_categories` 撈「期貨權益」的 workaround |

注意：**國外股票的 `MarketPrice` 官方固定回 0**，美股部位仍要自行查價。

---

## 二、實測結果（2026-07-31，macOS arm64）

| 項目 | 結果 |
|---|---|
| .NET 8 SDK + pythonnet 載入 `YuantaSparkAPI.dll` | ✅ 成功（DLL Version 2.2026.0713.0） |
| macOS arm64 原生支援 | ✅ 官方有 `YuantaSparkAPI_osx-arm64_Python.zip`，含 arm64 dylib |
| **UAT 測試環境連線** | ❌ **連不上**：`ystest.yuanta.com.tw` (220.130.122.92) 的 80/443 皆 timeout。符合文檔「測試環境需向營業員申請並提供固定 IP 做防火牆白名單」 |
| **PROD 正式環境連線** | ✅ **從本機直連成功**，socket handshake 完成（`IS_ServiceName:VM-YOAPI-P12`），**無 IP 白名單阻礙** |
| PROD 登入回應鏈路 | ✅ 用假帳號 `S00000000000` 探測，正常收到 `MsgCode=0112 無此權限使用此功能` —— 代表憑證載入、封包往返、`OnResponse` callback 全部正常，只差真帳密 |

結論：**技術路徑可行，正式環境不需要固定 IP，後續上 GCP Cloud Run 不必加 VPC Connector + Cloud NAT。**
（原本這是評估中最大的架構障礙。）

---

## 三、你要填的東西（只有這一步需要你動手）

### 1. 憑證檔

把元大官網「憑證專區」下載的**正式憑證 `.pfx`** 放進：

```
/Users/yen/claude/Portfolio-Tracking/.secrets/
```

這個目錄已在 `.gitignore`，不會進版控。檔名隨意。

> 若元大只給你 Windows 憑證安裝檔（`.exe` / 匯入到系統憑證存放區），
> 需要從「憑證管理工具」匯出成 `.pfx` 才能在 macOS/Linux 用——
> macOS/Linux 的 `Login()` 是直接吃 pfx 檔路徑，不讀系統憑證庫。

### 2. `.env` 加這幾行

（我不會讀你的 `.env`，請自己貼上並填值；欄位說明同 `.env.example`）

```bash
YUANTA_SPARK_ENV=PROD
YUANTA_SPARK_CERT_PATH=/Users/yen/claude/Portfolio-Tracking/.secrets/你的憑證.pfx
YUANTA_SPARK_CERT_PASSWORD=憑證密碼
YUANTA_SPARK_STOCK_ACCOUNT=S加分公司4碼加帳號7碼
YUANTA_SPARK_STOCK_PASSWORD=電子密碼
YUANTA_SPARK_FUT_ACCOUNT=
YUANTA_SPARK_FUT_PASSWORD=
```

- **帳號格式**：證券是 `S` + 分公司代號 4 碼 + 帳號 7 碼，共 12 字元（例 `S98875005091`）。
  分公司代號在對帳單或下單軟體上看得到。
- **密碼是「電子密碼」**，不是網銀或看盤軟體密碼。
- 期貨兩行沒有期貨戶就留空，PoC 會自動跳過。

### 3. 跑

```bash
uv run python scripts/yuanta_spark_poc.py
```

成功會印出每檔持倉的股數 / 市值 / 未實現損益、銀行餘額、期貨權益總值，
原始 JSON 寫到 `data/raw/yuanta_spark_poc/spark_<時間戳>.json`。

出錯時加 `YUANTA_SPARK_DEBUG=1` 重跑，`log/` 下會留完整封包紀錄。

---

## 四、環境準備（已經幫你做好，換機器才需要重做）

```bash
brew install dotnet@8                    # 已裝 8.0.127
uv pip install pythonnet==3.0.5          # 官方實測版本組合
```

官方元件包（62 MB，356 個檔案，已下載解壓，**不進版控**）：

```
vendor/yuanta_spark/YuantaSparkAPI_osx-arm64_Python/
```

其他平台下載網址（`docs` 頁沒列，是從產品頁 HTML 抽出來的）：

| 平台 | URL |
|---|---|
| macOS arm64 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_osx-arm64_Python.zip` |
| Linux x64（部署用） | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_linux-x64_Python.zip` |
| UAT 測試憑證 | `https://ys.yuanta.com.tw/quartet/api/B110000005_TWCA.zip`（密碼 `yuanta`） |

> 解壓時 `unzip` 會因為包內有 Big5 中文檔名的 PDF 而報錯，其餘 355 個檔案不受影響，可忽略。

---

## 五、寫 connector 前還要解掉的三件事

1. **Docker image 變大**：現有 `Dockerfile` 是 Python base，要接 Spark API 就得塞 .NET 8 + 62 MB 元件包。
   要嘛換 `mcr.microsoft.com/dotnet/sdk:8.0` 再裝 Python，要嘛在 Python image 裡裝 dotnet。
   若嫌重，另一條路是元大改走「每日在本機/固定機器跑、結果推 API」——但那等於退回現在的半自動狀態。
2. **多用戶登入限制**：單一帳號同時連線上限 10、登入 1000 次/日、帳務類 600 次/分。
   每日 batch 的量遠低於限制，但 connector 要確保 `LogOut()` + `Close()` 一定執行，別把連線用光。
3. **憑證怎麼存**：`user_connectors.credentials_json` 目前存的是文字型 key。
   元大要存 pfx，得比照富邦作法（base64 進 credentials，跑的時候寫 0600 暫存檔、用完刪除）。

---

## 六、API 行為備忘（實作時會踩的坑）

- **全非同步**：所有查詢函式只回 `bool`（送出成功與否），資料一律走 `OnResponse(intMark, dwIndex, strIndex, objHandle, objValue)` callback。
  PoC 已用 `queue.Queue` 把它同步化，不要照抄官方範例的 `time.sleep()`。
- **`dwIndex` 錯誤碼**：`3`=尚未登入、`9`=簽章失敗/憑證異常、`5`=功能權限不足。
- **登入成功碼有兩種**：`0001` 和 `00001` 都要當成功（官方範例自己也這樣判）。
- **語系一律傳 `enumLangType.UTF8`**，預設是 Big5，中文股名會變亂碼。
- **`namespace` 是 `YuantaOneAPI`**（不是 `YuantaSparkAPI`），但 `clr.AddReference` 要用 `"YuantaSparkAPI"`（組件檔名）。
- **`Open()` 是非同步的**，要等 `intMark=0, dwIndex=1` 的系統訊息才算連上。
- **盤前的 `MarketAmt`** 用開盤參考價計算，batch 執行時間要避開。
- 未實現損益明細（`GetUnrealizedGainLossDetail`）的 `Cost` 欄位在 Python 端無法直接屬性存取，
  官方範例是用 `System.Reflection.BindingFlags` 反射取值。本 PoC 沒用到這支。

---

## 七、參考

- 各 API 完整欄位表與官方原文範例：`docs/yuanta-spark-api-reference.md`
- 官方範例程式：`vendor/yuanta_spark/YuantaSparkAPI_osx-arm64_Python/YSendOrder.py`（95 KB，涵蓋所有功能）
- 現行 PDF 流程的已知限制：`docs/yuanta-cumcash-known-limitations.md`

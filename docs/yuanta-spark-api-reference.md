# 元大證券 Spark API — 唯讀帳務查詢 PoC 調查筆記

調查日期：2026-07-31
文檔站根目錄：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/`

> 說明：以下「原文程式碼」皆從文檔頁面直接擷取。程式碼區塊的縮排以 WebFetch 取回的 markdown 版本為準；
> 若要逐字元完全一致，建議實作時再開一次原頁面對照。**未經文檔佐證的 API 名稱與欄位一律標註「文檔未提及」。**

---

## 0. 完整文檔目錄（實際 href，供後續查證）

來源 URL：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/1.前言/1.簡介/index.html`（側邊選單）

Base = `https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/`

| 章節 | 路徑（相對 base，未 encode） |
|---|---|
| 前言/簡介 | `1.前言/1.簡介/index.html` |
| 前言/測試環境&正式環境說明 | `1.前言/2.測試環境&正式環境說明/index.html` |
| 前言/使用限制說明 | `1.前言/3.使用限制說明/index.html` |
| 前言/期貨報價代碼7xxx變更規則 | `1.前言/4.期貨報價代碼7xxx變更規則/index.html` |
| Python設定/Linux系統 | `2.Python設定/Linux系統/index.html` |
| Python設定/Windows、Mac系統 | `2.Python設定/Windows、Mac系統/index.html` |
| C#設定/環境建置-C# | `3.C#設定/環境建置-C#/index.html` |
| 基礎/API相關設定 | `基礎/API相關設定/index.html` |
| 基礎/連線與離線 | `基礎/連線與離線/index.html` |
| 基礎/登入 | `基礎/登入/index.html` |
| 基礎/回應事件 | `基礎/回應事件/index.html` |
| 基礎/物件 | `基礎/物件/index.html` |
| 基礎/列舉物件 | `基礎/列舉物件/index.html` |
| 帳務/股票庫存綜合總表 | `帳務/股票庫存綜合總表/index.html` |
| 帳務/期貨庫存總表查詢 | `帳務/期貨庫存總表查詢/index.html` |
| 帳務/國際期貨庫存總表查詢 | `帳務/國際期貨庫存總表查詢/index.html` |
| 帳務/期貨複式單庫存明細查詢 | `帳務/期貨複式單庫存明細查詢/index.html` |
| 帳務/未實現損益明細查詢 | `帳務/未實現損益明細查詢/index.html` |
| 帳務/已實現損益查詢 | `帳務/已實現損益查詢/index.html` |
| 帳務/沖銷明細查詢 | `帳務/沖銷明細查詢/index.html` |
| 帳務/銀行餘額查詢 | `帳務/銀行餘額查詢/index.html` |
| 帳務/交割款查詢 | `帳務/交割款查詢/index.html` |
| 帳務/期貨權益數查詢 | `帳務/期貨權益數查詢/index.html` |
| 帳務/期貨保證金最佳化查詢 | `帳務/期貨保證金最佳化查詢/index.html` |
| 回報（5 頁） | `回報/…/index.html` |
| 行情 / 交易 / 條件單 | 本次未抓（PoC 不需要） |

---

## 1. 前言 → 測試環境 & 正式環境說明

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/1.%E5%89%8D%E8%A8%80/2.%E6%B8%AC%E8%A9%A6%E7%92%B0%E5%A2%83%26%E6%AD%A3%E5%BC%8F%E7%92%B0%E5%A2%83%E8%AA%AA%E6%98%8E/index.html`

### 重點
- **測試環境需向營業員申請 API 權限並提供固定 IP** → 有 IP 白名單，且是走營業員人工開通。
- 公用測試帳號（文檔明示）：帳號種類 `S`、帳號 `98875005091`、密碼 `1234`、環境 `測試環境`。
  → 登入字串即 `S98875005091` / `1234`，`enumEnvironmentMode.UAT`。
- 測試憑證可下載匯入電腦使用（實際檔案見第 8 節）。
- 文檔警語：「測試環境使用屬加值服務，僅為提供客戶串接測試，**不保證穩定提供服務**」。
- `YuantaSparkAPI.dll` 元件：實作 `YuantaSparkAPITrader` 物件呼叫功能，可於宣告時指定 log 檔儲存位置。
- 正式環境：向營業員申請開通後即可連線。
  - 證券：種類 `S`，帳號格式 `4+7`，共 11 碼（分公司代號 4 碼 + 帳號 7 碼），密碼＝**電子密碼**。
  - 期貨：種類 `F`，帳號＋電子密碼。
  - 需至官網申請**正式憑證**。
- 正式環境警語：「正式環境為正式交易環境，透過API所送出的所有委託皆視為有效交易指令」。

### 原文（測試環境交易規則表，與唯讀帳務無關，僅存證）

| 委託條件 | 委託書號尾末碼 | 狀態 |
|--------|------------|------|
| ROD | 0, 5, A, K, U等 | 不成交 |
| ROD | 6, G, Q等 | 隨機成交 |
| ROD | 7, H, R等 | 限價單=>完全成交；市價單=>部分失效 |
| IOC | 0, 5, A, K等 | 價穩失效 |
| IOC | 6, G, Q等 | 成交一半 |
| FOK | 0, 5, A, K等 | 委託失敗 |
| 集合競價 | 4904市價/IOC/FOK | 不接受此類委託 |
| 價穩措施 | 5203市價/IOC/FOK | 價穩失效 |

---

## 2. 前言 → 使用限制說明（頻率限制）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/1.%E5%89%8D%E8%A8%80/3.%E4%BD%BF%E7%94%A8%E9%99%90%E5%88%B6%E8%AA%AA%E6%98%8E/index.html`

### 原文表格 — 單一連線使用限制

| 功能 | 商品/次數限制 |
|------|--------------|
| 已登入帳號重複呼叫登入作業 | 不允許 |
| 登入失敗後重新登入頻率 | 每4秒1次 |
| 不同FunctionID訂閱報價商品總數上限 | 2000 |
| 同FunctionID一秒內訂閱次數 | 10 |
| 同FunctionID單次訂閱商品數上限 | 200 |
| **同FunctionID一秒內報價/帳務類發送次數** | **3** |
| K線查詢一秒內發送次數 | 1 |
| 同FunctionID一秒內交易類發送次數 | 10 |
| 同FunctionID單次交易最多筆數 | 30 |
| 報價表查詢單次商品上限 | 600 |

### 原文表格 — 單一帳號使用限制

| 項目 | 商品/次數限制 |
|------|--------------|
| 同時最高連線數 | 10 |
| 登入數限制 | 1000次/日 |
| 總訂閱商品數 | 3000檔 |
| 行情類總呼叫數 | 1200次/1分鐘 |
| **帳務類總呼叫數** | **600次/1分鐘** |
| 交易類總呼叫數 | 3000次/1分鐘 |

> 原文：「**超過呼叫限制後**，系統暫停服務1分鐘並回傳錯誤訊息。**一小時內暫停達10次將停止該帳號API存取權限**。」

### 對 PoC 的意義
每日 batch 只跑幾支帳務查詢，離限制非常遠。真正的硬限制是**登入 1000 次/日**與**同時連線 10**——
多用戶架構下若每個用戶各自 login，注意不要在同一帳號上開太多 session。

---

## 3. 基礎 → API 相關設定

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/API%E7%9B%B8%E9%97%9C%E8%A8%AD%E5%AE%9A/index.html`

### 重點
只有兩個設定函式：`SetLogType`、`SetPMMServerCheck`。

| 函數 | 簽章 | 說明 |
|---|---|---|
| SetLogType | `void SetLogType(enumLogType logType);` | 設定 API Log 類別 |
| SetPMMServerCheck | `void SetPMMServerCheck(bool flag);` | 是否檢查 PMMServer。True=檢查(預設)；False=不檢查 |

### 原文程式碼

```python
objYuantaSparkAPI.SetLogType(enumLogType.COMMON)
```

```python
objYuantaSparkAPI.SetPMMServerCheck(false)
```

```csharp
objYuantaSparkAPI.SetLogType(enumLogType.COMMON);
```

```csharp
objYuantaSparkAPI.SetPMMServerCheck(false);
```

---

## 4. 基礎 → 連線與離線

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E9%80%A3%E7%B7%9A%E8%88%87%E9%9B%A2%E7%B7%9A/index.html`

### 重點
三個函式，全部無回傳值（void）：

| 函數 | 簽章 | 說明 |
|---|---|---|
| Open | `void Open(enumEnvironmentMode Mode);` | 開啟 API 連線 |
| Close | `void Close();` | 關閉 API 連線 |
| Dispose | `void Dispose();` | 釋放 API 連線 |

`Open()` 是**非同步**的：所有範例都在 `Open()` 之後 `time.sleep(2)` / `Thread.Sleep(1000)` 再 `Login()`。
連線結果從 `OnResponse` 的 `intMark=0` 系統訊息取得（`dwIndex=1` Connect / `2` Disconnect / `3` 網路異常 / `5` 未連線）。

### 原文程式碼

```python
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
objYuantaSparkAPI.Close()
objYuantaSparkAPI.Dispose()
```

```csharp
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT);
objYuantaSparkAPI.Close();
objYuantaSparkAPI.Dispose();
```

---

## 5. 基礎 → 登入（★ 關鍵）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E7%99%BB%E5%85%A5/index.html`

### 重點：**Windows 與 Linux/macOS 的 Login 簽章不同**

```
Windows:  bool Login(Account, Pass)
Linux:    bool Login(PfxPath, PfxPass, Account, Pass)
```

回傳 `bool`：`True` 執行成功；`False` 執行失敗（詳細結果從 `OnResponse` 事件接收）。

#### Input Parameters — Windows

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 登入帳號 | 證券：S + 分公司代號(4) + 帳號(7)，例 `S98875005091`；期貨：F + 分公司代號(7+3) + 帳號(7)，例 `FF021000P001234567` |
| Pass | string | 登入密碼 | |

#### Input Parameters — Linux（macOS 同此，見第 9 節）

| Name | Type | Description | Memo |
|------|------|-------------|------|
| PfxPath | string | Pfx 憑證路徑 | **絕對路徑** |
| PfxPass | string | Pfx 憑證密碼 | |
| Account | string | 登入帳號 | 同上 |
| Pass | string | 登入密碼 | |

#### Output Parameters

**LoginResult**

| Name | Type | Description |
|------|------|-------------|
| LoginStatus | Status | 登入狀態 |
| LoginList | List | 登入資料清單 |

**Status**

| Name | Type | Description | Memo |
|------|------|-------------|------|
| MsgCode | string | 訊息代碼 | `0000`: 執行失敗；`0001`: 執行成功；`0102`: 密碼凍結/未啟用；`0112`: 無權限 |
| MsgContent | string | 中文訊息 | |
| Count | Int | 筆數 | |

**LoginData**

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | 證券 `S98875005091`；期貨 `FF021000P001234567` |
| Name | string | 客戶姓名 | |
| InvestorID | string | 身分證字號 | |
| SellerNo | Short | 營業員代碼 | |

> ⚠️ 範例的 `on_response` 額外檢查 `strMsgCode == '0001' or strMsgCode == '00001'`——
> 實作時兩個都要當成功處理。

#### Logout

| 函數名稱 | Logout |
|---|---|
| 說明 | 登出先前透過 API 登入的所有帳號 |
| 語法 | `bool LogOut()` |

### 原文程式碼 — 引用元件（Python）

```python
import os, time, datetime, struct, pathlib, sys
from datetime import datetime
from pathlib import Path
from pythonnet import load

load("coreclr")
import clr, System

##透過Clr引用系統標準函式
clr.AddReference('System.Collections')
from System.Collections.Generic import List

##宣告增加模組、DLL的路徑(windows可抓取當前路徑 Linux跟MAC需指定路徑)
sys.path.append(Path(pathlib.Path(__file__).parent.resolve()))
if sys.platform == "win32":
    os.add_dll_directory(Path(pathlib.Path(__file__).parent.resolve()))

##透過Clr引用YuantaSparkAPI.dll
##pythonnet引用元件不用加附檔名
try:
    clr.AddReference("YuantaSparkAPI")
except Exception as e:
    print(f"Error loading YuantaSparkAPI: {e}")
from YuantaOneAPI import YuantaSparkAPITrader, enumLogType, enumEnvironmentMode
# 建立 API 物件
objYuantaSparkAPI = YuantaSparkAPITrader()
objYuantaSparkAPI.SetLogType(enumLogType.COMMON)
```

> 注意：**namespace 是 `YuantaOneAPI`，不是 `YuantaSparkAPI`**；`clr.AddReference` 用的才是
> `"YuantaSparkAPI"`（組件檔名，不加副檔名）。

### 原文程式碼 — OnResponse + 登入呼叫（Python）

```python
# 回應事件
def on_response(intMark, dwIndex, strIndex, objHandle, objValue):
    try:
        result = ''
        match intMark:
            case 0:  # 系統回應資訊
                result = str(objValue)
            case 1:  # 查詢回應資訊
                match strIndex:
                    case 'Login':
                        loginResult = objValue
                        status = loginResult.LoginStatus
                        strMsgCode = status.MsgCode # 訊息代碼
                        strMsgContent = status.MsgContent # 訊息內容
                        intCount = status.Count # 筆數
                        result = '{0},{1},帳號筆數:{2}\r\n'.format(strMsgCode,strMsgContent, str(intCount))
                        if strMsgCode == '0001' or strMsgCode == '00001' or intCount > 0 :
                            for i in objValue.LoginList:
                                result += f"{i.Account},{i.Name},{i.InvestorID},{i.SellerNo}\n"

        if result:
            print('##================================================##\n')
            print(result)

    except Exception as error:
        print(f"處理回應時發生錯誤: {error}")

objYuantaSparkAPI.OnResponse += on_response
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)

#證券 (ex:S+98xxxxxxxxx)
objYuantaSparkAPI.Login('S98875005091', '1234') 
time.sleep(2)

#期貨 (ex:F+ F021xxxxxxxxxxxxx)
#objYuantaSparkAPI.Login('FF0210132243219588', 'abcd123')
time.sleep(2)

#Linux/MAC登入 需帶入憑證絕對路徑與憑證密碼
#objYuantaSparkAPI.Login('/home/yuanta/YuantaSparkAPI_NET6_Python/B110000005_TWCA.pfx','yuanta','S98875005091', '1234')
#time.sleep(2)

# 保持程式運行
while True:
    time.sleep(1)
```

> ★ 這行是 Linux/macOS 登入的唯一原文範例，測試憑證密碼是 `yuanta`：
> `objYuantaSparkAPI.Login('/home/yuanta/YuantaSparkAPI_NET6_Python/B110000005_TWCA.pfx','yuanta','S98875005091', '1234')`

### 原文程式碼 — C# 登入

```csharp
using System;
using System.Text;
using System.Threading;
using YuantaOneAPI;

YuantaSparkAPITrader objYuantaSparkAPI = new YuantaSparkAPITrader();
string Account = "S98875005091";
string Password = "1234";
enumEnvironmentMode enumEvenMode = enumEnvironmentMode.UAT;

objYuantaSparkAPI.OnResponse += objApi_OnResponse;
objYuantaSparkAPI.SetLogType(enumLogType.ALL);

objYuantaSparkAPI.Open(enumEvenMode);
Thread.Sleep(1000);

objYuantaSparkAPI.Login(Account, Password);
Thread.Sleep(1000);
```

### 原文 Response Body

```json
{
  "Result": {
    "LoginStatus": {
      "MsgCode": "0001",
      "MsgContent": "執行成功!",
      "Count": 1
    },
    "LoginList": [
      {
        "Account": "S98875005091",
        "Name": "陳○○",
        "InvestorID": "B110000005",
        "SellerNo": "55"
      }
    ]
  }
}
```

---

## 6. 基礎 → 回應事件（callback 機制）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E5%9B%9E%E6%87%89%E4%BA%8B%E4%BB%B6/index.html`

### 重點：**全部是非同步 callback，沒有同步回傳資料的 API**

所有查詢函式只回傳 `bool`（送出成功與否），實際資料一律經由 `OnResponse` 事件送回。
註冊方式（Python，pythonnet 的 .NET event `+=` 語法）：

```python
objYuantaSparkAPI.OnResponse += on_response
```

事件簽章：
```
OnResponseEventHandler(intMark, dwIndex, strIndex, objHandle, objValue)
```

### 原文 Output Parameters

| Name | Type | Description | Memo |
|------|------|-------------|------|
| intMark | int | 回應類別 | 0: 系統資訊回應<br>1: 查詢資訊回應<br>2: 訂閱資訊回應 |
| dwIndex | uint | 回應狀態 | **intMark=0 時：**<br>0: 其他訊息<br>1: Connect<br>2: Disconnect<br>3: 網路異常<br>4: 需下載新版 API<br>5: 未連線<br>6: 系統公告<br><br>**intMark=1 時：**<br>0: 一般帳號/子帳號登入<br>3: 尚未登入<br>4: 登入帳號輸入錯誤<br>5: 功能代號錯誤或權限不足<br>6: 即時回報訂閱失敗<br>7: SocketRPRead 失敗<br>9: 簽章失敗/憑證異常<br>10: 已登出!<br>11: 帳號資訊異常<br>12: 取得已訂閱商品清單異常<br>其他: FunctionID（例 1E640A1F）<br><br>**intMark=2 時：**<br>1: 訂閱/取消訂閱失敗<br>其他: FunctionID（例 1E640A1F） |
| strIndex | string | 功能名稱 | 字串型 Function（例 SendStockOrder）<br>參考 FunctionList<br>若 strIndex 為空，代表功能查詢/訂閱錯誤，objValue 用字串格式解析 |
| objHandle | object | Handle 值 | 回傳觸發訂閱事件時所傳入的 Handle 值（不需處理） |
| objValue | object | 回傳資料 | 連線相關系統回應用字串格式解析<br>各功能回傳值依文件轉型解析<br>非功能對應表的功能用舊元件方式解析為 byte[] |

### 對 PoC 的意義（重要）
- **`dwIndex == 9`（簽章失敗/憑證異常）** 是憑證問題的判斷點。
- **`dwIndex == 3`（尚未登入）** 是「登入還沒完成就送查詢」的典型錯誤。
- Python 端要把 callback 結果收進一個容器（如 `queue.Queue` / `threading.Event`），
  再由主執行緒等待——所有官方範例都用土法煉鋼的 `time.sleep()` + `while True`。
- `strIndex` 就是查詢函式名（如 `'GetStoreSummary'`），用它做 dispatch。

---

## 7. 基礎 → 物件 / 列舉物件

### 來源 URL
- 物件：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E7%89%A9%E4%BB%B6/index.html`
- 列舉物件：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E5%88%97%E8%88%89%E7%89%A9%E4%BB%B6/index.html`

### 物件（共用結構）

**TYuantaDateTime**

| Field | Type | Description |
|---|---|---|
| struDate | TYuantaDate | 日期物件 |
| struTime | TYuantaTime | 時間物件 |

**TYuantaDate**

| Field | Type | Description |
|---|---|---|
| ushtYear | ushort | 西元年 |
| bytMon | byte | 月 |
| bytDay | byte | 日期 |

**TYuantaTime**

| Field | Type | Description |
|---|---|---|
| bytHour | byte | 小時 |
| bytMin | byte | 分鐘 |
| bytSec | byte | 秒鐘 |
| ushtMSec | ushort | 毫秒 |

> ⚠️ 不一致點：`基礎/物件` 頁定義 `TYuantaDateTime` 只有 `struDate`/`struTime` 兩層，
> 但 `期貨權益數查詢` 的 Python 範例直接用 `dateTime.Year / .Month / .Day / .Hour / .Minute / .Second / .Millisecond`（扁平）。
> 實作時兩種都要試，以實跑為準。

### 列舉物件

**enumEnvironmentMode 連線環境類別**
- `PROD` = 1 正式環境
- `UAT` = 2 測試環境

**enumLangType 語系**
- `Normal` = 0 Big5
- `UTF8` = 1 UTF8
- `SC` = 2 簡體中文

> PoC 建議一律傳 `enumLangType.UTF8`，避免 Big5 中文名稱在 Python 端變亂碼。

**enumLogType Log類別**
- `NONE` = 0 不記錄任何的LOG
- `System` = 1 紀錄一般Log & 排除訂閱即時回報/彙總
- `COMMON` = 2 紀錄一般Log
- `COMMON_WITH_QUOTE` = 3 紀錄一般Log & 特定行情Log
- `ALL` = 4 全部訊息都強制記錄

**enumMarketType 市場類別**
- `TWSE` = 1 上市
- `TWOTC` = 2 上櫃
- `TAIFEX` = 3 期貨
- `TWEMERGING` = 4 興櫃
- `TWSEODD` = 5 盤中零股-上市
- `TWOTCODD` = 6 盤中零股-上櫃
- `SGX` = 202 新加坡交易所
- `CME` = 203 芝商所CME Group
- `CBOT` = 204 芝商所原CBOT
- `TCE` = 205 東京商品 TOCOM
- `OSE` = 207 日本交易所JPX
- `HKFE` = 208 香港交易所
- `NYBOT` = 209 洲際-美國ICE-US交易所
- `LIFFE` = 210 洲際-英國ICE-UK交易所
- `XEUREX` = 211 歐洲交易所
- `ASX` = 212 澳洲交易所
- `CBOE` = 215 CBOE期貨交易所

---

## 8. 元件下載 / 申請流程 / 憑證

### 來源 URL
- 產品頁：`https://www.yuanta.com.tw/file-repository/content/API/page/index.html`
- 下載目錄（WebFetch 403，但 curl HEAD 可驗證檔案存在）：`https://ys.yuanta.com.tw/quartet/api/`

### 申請流程（原文轉述）
1. 簽署「應用程式介面(API)服務申請暨委託交易風險預告書」。
2. 下載 API 測試軟體，完成測試並上傳測試結果，然後「聯繫所屬營業員」開通 API。
3. 下載 API 元件開始交易。

**資格條件（Q1 原文）：**「申請元大SPARK API沒有財力或交易量門檻限制，只要是元大證券客戶即可提出申請」。
**測試環境需由營業員申請固定 IP 防火牆開通。**

### 元件下載連結（從產品頁 HTML `href` 抽出，實測 HTTP 200）

| 檔案 | URL | 驗證 |
|---|---|---|
| macOS **arm64** Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_osx-arm64_Python.zip` | HTTP 200, 61,504,871 bytes, Last-Modified 2026-07-13 |
| macOS x64 Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_osx-x64_Python.zip` | 列於頁面 |
| **Linux x64** Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_linux-x64_Python.zip` | HTTP 200, 62,949,139 bytes, Last-Modified 2026-07-13 |
| Linux arm64 Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_linux-arm64_Python.zip` | 列於頁面 |
| Windows x64 Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_win-x64_Python.zip` | 列於頁面 |
| Windows x86 Python 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_win-x86_Python.zip` | 列於頁面 |
| C# 元件 | `https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_CSharp.zip` | 列於頁面 |
| **測試憑證** | `https://ys.yuanta.com.tw/quartet/api/B110000005_TWCA.zip` | HTTP 200, 6,723 bytes, Last-Modified 2026-06-30 |
| 舊元件（COM / Delphi / WPF，僅維護） | `YuantaOneAPI_Com.zip` / `YuantaOneAPI_Delphi.zip` / `YuantaOneAPI_WPF.zip` | 列於頁面 |
| API 測試軟體（Windows 安裝檔） | `https://ys.yuanta.com.tw/Quartet/APITest/setup.exe` | 列於頁面 |
| 版本歷程 PDF | `https://ys.yuanta.com.tw/quartet/api/YuantaApiHis.pdf` | 列於頁面 |

> 產品頁原文：「新功能僅限 Python/C#」，COM/Delphi/WPF 僅維護不新增功能。

### 憑證
- **正式環境**：使用元大證券官網「憑證專區」下載的正式憑證。
- **測試環境**：測試憑證 `B110000005_TWCA.zip`（解開後為 `B110000005_TWCA.pfx`，範例中密碼 `yuanta`）。
- **Windows**：憑證匯入到當前帳號的 Windows 憑證存放區，安裝密碼 `yuanta`（測試憑證）；
  `Login(Account, Pass)` 不帶憑證路徑。
- **Linux / macOS**：憑證不匯入系統，改由 `Login(PfxPath, PfxPass, Account, Pass)` 直接傳 pfx 絕對路徑 + 密碼。

---

## 9. 平台可行性（macOS arm64 / Linux x86_64 / .NET）

### 來源 URL
- Linux 建置：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/2.Python%E8%A8%AD%E5%AE%9A/Linux%E7%B3%BB%E7%B5%B1/index.html`
- Windows/Mac 建置：`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/2.Python%E8%A8%AD%E5%AE%9A/Windows%E3%80%81Mac%E7%B3%BB%E7%B5%B1/index.html`

### (a) macOS arm64 — **可行**
- 官方明確提供 `YuantaSparkAPI_osx-arm64_Python.zip`（curl HEAD 實測 HTTP 200，61.5 MB，2026-07-13 更新）。
- Windows/Mac 文檔的 macOS 專節原文重點（逐條）：
  - 使用 `load("coreclr")` 載入 .NET Core / 8 執行環境。
  - 「設定 DLL 路徑（**macOS 需指定路徑**）」→ `os.add_dll_directory(指定的絕對路徑)`。
  - 「調整登入寫法：**macOS 需指定讀取的憑證才能登入**，路徑請填寫絕對路徑。」
  - 「於範例程式資料夾開啟終端機畫面」、「macOS 環境需輸入 Python 版本（`python3`）」。
  - 「請確保所有元件與主程式（`YSendOrder.py`）位於同一目錄或指定路徑。」
- 文檔**沒有**特別區分 Intel Mac 與 Apple Silicon 的使用說明；區分只體現在下載檔名（osx-arm64 vs osx-x64）。
- 元件名稱一律叫 `YuantaSparkAPI.dll`（.NET 8 managed assembly，非平台原生 `.so`/`.dylib`），
  跨平台差異在包內附帶的 native runtime。**文檔中沒有出現 `.so` / `.dylib` 檔名。**

### (b) Linux x86_64 部署 — 需要 .NET **SDK** 8
原文（Ubuntu 24.04）：

```bash
sudo apt update
sudo apt upgrade -y
```

```bash
sudo apt-get install dotnet-sdk-8.0
```
> 原文備註：Ubuntu 24.04 已不支援 .NET 6。

```bash
sudo apt install python3
sudo apt install python3-pip
python3 –version
pip3 --version
```

因 PEP668 限制，需建虛擬環境：
```bash
sudo apt install python3.12-venv
python3 -m venv myenv
source myenv/bin/activate
```

```bash
pip install pythonnet
```

**官方實測通過版本組合：**
- Python 3.12.3
- Pythonnet 3.0.5
- Dotnet 8.0.112
- Openssl 3.0.13

> Docker 部署建議：base image 用 `mcr.microsoft.com/dotnet/sdk:8.0`（文檔裝的是 SDK 不是 runtime；
> 保守起見先照文檔用 SDK，之後再試能否降成 `aspnet`/`runtime` image），另裝 python3 + pythonnet，
> 並把 `YuantaSparkAPI_linux-x64_Python.zip` 解開的元件放進去。
> 注意 openssl 版本（3.0.13）——pfx 憑證讀取常卡在 OpenSSL 3 的 legacy provider 問題，需實測。

### (c) 登入是否需要憑證以外的東西 — **不需要**
- `Login()` 的參數就只有：**憑證路徑 + 憑證密碼 + 帳號 + 密碼**（Linux/macOS），Windows 更少（帳號 + 密碼）。
- **文檔中沒有任何 OTP / 簡訊驗證碼 / 二次驗證的欄位或流程。**
- 「簽署」是**開通階段**的紙本流程（風險預告書），不是每次登入要做的事；
  API 內部的簽章由憑證處理（失敗時 `OnResponse` 的 `dwIndex=9`「簽章失敗/憑證異常」）。
- 額外的行政前置：向營業員申請 API 權限、提供**固定 IP** 給防火牆白名單（測試環境明文要求）。
  → ⚠️ 這對雲端部署是風險：Cloud Run 出口 IP 需要用 VPC Connector + Cloud NAT 固定住。

### 常見錯誤（原文備註）
- 未安裝 .NET SDK；安裝 .NET 8 以下版本也會出錯，建議 8.0 以上。
- 未安裝 pythonnet 套件。
- Python 無法正確找到 .NET → 刪除 `C:\Program Files\dotnet` 重裝；或加環境變數 `DOTNET_ROOT=C:\Program Files\dotnet\`。
- 「Python 語言的數字型別為 int（整數）、float（浮點數）。故使用各項功能傳遞參數時，
  若非文件說明為浮點數型別，請以 int 型別傳遞。」

---

## 10. 帳務 → 股票庫存綜合總表（★ PoC 主力）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E8%82%A1%E7%A5%A8%E5%BA%AB%E5%AD%98%E7%B6%9C%E5%90%88%E7%B8%BD%E8%A1%A8/index.html`

### 函式
```
bool GetStoreSummary(Account, lng)
```
回傳 `bool`：`True` 執行成功；`False` 執行異常（結果從 `OnResponse` 接收）。

### Input Parameters

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | 證券: S+分公司代號(4)+帳號(7)，例 `S98875005091`。註1 |
| lng | enumLangType | 語系 | 預設 `Normal`；Normal:Big5 / UTF8:UTF8 / SC:簡體中文 |

> 註1：**限證券使用**

### Output — StoreSummaryResult

| Name | Type | Description |
|------|------|-------------|
| StkStoreList | List\<StkStore\> | 現貨庫存清單 |
| OVStkStoreList | List\<OVStkStore\> | 國外股票庫存清單 |

### Output — StkStore 現貨庫存物件（原文）

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | |
| TradeKind | Int | 交易種類 | 0:現股 / 3:資買 / 4:券賣 / 6:借券 |
| MarketNo | enumMarketType | 市場代碼 | 參考列舉物件-市場類別 |
| MarketName | string | 市場名稱 | 上市/上櫃 |
| StkCode | string | 股票代號 | |
| StkName | string | 股票名稱 | |
| StockQty | Long | 股數 | |
| Price | double | 成交均價 | |
| Cost | double | 持有成本 | |
| Interest | Long | 預估利息 | |
| BuyNotInNos | Int | 買進未入帳股數 | |
| SellNotInNos | Int | 賣出未入帳股數 | |
| TradingQty | Long | 可交易股數 | |
| Loan | Long | 資保證金/券擔保價品 | |
| TaxRate | double | 交易稅率 | 0:Reits 股票 / 1:基金,認股權證,債券,存託憑證 / 3:一般股票(單位千分之一) |
| LotSize | Int | 交易單位 | 每手股數 |
| MarketPrice | double | 市價 | **盤前市價若為0則給開盤參考價** |
| Decimal | Int | 小數位數 | +為小數位數 / -為分數分母 / 0為整數 |
| StkType1 | Int | 屬性1 | Bit1:管理商品 Bit2:交易記號 Bit3:受益憑證 Bit4:ETF商品 Bit5:權證記號 Bit6:特別股 Bit7:存託憑證 Bit8:外國股票 |
| StkType2 | Int | 屬性2 | Bit1:可轉換公司債 Bit2:附認股權公司債 Bit3:警示股 Bit4:指數記號 Bit5:期貨 Bit6:個股選擇權 Bit7:指數選擇權 Bit8:保留 |
| BuyPrice | double | 買價 | |
| SellPrice | double | 賣價 | |
| UpStopPrice | double | 漲停價 | |
| DownStopPrice | double | 跌停價 | |
| PriceMultiplier | uint | 計價倍數 | 1，乘1倍 / 10，乘10倍 |
| CurrencyType | string | 幣別 | TWD / CNY / HKD / USD |
| CDQTY | Long | 借貸股數 | |
| OddTradingQty | Long | 零股可下單股數 | |
| **ReturnAmt** | double | **未實現損益** | |
| **MarketAmt** | double | **股票市值** | |

### Output — OVStkStore 國外股票庫存物件（原文）

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 現貨帳號 | |
| CurrencyType | string | 幣別 | USD:美元 / HKD:港幣 |
| MarketNo | enumMarketType | 市場代碼 | 參考列舉物件-市場類別 |
| MarketName | string | 市場名稱 | |
| StkCode | string | 股票代號 | |
| StkName | string | 股票名稱 | |
| StkFullName | string | 股票全名 | |
| StockQty | Long | 庫存股數 | |
| TradingQty | Long | 可交易股數 | |
| Price | double | 成交均價 | |
| Cost | double | 持有成本 | |
| CloseRate | double | 匯率 | |
| RateKind | Int | 匯率運算模式 | 1:除以匯率 / 2:乘以匯率 |
| LotSize | int | 交易單位 | 每手股數 |
| MarketPrice | double | 市價 | **固定為0,前端自行根據登入權限查詢** |
| Decimal | Int | 小數位數 | +為小數位數 / -為分數分母 / 0為整數 |
| BuyPrice | int | 買價 | |
| SellPrice | int | 賣價 | |

> ⚠️ **國外股票的 MarketPrice 固定為 0**，市值要自己另外查價。台股 `StkStore` 則直接給 `MarketAmt`（市值）
> 與 `ReturnAmt`（未實現損益），不需外部查價——對 Portfolio-Tracking 是好消息（和富邦一樣可以不打外部查價）。
> 但 `MarketAmt` 在盤前可能用開盤參考價，跑 batch 的時間點要注意。

### 原文程式碼 — Python OnResponse

```python
# 回應事件
def on_response(intMark, dwIndex, strIndex, objHandle, objValue):
    try:
        result = ''
        match intMark:
            case 0:  # 系統回應資訊
                result = str(objValue)
            case 1:  # 查詢回應資訊
                match strIndex:
                    case 'Login':
                        loginResult = objValue
                        status = loginResult.LoginStatus
                        strMsgCode = status.MsgCode # 訊息代碼
                        strMsgContent = status.MsgContent # 訊息內容
                        intCount = status.Count # 筆數
                        result = '{0},{1},帳號筆數:{2}\r\n'.format(strMsgCode,strMsgContent, str(intCount))
                        if strMsgCode == '0001' or strMsgCode == '00001' or intCount > 0 :
                            for i in objValue.LoginList:
                                result += f"{i.Account},{i.Name},{i.InvestorID},{i.SellerNo}\n"
                    case 'GetStoreSummary':
                        sResult = objValue
                        stkList = sResult.StkStoreList
                        OVstkList = sResult.OVStkStoreList
                        result += '股票庫存綜合總表:\n'
                        # 現貨庫存
                        result += f'現貨庫存筆數:{stkList.Count}\n'
                        for i in range(stkList.Count):
                            result +='{0},{1},{2},{3},{4},{5},{6},{7}\r\n'.format(int(stkList[i].TradeKind),str(stkList[i].MarketNo),stkList[i].StkCode,stkList[i].StkName,stkList[i].StockQty,stkList[i].Price,stkList[i].ReturnAmt,stkList[i].MarketAmt)
                        #所有欄位資料太多印不出來
                        """ result += '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14} {15},{16},{17},{18},{19},{20},{21},{22},{23},{24},{25},{26},{27},{28},{29}\r\n'.format(
                            stkList[i].Account,str(stkList[i].TradeKind),str(stkList[i].MarketNo),stkList[i].MarketName,stkList[i].StkCode,stkList[i].StkName,str(stkList[i].StockQty),str(stkList[i].Price),str(stkList[i].Cost),
                            str(stkList[i].Interest),str(stkList[i].BuyNotInNos),str(stkList[i].SellNotInNos),str(stkList[i].TradingQty),str(stkList[i].Loan),float(stkList[i].TaxRate),str(stkList[i].LotSize),float(stkList[i].MarketPrice),
                            int(stkList[i].Decimal),int(stkList[i].StkType1),int(stkList[i].StkType2),float(stkList[i].BuyPrice),float(stkList[i].SellPrice),float(stkList[i].UpStopPrice),float(stkList[i].DownStopPrice),
                            str(stkList[i].PriceMultiplier),stkList[i].CurrencyType,str(stkList[i].CDQTY),str(stkList[i].OddTradingQty),float(stkList[i].ReturnAmt),float(stkList[i].MarketAmt)) """
                        # 國外現貨庫存
                        result += f'國外現貨庫存筆數:{OVstkList.Count}\n'
                        for i in range(OVstkList.Count):
                            result += '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13} {14},{15},{16},{17}\r\n'.format(
                                OVstkList[i].Account,OVstkList[i].CurrencyType,str(OVstkList[i].MarketNo),OVstkList[i].MarketName,OVstkList[i].StkCode,OVstkList[i].StkName,OVstkList[i].StkFullName,str(OVstkList[i].StockQty),
                                str(OVstkList[i].TradingQty),str(OVstkList[i].Price),str(OVstkList[i].Cost),str(OVstkList[i].CloseRate),int(OVstkList[i].RateKind),str(OVstkList[i].LotSize),float(OVstkList[i].MarketPrice),
                                int(OVstkList[i].Decimal),str(OVstkList[i].BuyPrice),str(OVstkList[i].SellPrice))
        if result:
            print('##================================================##\n')
            print(result)
    except Exception as error:
        print(f"處理回應時發生錯誤: {error}")

objYuantaSparkAPI.OnResponse += on_response
#測試環境帳號:UAT 正式環境:PROD
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)
objYuantaSparkAPI.Login('S98875005091', '1234')
time.sleep(2)
#股票庫存綜合總表
objYuantaSparkAPI.GetStoreSummary('S98875005091')
# 保持程式運行
while True:
    time.sleep(2)
```

### 原文程式碼 — C#

```csharp
objYuantaSparkAPI.GetStoreSummary(Account);
Thread.Sleep(2000);
```

```csharp
if (strIndex == "GetStoreSummary")
{
    var result = (StoreSummaryResult)objValue;
    strResult += "庫存綜合總表筆數: " + result.StkStoreList.Count + "\r\n";
    result.StkStoreList.ForEach(x =>
    {
        strResult += $"{x.Account},{x.TradeKind},{x.MarketNo},{x.MarketName},{x.StkCode},{x.StkName},{x.StockQty},{x.Price},{x.Cost},{x.Interest},{x.BuyNotInNos},{x.SellNotInNos}," +
            $"{x.TradingQty},{x.Loan},{x.TaxRate},{x.LotSize},{x.MarketPrice},{x.Decimal},{x.StkType1},{x.StkType2},{x.BuyPrice},{x.SellPrice},{x.UpStopPrice},{x.DownStopPrice}," +
            $"{x.PriceMultiplier},{x.CurrencyType},{x.CDQTY},{x.OddTradingQty},{x.ReturnAmt},{x.MarketAmt}\r\n";
    });
    strResult += "國外股票庫存筆數: " + result.OVStkStoreList.Count + "\r\n";
    result.OVStkStoreList.ForEach(x =>
    {
        strResult += $"{x.Account},{x.CurrencyType},{x.MarketNo},{x.MarketName},{x.StkCode},{x.StkName},{x.StkFullName},{x.StockQty},{x.TradingQty},{x.Price},{x.Cost},{x.CloseRate}," +
            $"{x.RateKind},{x.LotSize},{x.MarketPrice},{x.Decimal},{x.BuyPrice},{x.SellPrice}\r\n";
    });
```

> 註：`股票庫存綜合總表` 頁面**沒有**提供 JSON Response Body 範例（其他帳務頁多半有）。

---

## 11. 帳務 → 期貨庫存總表查詢

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E6%9C%9F%E8%B2%A8%E5%BA%AB%E5%AD%98%E7%B8%BD%E8%A1%A8%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetFutStoreSummary(Account, lng)
```

### Input Parameters

| Name | Type | Description |
|------|------|-------------|
| Account | string | 帳號。格式 F + 分公司代號(7+3) + 帳號(7)，例 `FF021000P001234567` |
| Lng | enumLangType | 語系。Normal(Big5) / UTF8 / SC；預設 Normal |

### Output — FutStoreSummaryResult

| Name | Type | Description |
|------|------|-------------|
| FutStoreList | List\<FutStore\> | 期貨庫存清單 |

### Output — FutStore（原文，43 欄）

| Name | Type | Description |
|------|------|-------------|
| FutAccount | string | 帳號 |
| Kind | string | F(期貨) / O(選擇權) / C(期貨+選擇權) |
| Trid | string | 商品代碼（例 TX109100E4） |
| BS | string | B(買) / S(賣) |
| Qty | Int | 未平倉口數 |
| Amt | double | 成交總點數 |
| Fee | double | 手續費 |
| Tax | double | 交易稅 |
| CurrencyType | string | 幣別：NTD |
| DayTradeID | string | 當沖註記："Y" 或空白 |
| Commodity1 | string | 商品代碼1 |
| CallPut1 | string | Call/Put 1：C 或 P |
| SettlementMonth1 | Int | 結算月份1（例 200712） |
| StrikePrice1 | double | 履約價1 |
| BS1 | string | 買賣別1 |
| StkName1 | string | 商品名稱1 |
| MarketNo1 | enumMarketType | 市場代碼1 |
| StkCode1 | string | 報價代碼1 |
| Commodity2 … StkCode2 | — | 第二腳（複式單）對應欄位 |
| BuyPrice1 / SellPrice1 / MarketPrice1 | double | 買價1 / 賣價1 / 市價1（盤前為0時給開盤參考價） |
| BuyPrice2 / SellPrice2 / MarketPrice2 | double | 第二腳對應 |
| Decimal | Short | 小數位數（+小數位 / -分數分母 / 0整數） |
| ProductType1 | string | F(期貨) / O(選擇權) |
| ProductKind1 | string | I(指數) R(利率) B(債券) C(商品) S(股票) |
| ProductType2 / ProductKind2 | string | 第二腳對應 |
| UpStopPrice1 / DownStopPrice1 | double | 漲停/跌停價1 |
| UpStopPrice2 / DownStopPrice2 | double | 漲停/跌停價2 |
| StkCode1opp / StkCode2opp | string | 反向腳報價代碼 |

### 原文程式碼 — Python

```python
import os, time, datetime, struct, pathlib, sys
from datetime import datetime
from pathlib import Path
from pythonnet import load

load("coreclr")
import clr, System

clr.AddReference('System.Collections')
from System.Collections.Generic import List

sys.path.append(Path(pathlib.Path(__file__).parent.resolve()))
if sys.platform == "win32":
    os.add_dll_directory(Path(pathlib.Path(__file__).parent.resolve()))

try:
    clr.AddReference("YuantaSparkAPI")
except Exception as e:
    print(f"Error loading YuantaSparkAPI: {e}")
from YuantaOneAPI import YuantaSparkAPITrader, enumLogType, enumMarketType, enumEnvironmentMode

objYuantaSparkAPI = YuantaSparkAPITrader()
objYuantaSparkAPI.SetLogType(enumLogType.COMMON)

def on_response(intMark, dwIndex, strIndex, objHandle, objValue):
    try:
        result = ''
        match intMark:
            case 0:
                result = str(objValue)
            case 1:
                match strIndex:
                    case 'Login':
                        loginResult = objValue
                        status = loginResult.LoginStatus
                        strMsgCode = status.MsgCode
                        strMsgContent = status.MsgContent
                        intCount = status.Count
                        result = '{0},{1},帳號筆數:{2}\r\n'.format(strMsgCode,strMsgContent, str(intCount))
                        if strMsgCode == '0001' or strMsgCode == '00001' or intCount > 0 :
                            for i in objValue.LoginList:
                                result += f"{i.Account},{i.Name},{i.InvestorID},{i.SellerNo}\n"

                    case 'GetFutStoreSummary':
                        fResult = objValue
                        futList = fResult.FutStoreList

                        result += '期貨庫存總表:\n'
                        result += f'期貨庫存筆數:{futList.Count}\n'
                        for i in range(futList.Count):
                            result += '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15},{16},{17},{18},{19},{20},{21},{22},{23},{24},{25},{26},{27},{28},{29},{30},{31},{32},{33},{34},{35},{36},{37},{38},{39},{40},{41},{42}\r\n'.format(
                                futList[i].FutAccount,futList[i].Kind,futList[i].Trid,futList[i].BS,str(futList[i].Qty),str(futList[i].Amt),str(futList[i].Fee),str(futList[i].Tax),futList[i].CurrencyType,futList[i].DayTradeID,
                                futList[i].Commodity1,futList[i].CallPut1,str(futList[i].SettlementMonth1),str(futList[i].StrikePrice1),futList[i].BS1,futList[i].StkName1,str(futList[i].MarketNo1),futList[i].StkCode1,
                                futList[i].Commodity2,futList[i].CallPut2,str(futList[i].SettlementMonth2),str(futList[i].StrikePrice2),futList[i].BS2,futList[i].StkName2,str(futList[i].MarketNo2),futList[i].StkCode2,
                                str(futList[i].BuyPrice1),str(futList[i].SellPrice1),float(futList[i].MarketPrice1),str(futList[i].BuyPrice2),str(futList[i].SellPrice2),str(futList[i].MarketPrice2),str(futList[i].Decimal),
                                futList[i].ProductType1,futList[i].ProductKind1,futList[i].ProductType2,futList[i].ProductKind2,str(futList[i].UpStopPrice1),str(futList[i].DownStopPrice1),str(futList[i].UpStopPrice2),
                                str(futList[i].DownStopPrice2),futList[i].StkCode1opp,futList[i].StkCode2opp)

        if result:
            print('##================================================##\n')
            print(result)

    except Exception as error:
        print(f"處理回應時發生錯誤: {error}")

objYuantaSparkAPI.OnResponse += on_response
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)
objYuantaSparkAPI.Login('FF0210132243219588', 'abcd123')
time.sleep(2)

objYuantaSparkAPI.GetFutStoreSummary('FF0210132243219588')

while True:
    time.sleep(1)
```

---

## 12. 帳務 → 期貨權益數查詢（★ 期貨淨值）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E6%9C%9F%E8%B2%A8%E6%AC%8A%E7%9B%8A%E6%95%B8%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetFutInterestStore(Account, Type, Currency, lng)
```

### Input Parameters（原文）

| 參數名 | 型態 | 說明 | 備註 |
|--------|------|------|------|
| Account | string | 帳號 | 期貨格式: F+分公司代號(7+3)+帳號(7)，例 `FF021000P001234567` |
| Type | string | 型態 | `1`:基本幣別；`2`:明細幣別 |
| Currency | string | 幣別 | `TWD`(台幣)、`USA`(美金)、`CNA`(人民幣)、`JPA`(日圓) |
| Lng | enumLangType | 語系 | Normal(Big5)、UTF8、SC；預設 Normal |

> ⚠️ 幣別代碼是 `USA` / `CNA` / `JPA`，**不是** ISO 的 USD/CNY/JPY。

### Output — FutInterestStoreResult（原文，全欄）

| 欄位名 | 型態 | 說明 | 備註 |
|--------|------|------|------|
| ReplyCode | Short | 委託結果代碼 | 0:成功；其他:失敗 |
| Advisory | String | 錯誤說明 | |
| Type | String | 型態 | 1:基本幣別；2:明細幣別 |
| Currency | String | 幣別 | TWD、USA、CNA、JPA |
| **Equity** | double | **權益數** | |
| AllFullIm | double | 全額原始保證金 | |
| CanuseMargin | double | 可運用保證金 | |
| RiskRate | String | 權益比率 | |
| DaytradeRisk | String | 當沖風險指標 | |
| AllRiskRate | String | 風險指標 | |
| CashForward | double | 前日餘額 | |
| OpenGlYes | double | 昨日未平倉損益 | |
| UpdateTime | TYuantaDateTime | 風險更新時間 | 時間日期物件 |
| Accounting | double | 存/提 | |
| FloatMargin | double | 未沖銷期貨浮動損益 | |
| FloatPremium | double | 未沖銷買方選擇權市值+未沖銷賣方選擇權市值 | |
| CommissionAll | double | 手續費 | |
| **TotalValue** | double | **權益總值** | |
| TaxRate | double | 期交稅 | |
| AllIm | double | 原始保證金 | |
| CallMargin | double | 追繳保證金 | |
| Grantal | double | 本日期貨平倉損益淨額+到期履約損益 | |
| AllMm | double | 維持保證金 | |
| OrderIm | double | 委託保證金 | |
| Premium | double | 權利金收入與支出 | |
| OrderPremium | double | 委託權利金 | |
| Balance | double | 本日餘額 | |
| CanusePremium | double | 可動用(出金)保證金(含抵委) | |
| CoveredOim | double | 委託抵繳保證金 | |
| BondAmt | double | 債券實物交割款 | |
| NobondAmt | double | 債券實物不足交割款 | |
| BondMargin | double | 債券待交割保證金 | |
| CoveredIm | double | 有價證券抵繳總額 | |
| ReduceIm | double | 期貨多空減收保證金 | |
| IncreaseIm | double | 加收保證金 | |
| YTotalValue | double | 昨日權益總值 | |
| Rate | double | 匯率 | |
| BestFlag | string | 客戶保證金計收方式 | `' '`(傳統/策略)、`'S'`(整戶風險/SPAN)、`'Y'`(保證金最佳化) |
| GlToday | double | 本日損益 | |
| DspEquity | double | 風險權益總值 | |
| DspFloatmargin | double | 未沖銷期貨風險浮動損益 | |
| DspFloatpremium | double | 未沖銷買方選擇權風險市值+未沖銷賣方選擇權風險市值 | |
| DspIM | double | 風險原始保證金 | |
| DspRiskRate | double | 盤後風險指標 | |

> ★ Portfolio-Tracking 要的期貨帳戶淨值＝`TotalValue`（權益總值）或 `Equity`（權益數）。
> 官方 JSON 範例中 `TotalValue` 與 `Equity` 皆為 `50094758`，但 `TaxRate` 以後的欄位全為空字串——
> 表示**很多欄位在 Type=1 時不回值**，實作要防空字串 → float 轉型炸掉。

### 原文程式碼 — Python 呼叫與 OnResponse

```python
def on_response(intMark, dwIndex, strIndex, objHandle, objValue):
    try:
        result = ''

        match intMark:
            case 0:  # 系統回應資訊
                result = str(objValue)

            case 1:  # 查詢/回應資訊
                match strIndex:
                    case 'Login':
                        loginResult = objValue
                        status = loginResult.LoginStatus
                        strMsgCode = status.MsgCode # 訊息代碼
                        strMsgContent = status.MsgContent # 訊息內容
                        intCount = status.Count # 筆數
                        result = '{0},{1},帳號筆數:{2}\r\n'.format(strMsgCode,strMsgContent, str(intCount))
                        if strMsgCode == '0001' or strMsgCode == '00001' or intCount > 0 :
                            for i in objValue.LoginList:
                                result += f"{i.Account},{i.Name},{i.InvestorID},{i.SellerNo}\n"

                    case 'GetFutInterestStore':
                        fResult = objValue

                        result += '期貨權益數:\r\n'

                        #dateTime=TYuantaDateTime()
                        dateTime = fResult.UpdateTime

                        Date= '{0}/{1}/{2}'.format(dateTime.Year, dateTime.Month, dateTime.Day)
                        Time= '{0}:{1}:{2}.{3}'.format(str(dateTime.Hour), str(dateTime.Minute), str(dateTime.Second), str(dateTime.Millisecond))

                        result += '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12} {13},{14},{15},{16},{17},{18},{19},{20},{21},{22},{23},{24},{25},{26},{27},{28},{29},{30},{31},{32},{33},{34},{35},{36},{37},{38},{39},{40},{41},{42},{43},{44}\r\n'.format(
                            str(fResult.ReplyCode),fResult.Advisory,fResult.Type,fResult.Currency,str(fResult.Equity),str(fResult.AllFullIm),str(fResult.CanuseMargin),fResult.RiskRate,fResult.DaytradeRisk,
                            fResult.AllRiskRate,str(fResult.CashForward),str(fResult.OpenGlYes),Date,Time,str(fResult.Accounting),str(fResult.FloatMargin),str(fResult.FloatPremium),str(fResult.CommissionAll),
                            str(fResult.TotalValue),str(fResult.TaxRate),str(fResult.AllIm),str(fResult.CallMargin),str(fResult.Grantal),str(fResult.AllMm),str(fResult.OrderIm),str(fResult.Premium),
                            str(fResult.OrderPremium),str(fResult.Balance),str(fResult.CanusePremium),str(fResult.CoveredOim),str(fResult.BondAmt),str(fResult.NobondAmt),str(fResult.BondMargin),str(fResult.CoveredIm),
                            str(fResult.ReduceIm),str(fResult.IncreaseIm),str(fResult.YTotalValue),str(fResult.Rate),fResult.BestFlag,str(fResult.GlToday),str(fResult.DspEquity),str(fResult.DspFloatmargin),
                            str(fResult.DspFloatpremium),str(fResult.DspIM),str(fResult.DspRiskRate))

        if result:
            print('##================================================##\n')
            print(result)

    except Exception as error:
        print(f"處理回應時發生錯誤: {error}")

objYuantaSparkAPI.OnResponse += on_response
#測試環境帳號:UAT 正式環境:PROD
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)
objYuantaSparkAPI.Login('FF0210132243219588', 'abcd123')
time.sleep(2)

objYuantaSparkAPI.GetFutInterestStore('FF0210132243219588','1','TWD')
time.sleep(2)

# 保持程式運行
while True:
    time.sleep(1)
```

> 注意元件引用行多了 `FutSprStore`：
> `from YuantaOneAPI import YuantaSparkAPITrader, enumLogType, enumQuoteIndexType, enumMarketType, enumEnvironmentMode, enumQuoteFiveTickIndexType, FutSprStore`

### 原文 Response Body

```json
{
  "Result": {
      "ReplyCode": "0",
      "Advisory": "查詢成功",
      "Type": "1",
      "Currency": "TWD",
      "Equity": "50094758.0",
      "AllFullIm": "306000.0",
      "CanuseMargin": "49753758.0",
      "RiskRate": "999.00",
      "DaytradeRisk": "999.00",
      "AllRiskRate": "999.00",
      "CashForward": "49998958.0",
      "OpenGlYes": "60800.0",
      "UpdateDate": "2025/9/8",
      "UpdateTime": "16:17:49.0",
      "Accounting": "0.0",
      "FloatMargin": "95800.0",
      "FloatPremium": "0.0",
      "CommissionAll": "0.0",
      "TotalValue": "50094758",
      "TaxRate": "",
      "AllIm": "",
      "CallMargin": "",
      "Grantal": "",
      "AllMm": "",
      "OrderIm": "",
      "Premium": "",
      "OrderPremium": "",
      "Balance": "",
      "CanusePremium": "",
      "CoveredOim": "",
      "BondAmt": "",
      "NobondAmt": "",
      "BondMargin": "",
      "CoveredIm": "",
      "ReduceIm": "",
      "IncreaseIm": "",
      "YTotalValue": "",
      "Rate": "",
      "BestFlag": "",
      "GlToday": "",
      "DspEquity": "",
      "DspFloatmargin": "",
      "DspFloatpremium": "",
      "DspIM": "",
      "DspRiskRate": ""
  }
}
```

---

## 13. 帳務 → 未實現損益明細查詢

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E6%9C%AA%E5%AF%A6%E7%8F%BE%E6%90%8D%E7%9B%8A%E6%98%8E%E7%B4%B0%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetUnrealizedGainLossDetail(Account, MarketType, StkCode, lng)
```

### Input Parameters

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | 證券: S+分公司代號(4)+帳號(7)，例 S98875005091。註1（限證券使用） |
| MarketType | enumMarketType | 市場類別 | 參考列舉物件-市場類別 |
| StkCode | string | 股票代號 | |
| lng | enumLangType | 語系 | 預設 `Normal` |

> ⚠️ **必須逐檔指定 StkCode**，不能一次拿全部。要抓全部未實現損益就得先 `GetStoreSummary()`
> 拿到持股清單，再對每檔各呼叫一次——受「同 FunctionID 一秒內帳務類發送 3 次」限制。
> 但 `GetStoreSummary` 的 `StkStore` 已經有 `ReturnAmt`（未實現損益）與 `MarketAmt`（市值），
> **PoC 用 GetStoreSummary 一支就夠**，本 API 只在需要「同一股票分批進場的逐筆成本」時才用。

### Output — UnGainLossDetailResult

| Name | Type | Description | Memo |
|------|------|-------------|------|
| UnGainLossDetailList | List\<UnGainLossDetail\> | 結果清單 | 註2：不含待沖銷委託資訊 |

### Output — UnGainLossDetail

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | |
| TradeKind | int | 交易種類 | 0:現股；3:資買；4:券賣 |
| MarketNo | enumMarketType | 市場代碼 | |
| StkCode | string | 股票代號 | |
| StockQty | long | 庫存股數 | |
| Price | double | 成交價 | |
| TradeDate | string | 成交日期 | 格式 yyyy/MM/dd |
| Cost | double | 持有成本 | |
| Interest | long | 預估利息 | |
| ReturnAmt | double | 未實現損益 | |
| MarketAmt | double | 股票市值 | 股數 × 市價 |

### 原文程式碼 — Python OnResponse（★ 有 pythonnet 反射的坑）

```python
                    case 'GetUnrealizedGainLossDetail':
                        GResult = objValue
                        gResult = GResult.UnGainLossDetailList

                        result += '未實現損益明細結果:\r\n'
                        for item in gResult:
                            f = item.GetType().GetField('Cost', BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly)
                            cost = f.GetValue(item)
                            result += f'{item.Account},{item.TradeKind},{item.MarketNo},{item.StkCode},{item.StockQty},{item.Price},{item.TradeDate},{cost},{item.Interest},{item.ReturnAmt},{item.MarketAmt}\r\n'
```

> ★★ **重要坑**：`Cost` 欄位在 Python 端**無法用屬性存取**，官方範例用
> `System.Reflection.BindingFlags` 反射取值（需 `from System.Reflection import BindingFlags`）。
> 推測是 `Cost` 與某個 .NET 內建成員名稱衝突。其他欄位可正常 `item.XXX` 存取。
> `GetStoreSummary` 的 `StkStore.Cost` 是否也有同樣問題，**文檔沒說明，需實測**。

### 原文程式碼 — Python 呼叫

```python
objYuantaSparkAPI.OnResponse += on_response
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)

objYuantaSparkAPI.Login('S98875005091', '1234')
time.sleep(2)

objYuantaSparkAPI.GetUnrealizedGainLossDetail('S98875005091',enumMarketType.TWSE,'2885')

while True:
    time.sleep(2)
```

### 原文 Response Body

```json
{
  "Result": {
    "UnGainLossDetailList": [
      {
        "Account": "S98875005091",
        "TradeKind": "0",
        "MarketNo": "TWSE",
        "StkCode": "2330",
        "StockQty": "1000",
        "Price": "1660",
        "TradeDate": "2026/01/16",
        "Cost": "1662365",
        "Interest": "0",
        "ReturnAmt": "145056",
        "MarketAmt": "1810000"
      }
    ]
  }
}
```

---

## 14. 帳務 → 已實現損益查詢

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E5%B7%B2%E5%AF%A6%E7%8F%BE%E6%90%8D%E7%9B%8A%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetHisRealizedGainLoss(Account, SDate, EDate, lng)
```

### Input Parameters

| Name | Type | Description | Notes |
|------|------|-------------|-------|
| Account | string | 帳號 | 證券: S+分公司代號(4)+帳號(7)。註1（限證券使用） |
| SDate | string | 查詢起日 | 格式 yyyy/MM/dd。註2 |
| EDate | string | 查詢迄日 | 格式 yyyy/MM/dd。註2 |
| lng | enumLangType | 語系 | 預設 `Normal` |

> **註2：資料僅限近 2 年；查詢區間不得超過 1 年。**

### Output — RealizedGainLossResult

| Name | Type | Description |
|------|------|-------------|
| RealizedGainLossList | List\<RealizedGainLoss\> | 結果清單 |

### Output — RealizedGainLoss

| Name | Type | Description | Notes |
|------|------|-------------|-------|
| Account | string | 帳號 | |
| MarketNo | enumMarketType | 市場代碼 | |
| StkCode | string | 商品代號 | |
| TradeDate | string | 成交日期 | 格式 yyyy/MM/dd |
| TradeKind | int | 交易種類 | 0:現股；1:融資買；2:融券賣；3:融資；4:融券；5,6:借券；7:股票沖銷；8:證券沖銷；17:當沖買；18:當沖賣 |
| Price | double | 成交價 | |
| Qty | int | 成交股數 | |
| ProfitLoss | int | 損益 | |
| OrderNo | string | 委託書號 | |
| TermSplit | int | 委託書分割號 | |
| TermExt | string | 委託書擴充碼 | |
| Charge | int | 手續費 | |
| Cost | int | 持有成本 | |
| Tax | int | 交易稅 | |
| TotalAMT | int | 成交金額 | |

### 原文程式碼 — Python（含呼叫）

```python
                    case 'GetHisRealizedGainLoss':
                        GResult = objValue
                        gResult = GResult.RealizedGainLossList

                        result += '已實現損益查詢結果:\r\n'
                        for i in range(gResult.Count):  
                            result += '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14}\r\n'.format(gResult[i].Account,gResult[i].MarketNo,gResult[i].StkCode,gResult[i].TradeDate,gResult[i].TradeKind,gResult[i].Price,gResult[i].Qty,gResult[i].ProfitLoss,gResult[i].OrderNo,gResult[i].TermSplit,gResult[i].TermExt,gResult[i].Charge,gResult[i].Cost,gResult[i].Tax,gResult[i].TotalAMT)
```

```python
objYuantaSparkAPI.OnResponse += on_response
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)

objYuantaSparkAPI.Login('S98875005091', '1234')
time.sleep(2)

objYuantaSparkAPI.GetHisRealizedGainLoss('S98875005091','2026/04/01','2026/04/30')

while True:
    time.sleep(2)
```

### 原文 Response Body

```json
{
  "Result": {
    "RealizedGainLossList": [
      {
        "Account": "S98875005091",
        "MarketNo": "TWSE",
        "StkCode": "2344",
        "TradeDate": "2025/06/12",
        "TradeKind": "0",
        "Price": "17.25",
        "Qty": "1000",
        "ProfitLoss": "-10064",
        "OrderNo": "f0004",
        "TermSplit": "0",
        "TermExt": "00000",
        "Charge": "24",
        "Cost": "27239",
        "Tax": "51",
        "TotalAMT": "17250"
      }
    ]
  }
}
```

> 注意：這裡 `gResult[i].Cost` 是直接屬性存取（沒有用反射），與未實現損益頁不一致。
> 型別也不同（這裡 `Cost` 是 `int`，未實現損益是 `double`）。實測為準。

---

## 15. 帳務 → 銀行餘額查詢（現金）

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E9%8A%80%E8%A1%8C%E9%A4%98%E9%A1%8D%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetBankBalance(Account, lng)
```

### Input Parameters

| Name | Type | Description | Memo |
|------|------|-------------|------|
| Account | string | 帳號 | 證券: S+分公司代號(4)+帳號(7)，例 S98875005091。**限證券使用** |
| lng | enumLangType | 語系 | 預設 `Normal` |

### Output — BankBalanceResult / BankBalance

| Name | Type | Description | Memo |
|------|------|-------------|------|
| BankBalanceList | List\<BankBalance\> | 結果清單 | |
| Account | string | 帳號 | |
| ResponseTime | string | 系統回覆時間 | HH:mm:ss |
| BankAccount | string | 銀行帳號 | |
| **AvailableBalance** | double | **可用餘額** | |
| Message | string | 說明 | 錯誤訊息 |

> ★ 這正好補上元大對帳單「沒有現金存款餘額欄位」的缺口
> （見專案 `docs/yuanta-cumcash-known-limitations.md`）。

### 原文程式碼 — Python

```python
                    case 'GetBankBalance':
                        BResult = objValue
                        bResult = BResult.BankBalanceList
                        result += '銀行餘額查詢結果:\r\n'
                        for i in range(bResult.Count):  
                            result += '{0},{1},{2},{3},{4}\r\n'.format(bResult[i].Account,bResult[i].ResponseTime,bResult[i].BankAccount,bResult[i].AvailableBalance,bResult[i].Message)

objYuantaSparkAPI.OnResponse += on_response
objYuantaSparkAPI.Open(enumEnvironmentMode.UAT)
time.sleep(2)
objYuantaSparkAPI.Login('S981r1691656', 'abcd123')
time.sleep(2)

objYuantaSparkAPI.GetBankBalance('S981r1691656')

while True:
    time.sleep(2)
```

### 原文 Response Body

```json
{
  "Result": {
    "BankBalanceList": [
      {
        "Account": "S98875005091",
        "ResponseTime": "2026/01/01 14:30:15",
        "BankAccount": "S98875005091",
        "AvailableBalance": "1000000",
        "Message": ""
      }
    ]
  }
}
```

---

## 16. 帳務 → 交割款查詢

### 來源 URL
`https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%B8%B3%E5%8B%99/%E4%BA%A4%E5%89%B2%E6%AC%BE%E6%9F%A5%E8%A9%A2/index.html`

### 函式
```
bool GetStkTransactionOutlay(Account, lng)
```

### Input / Output

| Name | Type | Description |
|------|------|-------------|
| Account | string | 帳號（證券: S+分公司代號(4)+帳號(7)，限證券使用） |
| Lng | enumLangType | 語系，預設 Normal |

**ReversalReportResult**

| Name | Type | Description |
|------|------|-------------|
| TransactionOutlayList | List\<TransactionOutlay\> | 結果清單（**近 3 個交割日**的資料） |

**TransactionOutlay**

| Name | Type | Description |
|------|------|-------------|
| Account | string | 帳號 |
| SettlementDay | string | 交割日期（yyyy/MM/dd） |
| SettlementAmt | double | 交割金額 |

### 原文程式碼 — Python

```python
objYuantaSparkAPI.GetStkTransactionOutlay('S98875005091')

def on_response(intMark, dwIndex, strIndex, objHandle, objValue):
    if intMark == 1 and strIndex == 'GetStkTransactionOutlay':
        TResult = objValue
        tResult = TResult.TransactionOutlayList
        for i in range(tResult.Count):  
            print('{0},{1},{2}'.format(tResult[i].Account, tResult[i].SettlementDay, tResult[i].SettlementAmt))
```

---

## 17. 未抓取 / 找不到的項目

| 項目 | 狀態 |
|---|---|
| 「保證金查詢」 | 文檔中**沒有**叫這個名字的頁面。最接近的是 `帳務/期貨保證金最佳化查詢`（未抓）與 `期貨權益數查詢` 內的各項保證金欄位 |
| `帳務/國際期貨庫存總表查詢` | 未抓（PoC 不需要） |
| `帳務/期貨複式單庫存明細查詢` | 未抓 |
| `帳務/沖銷明細查詢` | 未抓 |
| `回報/*` 5 頁 | 未抓 |
| `行情 / 交易 / 條件單` | 未抓（依需求略過） |
| `ys.yuanta.com.tw/quartet/api/` 目錄列表 | **WebFetch 403 Forbidden**；但個別檔案 URL 以 curl HEAD 驗證為 HTTP 200 |
| `.so` / `.dylib` 原生檔名 | 文檔中**完全沒提及**；只講 `YuantaSparkAPI.dll`（.NET assembly，跨平台同名） |
| 明確的 Docker 部署指引 | 文檔**沒有**；只有 Ubuntu 24.04 裸機安裝步驟 |
| Login 是否支援 OTP / 二次驗證 | 文檔中**沒有任何相關欄位或流程**（＝不需要） |

---

## 18. PoC 落地建議（本節為分析，非文檔原文）

1. **主力只需三支 API**：
   - `GetStoreSummary(account, lng)` → 台股/國外股票持倉 + 市值(`MarketAmt`) + 未實現損益(`ReturnAmt`)
   - `GetBankBalance(account, lng)` → 現金（`AvailableBalance`）
   - `GetFutInterestStore(account, '1', 'TWD', lng)` → 期貨權益總值（`TotalValue`）
   證券與期貨是**兩個不同帳號**（`S...` / `F...`），登入也分開。

2. **同步化 callback**：包一層 `threading.Event` + dict，`OnResponse` 收到對應 `strIndex` 就 set，
   主流程 `wait(timeout)`。不要照抄官方的 `time.sleep()`。

3. **Big5 亂碼**：一律傳 `enumLangType.UTF8`。

4. **`Cost` 欄位反射坑**：未實現損益明細的 `Cost` 必須用 `BindingFlags` 反射取，
   其他物件的 `Cost` 未知，PoC 要對每個物件實測一次。

5. **固定 IP**：測試環境明文要求提供固定 IP 給營業員做防火牆白名單。
   Cloud Run 需 VPC Connector + Cloud NAT 固定出口 IP，這是本專案接入的**最大架構障礙**，
   建議在寫任何 code 之前先跟營業員確認正式環境是否也強制 IP 白名單。

6. **pythonnet + .NET 8 進 Docker**：現有 `Dockerfile` 是 Python base image，
   要嘛換成 `mcr.microsoft.com/dotnet/sdk:8.0` 再裝 Python，要嘛在 Python image 裡裝 dotnet。
   元件包 62 MB，會明顯拉大 image；考慮是否值得，或改成獨立 sidecar service。

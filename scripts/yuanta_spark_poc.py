"""元大證券 Spark API 唯讀查帳 PoC — dry-run，不寫 DB。

目的：驗證 Spark API（pythonnet + .NET 8）能否取到 portfolio-tracking 需要的
持倉 / 市值 / 現金 / 期貨權益，取代目前的 PDF 對帳單流程（scripts/yuanta_pdf_parse_poc.py）。

只呼叫三支唯讀帳務 API，不碰下單：
    GetStoreSummary(account, lng)          → 股票庫存（含 MarketAmt 市值、ReturnAmt 未實現損益）
    GetBankBalance(account, lng)           → 銀行可用餘額（補上對帳單缺的現金欄位）
    GetFutInterestStore(acct, '1', 'TWD')  → 期貨權益總值 TotalValue（選填，需期貨帳號）

前置作業：
    1. 元件包已下載解壓在 vendor/yuanta_spark/YuantaSparkAPI_osx-arm64_Python/
       （Linux 部署要換 YuantaSparkAPI_linux-x64_Python.zip，見 docs/yuanta-spark-api-poc.md）
    2. 已裝 .NET 8 SDK 與 pythonnet：
           brew install dotnet@8
           uv pip install pythonnet==3.0.5
    3. 憑證 .pfx 放進 .secrets/（已被 .gitignore），並在 .env 填好下列變數

.env 需要填的變數（全部見 .env.example 的「元大 Spark API」段落）：
    YUANTA_SPARK_ENV=UAT                  # UAT 測試環境 / PROD 正式環境
    YUANTA_SPARK_CERT_PATH=...            # .pfx 絕對路徑（macOS/Linux 必填）
    YUANTA_SPARK_CERT_PASSWORD=...        # 憑證密碼
    YUANTA_SPARK_STOCK_ACCOUNT=S...       # S + 分公司代號4碼 + 帳號7碼
    YUANTA_SPARK_STOCK_PASSWORD=...       # 電子密碼
    YUANTA_SPARK_FUT_ACCOUNT=F...         # 選填，沒有期貨帳戶就留空
    YUANTA_SPARK_FUT_PASSWORD=...         # 選填

用法：
    uv run python scripts/yuanta_spark_poc.py
"""

import json
import os
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

DEFAULT_DLL_DIR = ROOT / "vendor" / "yuanta_spark" / "YuantaSparkAPI_osx-arm64_Python"
DLL_DIR = Path(os.getenv("YUANTA_SPARK_DLL_DIR") or DEFAULT_DLL_DIR)
OUT_DIR = ROOT / "data" / "raw" / "yuanta_spark_poc"

# ── 載入 .NET 元件 ────────────────────────────────────────────────────────────
if not (DLL_DIR / "YuantaSparkAPI.dll").exists():
    sys.exit(f"找不到 YuantaSparkAPI.dll，請確認 DLL 目錄：{DLL_DIR}")

from pythonnet import load as pythonnet_load

pythonnet_load("coreclr")

import clr  # noqa: E402

sys.path.append(str(DLL_DIR))
clr.AddReference("System.Collections")
clr.AddReference("YuantaSparkAPI")

from YuantaOneAPI import (  # noqa: E402
    OnResponseEventHandler,
    YuantaSparkAPITrader,
    enumEnvironmentMode,
    enumLangType,
    enumLogType,
)

# ── callback 同步：官方範例靠 time.sleep()，這裡改用 queue 等特定 strIndex ────
_responses: "queue.Queue[tuple[int, int, str, object]]" = queue.Queue()
_system_msgs: list[str] = []


def on_response(int_mark, dw_index, str_index, obj_handle, obj_value):
    """所有 API 結果都從這裡回來；只做搬運，解析交給主執行緒。"""
    try:
        if int_mark == 0:  # 系統訊息（連線狀態等）
            _system_msgs.append(f"[sys dwIndex={dw_index}] {obj_value}")
            return
        _responses.put((int_mark, dw_index, str_index or "", obj_value))
    except Exception as exc:  # callback 內炸掉會被 .NET 吞掉，一定要自己印
        print(f"!! on_response 例外：{exc}")


def wait_for(str_index: str, timeout: float = 15.0):
    """等指定功能的回應。dwIndex 非 0 代表錯誤（3=尚未登入 / 9=憑證異常）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            mark, dw_index, idx, value = _responses.get(timeout=deadline - time.time())
        except queue.Empty:
            break
        if idx == str_index:
            return dw_index, value
        print(f"   （略過非預期回應 intMark={mark} strIndex={idx or '<空>'} dwIndex={dw_index}）")
    raise TimeoutError(f"等 {str_index} 回應逾時 {timeout}s；系統訊息：{_system_msgs[-3:]}")


# ── 型別轉換：.NET 物件 → dict ────────────────────────────────────────────────
def obj_to_dict(obj, fields: list[str]) -> dict:
    out = {}
    for f in fields:
        try:
            v = getattr(obj, f)
        except Exception as exc:
            out[f] = f"<取值失敗: {exc}>"
            continue
        out[f] = v if isinstance(v, (int, float, str, bool, type(None))) else str(v)
    return out


STK_STORE_FIELDS = [
    "Account", "TradeKind", "MarketNo", "MarketName", "StkCode", "StkName",
    "StockQty", "Price", "Cost", "TradingQty", "Loan", "LotSize", "MarketPrice",
    "CurrencyType", "OddTradingQty", "ReturnAmt", "MarketAmt",
]
OV_STK_STORE_FIELDS = [
    "Account", "CurrencyType", "MarketNo", "MarketName", "StkCode", "StkName",
    "StkFullName", "StockQty", "TradingQty", "Price", "Cost", "CloseRate",
    "RateKind", "LotSize", "MarketPrice",
]
BANK_BALANCE_FIELDS = ["Account", "ResponseTime", "BankAccount", "AvailableBalance", "Message"]
FUT_INTEREST_FIELDS = [
    "ReplyCode", "Advisory", "Type", "Currency", "Equity", "TotalValue",
    "CanuseMargin", "AllIm", "Balance", "FloatMargin", "GlToday",
]


def main() -> int:
    env_name = (os.getenv("YUANTA_SPARK_ENV") or "UAT").upper()
    cert_path = os.getenv("YUANTA_SPARK_CERT_PATH") or ""
    cert_password = os.getenv("YUANTA_SPARK_CERT_PASSWORD") or ""
    stock_account = os.getenv("YUANTA_SPARK_STOCK_ACCOUNT") or ""
    stock_password = os.getenv("YUANTA_SPARK_STOCK_PASSWORD") or ""
    fut_account = os.getenv("YUANTA_SPARK_FUT_ACCOUNT") or ""
    fut_password = os.getenv("YUANTA_SPARK_FUT_PASSWORD") or ""

    if not stock_account or not stock_password:
        return _fail("請先在 .env 填 YUANTA_SPARK_STOCK_ACCOUNT / YUANTA_SPARK_STOCK_PASSWORD")
    for name, value in [
        ("YUANTA_SPARK_CERT_PATH", cert_path),
        ("YUANTA_SPARK_CERT_PASSWORD", cert_password),
        ("YUANTA_SPARK_STOCK_ACCOUNT", stock_account),
        ("YUANTA_SPARK_STOCK_PASSWORD", stock_password),
    ]:
        if "<" in value or value.startswith("/Users/you/") or set(value[1:]) == {"0"}:
            return _fail(f"{name} 還是 .env.example 的預留值（{value}），請改成實際值")
    if sys.platform != "win32" and not cert_path:
        return _fail("macOS/Linux 登入必須帶憑證，請在 .env 填 YUANTA_SPARK_CERT_PATH（絕對路徑）")
    if cert_path and not Path(cert_path).exists():
        return _fail(f"憑證檔不存在：{cert_path}")

    mode = enumEnvironmentMode.PROD if env_name == "PROD" else enumEnvironmentMode.UAT
    print(f"== 元大 Spark API PoC ==")
    print(f"環境: {env_name} / DLL: {DLL_DIR}")
    print(f"證券帳號: {stock_account}  期貨帳號: {fut_account or '(未設定)'}")

    api = YuantaSparkAPITrader(str(ROOT / "log"))
    api.OnResponse += OnResponseEventHandler(on_response)
    # 連線出問題時設 YUANTA_SPARK_DEBUG=1，log/ 下會留下完整封包紀錄
    api.SetLogType(enumLogType.ALL if os.getenv("YUANTA_SPARK_DEBUG") == "1" else enumLogType.COMMON)

    result: dict = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "env": env_name,
        "stock_account": stock_account,
    }

    try:
        print("\n[1/5] Open 連線…")
        api.Open(mode)
        _wait_connected()

        print("[2/5] Login 證券帳號…")
        ok = _login(api, cert_path, cert_password, stock_account, stock_password)
        if not ok:
            return _fail("證券帳號登入失敗，詳見上方訊息")

        print("[3/5] GetStoreSummary 股票庫存…")
        result["store_summary"] = _fetch_store_summary(api, stock_account)

        print("[4/5] GetBankBalance 銀行餘額…")
        result["bank_balance"] = _fetch_bank_balance(api, stock_account)

        if fut_account and fut_password:
            print("[5/5] 期貨帳號登入 + GetFutInterestStore 權益數…")
            if _login(api, cert_path, cert_password, fut_account, fut_password):
                result["fut_interest"] = _fetch_fut_interest(api, fut_account)
            else:
                result["fut_interest"] = {"error": "期貨帳號登入失敗"}
        else:
            print("[5/5] 跳過期貨（.env 未設 YUANTA_SPARK_FUT_ACCOUNT）")

    finally:
        try:
            api.LogOut()
            time.sleep(1)
            api.Close()
            api.Dispose()
        except Exception as exc:
            print(f"（關閉連線時例外，可忽略：{exc}）")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"spark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n原始結果已寫入：{out_path}")
    _print_summary(result)
    return 0


def _fail(msg: str) -> int:
    print(f"\n✗ {msg}")
    return 1


def _wait_connected(timeout: float = 10.0) -> None:
    """Open() 是非同步的，連線結果從 intMark=0 的系統訊息回來。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any("dwIndex=1" in m for m in _system_msgs):
            print("   連線成功")
            return
        time.sleep(0.3)
    print(f"   （未收到明確連線成功訊息，繼續嘗試登入。系統訊息：{_system_msgs}）")


def _login(api, cert_path, cert_password, account, password) -> bool:
    if sys.platform == "win32":
        api.Login(account, password)
    else:
        api.Login(cert_path, cert_password, account, password)

    dw_index, value = wait_for("Login")
    status = value.LoginStatus
    code, content = status.MsgCode, status.MsgContent
    print(f"   MsgCode={code} MsgContent={content} Count={status.Count}")
    if code not in ("0001", "00001") and status.Count <= 0:
        return False
    for item in value.LoginList:
        print(f"   登入帳號: {item.Account} / {item.Name} / 營業員 {item.SellerNo}")
    time.sleep(1)  # 主機端會擋快速連續動作
    return True


def _fetch_store_summary(api, account) -> dict:
    api.GetStoreSummary(account, enumLangType.UTF8)
    _, value = wait_for("GetStoreSummary")
    stk = [obj_to_dict(value.StkStoreList[i], STK_STORE_FIELDS) for i in range(value.StkStoreList.Count)]
    ov = [obj_to_dict(value.OVStkStoreList[i], OV_STK_STORE_FIELDS) for i in range(value.OVStkStoreList.Count)]
    print(f"   台股 {len(stk)} 檔 / 國外股票 {len(ov)} 檔")
    return {"stk_store": stk, "ov_stk_store": ov}


def _fetch_bank_balance(api, account) -> dict:
    api.GetBankBalance(account, enumLangType.UTF8)
    _, value = wait_for("GetBankBalance")
    rows = [obj_to_dict(value.BankBalanceList[i], BANK_BALANCE_FIELDS) for i in range(value.BankBalanceList.Count)]
    print(f"   銀行帳戶 {len(rows)} 筆")
    return {"bank_balance": rows}


def _fetch_fut_interest(api, account) -> dict:
    api.GetFutInterestStore(account, "1", "TWD", enumLangType.UTF8)
    _, value = wait_for("GetFutInterestStore")
    row = obj_to_dict(value, FUT_INTEREST_FIELDS)
    print(f"   權益總值 TotalValue={row.get('TotalValue')}")
    return row


def _print_summary(result: dict) -> None:
    print("\n── 摘要 ───────────────────────────────────────────")
    stk = result.get("store_summary", {}).get("stk_store", [])
    total_mv = sum(float(r.get("MarketAmt") or 0) for r in stk)
    for r in stk:
        print(f"  {r.get('StkCode'):>8} {r.get('StkName'):<10} 股數={r.get('StockQty'):>10} "
              f"市值={r.get('MarketAmt'):>12} 未實現損益={r.get('ReturnAmt'):>12}")
    print(f"  台股市值合計: {total_mv:,.0f}")
    for r in result.get("bank_balance", {}).get("bank_balance", []):
        print(f"  銀行餘額: {r.get('AvailableBalance')} ({r.get('BankAccount')}) {r.get('Message') or ''}")
    if "fut_interest" in result:
        print(f"  期貨權益總值: {result['fut_interest'].get('TotalValue')}")


if __name__ == "__main__":
    raise SystemExit(main())

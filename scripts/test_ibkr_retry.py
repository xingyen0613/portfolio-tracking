"""驗證 _get_statement 對傳輸層錯誤會重試、對 Fail 不重試。"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app.connectors.ibkr_connector as m

time.sleep = lambda *_: None  # 跳過等待

OK = '<FlexQueryResponse><Status>Success</Status><d>ok</d></FlexQueryResponse>'
FAIL = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token invalid</ErrorMessage></FlexStatementResponse>'
WARN = '<FlexStatementResponse><Status>Warn</Status></FlexStatementResponse>'

class Fake(m.IBKRConnector):
    def __init__(self, script):
        self.token, self.query_id, self.script, self.calls = "t", "q", list(script), 0
    def _request(self, endpoint, params):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

def case(name, script, expect_ok, expect_calls):
    c = Fake(script)
    try:
        c._get_statement("ref")
        got = "success"
    except RuntimeError as e:
        got = f"raised: {e}"
    ok = (got == "success") == expect_ok and c.calls == expect_calls
    print(f"{'PASS' if ok else 'FAIL'}  {name}: calls={c.calls} (預期 {expect_calls}) → {got}")
    return ok

CE = lambda: RuntimeError("GetStatement: ConnectionError")
results = [
    case("連線錯誤 2 次後成功 → 應重試並成功", [CE(), CE(), OK], True, 3),
    case("連線錯誤 5 次 → 用完重試後放棄", [CE()]*5, False, 5),
    case("Fail（token 無效）→ 不重試，立刻拋", [FAIL], False, 1),
    case("Warn 兩次後成功 → 既有行為不變", [WARN, WARN, OK], True, 3),
    case("連線錯誤後遇到 Fail → 不再重試", [CE(), FAIL], False, 2),
]
print("\n全部通過" if all(results) else "\n有失敗")
sys.exit(0 if all(results) else 1)

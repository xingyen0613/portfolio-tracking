"""IBKR Flex Web Service connector."""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

_BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
_HEADERS = {"User-Agent": "Python/3"}

# IBKR 週末報表產製窗口偶爾回 503 或 "Statement could not be generated"，
# 重試幾次即可，不必整天放棄。
_SEND_RETRIES = 3
_SEND_DELAY = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IBKRConnector(BaseConnector):
    platform_name = "ibkr"
    use_pricer = False  # IBKR provides mark prices directly

    def authenticate(self) -> None:
        self.token = self._credentials.get("flex_token")
        self.query_id = self._credentials.get("query_id")
        if not self.token or not self.query_id:
            raise RuntimeError("flex_token and query_id are required in connector credentials")

    def fetch_raw(self) -> list[dict]:
        ref_code, _ = self._send_request()
        xml_text = self._get_statement(ref_code)
        return [{
            "resource_type": "flex_report",
            "payload": {"raw_xml": xml_text},
            "fetched_at": _now(),
        }]

    def parse_holdings(self, raw_items: list[dict]) -> list[dict]:
        xml_text = raw_items[0]["payload"]["raw_xml"]
        root = ET.fromstring(xml_text)
        stmt = root.find(".//FlexStatement")
        holdings = []

        # Stock positions (SUMMARY level only, avoids duplicates)
        for pos in stmt.findall(".//OpenPosition"):
            if pos.get("levelOfDetail") != "SUMMARY":
                continue
            holdings.append({
                "platform_symbol": pos.get("symbol"),
                "platform_asset_name": pos.get("description"),
                "asset_type": "stock",
                "quantity": float(pos.get("position", 0)),
                "price": float(pos.get("markPrice", 0)),
                "value": float(pos.get("positionValueInBase", 0)),
                "original_currency": "USD",
                "price_source": "platform",
                "resource_type": "stock",
            })

        # Cash from EquitySummaryInBase (latest reportDate)
        equity_rows = stmt.findall(".//EquitySummaryByReportDateInBase")
        if equity_rows:
            latest = max(equity_rows, key=lambda r: r.get("reportDate", ""))
            cash = float(latest.get("cash", 0))
            holdings.append({
                "platform_symbol": "USD",
                "platform_asset_name": "Cash (USD)",
                "asset_type": "cash",
                "quantity": cash,
                "price": 1.0,
                "value": cash,
                "original_currency": "USD",
                "price_source": "platform",
                "resource_type": "cash",
            })

        return holdings

    def _request(self, endpoint: str, params: dict) -> str:
        """打 Flex endpoint 回 XML text。

        錯誤訊息刻意不帶 URL — query string 含 flex_token，而錯誤字串會進
        source_runs.error_message、connector last_error 與 batch log。
        """
        try:
            resp = requests.get(f"{_BASE_URL}/{endpoint}", params=params,
                                headers=_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"{endpoint}: HTTP {e.response.status_code}") from None
        except requests.RequestException as e:
            raise RuntimeError(f"{endpoint}: {type(e).__name__}") from None
        return resp.text

    def _send_request(self) -> tuple[str, str]:
        params = {"t": self.token, "q": self.query_id, "v": "3"}
        last_err = None

        for attempt in range(1, _SEND_RETRIES + 1):
            try:
                root = ET.fromstring(self._request("SendRequest", params))
                if root.findtext("Status") == "Success":
                    return root.findtext("ReferenceCode"), root.findtext("Url")
                last_err = f"SendRequest failed: {root.findtext('ErrorMessage')}"
            except RuntimeError as e:
                last_err = str(e)

            if attempt < _SEND_RETRIES:
                time.sleep(_SEND_DELAY)

        raise RuntimeError(f"{last_err} (after {_SEND_RETRIES} attempts)")

    def _get_statement(self, ref_code: str,
                       retries: int = 5, delay: int = 5) -> str:
        params = {"t": self.token, "q": ref_code, "v": "3"}
        time.sleep(5)

        for attempt in range(1, retries + 1):
            text = self._request("GetStatement", params)
            root = ET.fromstring(text)
            status = root.findtext("Status")

            if status == "Warn":
                time.sleep(delay)
                continue
            if status == "Fail":
                code = root.findtext("ErrorCode") or "?"
                msg = root.findtext("ErrorMessage") or text
                raise RuntimeError(f"GetStatement failed (code {code}): {msg}")

            return text

        raise RuntimeError("GetStatement: report not ready after max retries")

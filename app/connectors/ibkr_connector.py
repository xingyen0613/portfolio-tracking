"""IBKR Flex Web Service connector."""

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from app.connectors.base import BaseConnector

_BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
_HEADERS = {"User-Agent": "Python/3"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IBKRConnector(BaseConnector):
    platform_name = "ibkr"
    use_pricer = False  # IBKR provides mark prices directly

    def authenticate(self) -> None:
        self.token = self._credentials.get("flex_token") or os.getenv("IBKR_FLEX_TOKEN")
        self.query_id = self._credentials.get("query_id") or os.getenv("IBKR_FLEX_QUERY_ID")
        if not self.token or not self.query_id:
            raise RuntimeError("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID must be set")

    def fetch_raw(self) -> list[dict]:
        ref_code, get_url = self._send_request()
        xml_text = self._get_statement(ref_code, get_url)
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
            })

        return holdings

    def _send_request(self) -> tuple[str, str]:
        url = f"{_BASE_URL}/SendRequest"
        params = {"t": self.token, "q": self.query_id, "v": "3"}
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=30)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        if root.findtext("Status") != "Success":
            raise RuntimeError(f"SendRequest failed: {root.findtext('ErrorMessage')}")

        return root.findtext("ReferenceCode"), root.findtext("Url")

    def _get_statement(self, ref_code: str, get_url: str,
                       retries: int = 5, delay: int = 5) -> str:
        params = {"t": self.token, "q": ref_code, "v": "3"}
        time.sleep(5)

        for attempt in range(1, retries + 1):
            resp = requests.get(get_url, params=params, headers=_HEADERS, timeout=30)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            status = root.findtext("Status")

            if status == "Warn":
                time.sleep(delay)
                continue
            if status == "Fail":
                code = root.findtext("ErrorCode") or "?"
                msg = root.findtext("ErrorMessage") or resp.text
                raise RuntimeError(f"GetStatement failed (code {code}): {msg}")

            return resp.text

        raise RuntimeError("GetStatement: report not ready after max retries")

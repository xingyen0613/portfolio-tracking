"""YuantaConnector — 元大證券月度對帳單 PDF connector.

Credentials (stored encrypted in user_connectors.credentials_json):
    gmail_token_json: str  — Google OAuth token JSON
    pdf_password: str      — PDF decryption password (e.g. ID last 4 + birthdate)

Pipeline (overrides BaseConnector.run()):
    1. authenticate()      → build Gmail service from token, auto-refresh if needed
    2. _find_missing_months() → compare Gmail months vs DB account_snapshots
    3. For each missing month:
       a. _download_month_pdf()       → PDF bytes from Gmail
       b. parse_pdf() + decrypt_pdf() → parsed_json (in-memory)
       c. reconstruct daily holdings  → daily_entries (in-memory)
       d. fetch_month()               → prices from Yahoo Finance
       e. _write_month_to_db()        → normalized_holdings + account_snapshots (multi-date)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# PoC scripts expose reusable low-level functions
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from app.connectors.base import BaseConnector, RunResult

_SENDER = "ebillservice@bhu.yuanta.com.tw"
_SUBJECT_KW = "元大證券電子綜合月對帳單"
_MONTH_RE = re.compile(r"\((\d{4})/(\d{2})\)")
_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class YuantaConnector(BaseConnector):
    platform_name = "yuanta"
    use_pricer = False  # handles prices internally via Yahoo Finance

    def __init__(self, credentials: dict | None = None, account_key: str | None = None):
        super().__init__(credentials, account_key or "yuanta_main")
        self._gmail_service = None
        self._refreshed_token_json: str | None = None

    # -------------------------------------------------------------------------
    # authenticate
    # -------------------------------------------------------------------------

    def authenticate(self) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_json = self._credentials.get("gmail_token_json")
        if not token_json:
            raise ValueError("yuanta connector: missing gmail_token_json in credentials")

        creds = Credentials.from_authorized_user_info(json.loads(token_json), _SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self._refreshed_token_json = creds.to_json()
            else:
                raise ValueError(
                    "Gmail token expired and cannot be refreshed — re-authorize in settings"
                )

        self._gmail_service = build("gmail", "v1", credentials=creds)

    # -------------------------------------------------------------------------
    # Stubs — we override run() so these are never called via run_source_pipeline
    # -------------------------------------------------------------------------

    def fetch_raw(self) -> list[dict]:
        raise NotImplementedError("YuantaConnector uses a custom run() pipeline")

    def parse_holdings(self, raw_payloads: list[dict]) -> list[dict]:
        raise NotImplementedError("YuantaConnector uses a custom run() pipeline")

    # -------------------------------------------------------------------------
    # Custom run() — multi-date monthly pipeline
    # -------------------------------------------------------------------------

    def run(self, batch_id: str, user_id: str) -> RunResult:
        from app.auth.encryption import encrypt
        from app.storage.sqlite import get_account_id
        from config.db import get_conn

        source_run_id = str(uuid.uuid4())

        try:
            account_id = get_account_id(self.platform_name, self.account_key, user_id)
        except ValueError as e:
            return RunResult(source_run_id, self.platform_name, self.account_key, "failed", str(e))

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO source_runs (id, batch_id, account_id, started_at, status, user_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (source_run_id, batch_id, account_id, _now(), "running", user_id),
            )

        try:
            self.authenticate()

            if self._refreshed_token_json:
                _persist_refreshed_token(
                    user_id, self.platform_name, self.account_key,
                    self._credentials, self._refreshed_token_json, encrypt,
                )

            missing_months = self._find_missing_months(account_id, user_id)
            print(f"  [yuanta] missing months: {missing_months or 'none'}", flush=True)

            pdf_password = (
                self._credentials.get("pdf_password")
                or os.environ.get("YUANTA_PDF_PASSWORD", "")
            )

            cum_cash = Decimal(0)
            total_snapshots = 0

            for month in sorted(missing_months):
                pdf_bytes = self._download_month_pdf(month)
                if pdf_bytes is None:
                    print(f"  [yuanta] no PDF in Gmail for {month}, skipping", flush=True)
                    continue

                n, cum_cash = self._process_month(
                    month, pdf_bytes, pdf_password,
                    batch_id, source_run_id, account_id, user_id,
                    start_cum_cash=cum_cash,
                )
                total_snapshots += n

            with get_conn() as conn:
                conn.execute(
                    "UPDATE source_runs SET status='success', finished_at=%s WHERE id=%s",
                    (_now(), source_run_id),
                )

            print(
                f"  [yuanta] wrote {total_snapshots} daily snapshots "
                f"for {len(missing_months)} month(s)",
                flush=True,
            )
            return RunResult(source_run_id, self.platform_name, self.account_key, "success")

        except Exception as e:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE source_runs SET status='failed', finished_at=%s, error_message=%s "
                    "WHERE id=%s",
                    (_now(), str(e), source_run_id),
                )
            return RunResult(source_run_id, self.platform_name, self.account_key, "failed", str(e))

    # -------------------------------------------------------------------------
    # Pipeline steps
    # -------------------------------------------------------------------------

    def _find_missing_months(self, account_id: int, user_id: str) -> list[str]:
        from config.db import get_conn

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT LEFT(CAST(snapshot_date AS TEXT), 7) AS m "
                "FROM account_snapshots WHERE account_id=%s AND user_id=%s",
                (account_id, user_id),
            ).fetchall()
        existing = {r["m"] for r in rows}

        # First connect: limit Gmail search to last 6 months to avoid processing years of PDFs.
        # Subsequent runs: no date filter — picks up any missed months since last sync.
        after = None
        if not existing:
            cutoff = datetime.now(timezone.utc) - timedelta(days=183)
            after = cutoff.strftime("%Y/%m/%d")

        msgs = _gmail_search(self._gmail_service, _SENDER, _SUBJECT_KW, after=after)
        gmail_months: set[str] = set()
        for msg in msgs:
            m = _MONTH_RE.search(msg.get("subject", ""))
            if m:
                gmail_months.add(f"{m.group(1)}-{m.group(2)}")

        return sorted(gmail_months - existing)

    def _download_month_pdf(self, month: str) -> bytes | None:
        after = f"{month[:4]}/{month[5:7]}/01"
        msgs = _gmail_search(self._gmail_service, _SENDER, _SUBJECT_KW, after=after)
        for msg in msgs:
            m = _MONTH_RE.search(msg.get("subject", ""))
            if m and f"{m.group(1)}-{m.group(2)}" == month:
                return _download_pdf_attachment(self._gmail_service, msg["id"])
        return None

    def _process_month(
        self,
        month: str,
        pdf_bytes: bytes,
        pdf_password: str,
        batch_id: str,
        source_run_id: str,
        account_id: int,
        user_id: str,
        start_cum_cash: Decimal,
    ) -> tuple[int, Decimal]:
        from yuanta_pdf_parse_poc import decrypt_pdf, parse_pdf
        from yuanta_daily_reconstruct_poc import compute_anchor, reconstruct_shares, build_daily_entries
        from yuanta_price_fetch_poc import fetch_month as _fetch_prices

        print(f"  [yuanta] processing {month}...", flush=True)

        # 1. Parse PDF (decrypt_pdf needs a file path → use temp file)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = Path(f.name)
        try:
            decrypted = decrypt_pdf(tmp_path, pdf_password)
        finally:
            tmp_path.unlink(missing_ok=True)

        parsed_json = parse_pdf(decrypted)

        # 2. Store raw payload
        raw_payload_id = _write_raw_payload(source_run_id, user_id, month, parsed_json)

        # 3. Reconstruct daily holdings (all in-memory — no filesystem)
        anchor_holdings, anchor_margin = compute_anchor(parsed_json, None)
        shares_series = reconstruct_shares(parsed_json, anchor_holdings)
        daily_entries = build_daily_entries(
            parsed_json, shares_series, anchor_holdings, anchor_margin
        )

        # 4. Fetch prices from Yahoo Finance (owned + pledged stocks)
        symbols = _collect_symbols(daily_entries)
        pledged_stocks = _extract_pledged_stocks(parsed_json)
        symbols = sorted(set(symbols) | {ps["symbol"] for ps in pledged_stocks})

        # Check DB cache — symbols already fully cached for this month can skip Yahoo Finance
        from app.valuation.price_cache import get_month_prices, save_prices as _cache_save
        cached_month = get_month_prices(month, symbols)
        symbols_in_cache = {sym for day in cached_month.values() for sym in day}
        symbols_to_fetch = [s for s in symbols if s not in symbols_in_cache]

        if symbols_to_fetch:
            print(f"  [yuanta] fetching {len(symbols_to_fetch)} symbols from Yahoo Finance (cache miss): {symbols_to_fetch}", flush=True)
            price_doc = _fetch_prices(month, symbols_to_fetch)
            new_prices: dict[str, dict[str, str]] = price_doc.get("prices", {})
            # Save newly fetched prices to cache (TWD)
            for date_str, day_prices in new_prices.items():
                floats = {sym: float(p.replace(",", "")) for sym, p in day_prices.items()}
                if floats:
                    _cache_save(floats, date_str, source="yahoo_finance", currency="TWD")
            # Merge into cached_month (convert floats back to str for prices_by_date)
            for date_str, day_prices in new_prices.items():
                if date_str not in cached_month:
                    cached_month[date_str] = {}
                for sym, p in day_prices.items():
                    cached_month[date_str][sym] = float(p.replace(",", ""))
        else:
            print(f"  [yuanta] all {len(symbols)} symbols served from price cache for {month}", flush=True)

        # Convert back to {date: {sym: str}} for downstream processing
        prices_by_date: dict[str, dict[str, str]] = {
            d: {s: f"{p:.2f}" for s, p in day.items()}
            for d, day in cached_month.items()
        }

        # 5. Write to DB (multi-date)
        other_assets = _extract_other_assets(parsed_json)
        collateral_value = Decimal(
            str(parsed_json.get("summary", {}).get("collateral_total_value", 0) or 0)
            .replace(",", "")
        )
        official_raw = parsed_json.get("summary", {}).get("net_asset")
        official_net_asset = (
            Decimal(str(official_raw).replace(",", ""))
            if official_raw not in (None, "")
            else None
        )
        n, end_cum_cash = _write_month_to_db(
            month, daily_entries, prices_by_date, other_assets,
            pledged_stocks, collateral_value, official_net_asset,
            batch_id, source_run_id, raw_payload_id, account_id, user_id, start_cum_cash,
        )
        return n, end_cum_cash


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def _gmail_search(service, sender: str, subject_kw: str, after: str | None = None) -> list[dict]:
    query = f"from:{sender} subject:{subject_kw} has:attachment"
    if after:
        query += f" after:{after}"

    results = []
    page_token = None
    while True:
        kwargs: dict = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        for msg in resp.get("messages", []):
            detail = (
                service.users().messages()
                .get(userId="me", id=msg["id"], format="metadata",
                     metadataHeaders=["Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            results.append({
                "id": msg["id"],
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def _download_pdf_attachment(service, msg_id: str) -> bytes | None:
    import base64

    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

    def _walk(parts: list) -> bytes | None:
        for part in parts:
            mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            body = part.get("body", {})
            if mime == "application/pdf" or filename.lower().endswith(".pdf"):
                att_id = body.get("attachmentId")
                if att_id:
                    att = (
                        service.users().messages().attachments()
                        .get(userId="me", messageId=msg_id, id=att_id)
                        .execute()
                    )
                    return base64.urlsafe_b64decode(att["data"])
                data = body.get("data")
                if data:
                    return base64.urlsafe_b64decode(data)
            sub = part.get("parts", [])
            if sub:
                result = _walk(sub)
                if result:
                    return result
        return None

    return _walk(msg["payload"].get("parts", []))


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------

def _write_raw_payload(source_run_id: str, user_id: str, month: str, parsed_json: dict) -> str:
    from config.db import get_conn

    raw_payload_id = str(uuid.uuid4())
    content = json.dumps(parsed_json, ensure_ascii=False)
    payload_hash = hashlib.sha256(content.encode()).hexdigest()

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO raw_payloads
               (id, source_run_id, resource_type, file_path, payload_hash,
                fetched_at, parser_status, payload_json, user_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (raw_payload_id, source_run_id, "yuanta_parsed_statement",
             f"yuanta/{month}/parsed.json", payload_hash,
             _now(), "parsed", content, user_id),
        )
    return raw_payload_id


def _write_month_to_db(
    month: str,
    daily_entries: list[dict],
    prices_by_date: dict[str, dict[str, str]],
    other_assets: dict[str, tuple[Decimal, str, str]],
    pledged_stocks: list[dict],
    collateral_value: Decimal,
    official_net_asset: Decimal | None,
    batch_id: str,
    source_run_id: str,
    raw_payload_id: str,
    account_id: int,
    user_id: str,
    start_cum_cash: Decimal,
) -> tuple[int, Decimal]:
    from config.db import get_conn
    from config.settings import PARSER_VERSION
    from yuanta_net_asset_poc import _sum_daily_cashflow, resolve_symbol

    cum_cash = start_cum_cash
    other_assets_total = sum((v[0] for v in other_assets.values()), Decimal(0))
    snapshots_written = 0
    now = _now()
    has_collateral = bool(pledged_stocks) or collateral_value != 0
    last_priced_date: str | None = None
    last_priced_net_asset: Decimal | None = None

    with get_conn() as conn:
        for entry in daily_entries:
            date_str = entry["date"]
            cum_cash += _sum_daily_cashflow(entry)

            day_prices = prices_by_date.get(date_str, {})
            margin = Decimal(str(entry.get("margin_balance") or "0").replace(",", ""))

            if not day_prices:
                # Non-trading day: snapshot with null value
                conn.execute(
                    """INSERT INTO account_snapshots
                       (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (account_id, snapshot_date, batch_id) DO NOTHING""",
                    (str(uuid.uuid4()), batch_id, account_id,
                     date_str, None, "TWD", now, user_id),
                )
                continue

            # Trading day: write per-stock holdings (exclude pledged stocks — written separately as yuanta_collateral)
            pledged_symbols = {ps["symbol"] for ps in pledged_stocks}
            market_value = Decimal(0)
            for h in entry.get("holdings", []):
                sym = resolve_symbol(h)
                shares = int(h.get("shares", 0))
                if not sym or shares <= 0:
                    continue
                if sym in pledged_symbols:
                    continue
                price_str = day_prices.get(sym)
                if price_str is None:
                    continue
                price = float(price_str.replace(",", ""))
                value = shares * price
                market_value += Decimal(str(value))

                conn.execute(
                    """INSERT INTO normalized_holdings
                       (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                        asset_type, quantity, price, value, original_currency,
                        price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()), source_run_id, raw_payload_id,
                     sym, h.get("name"),
                     "tw_stock", shares, price, value, "TWD",
                     "yahoo", date_str, PARSER_VERSION, None, user_id, "yuanta_statement"),
                )

            # net_asset formula: with collateral don't add cum_cash (loan proceeds
            # are already captured in collateral value — double-counting otherwise).
            if has_collateral:
                if pledged_stocks:
                    # Compute daily collateral value from per-stock prices
                    collateral_today = Decimal(0)
                    for ps in pledged_stocks:
                        price_str = day_prices.get(ps["symbol"])
                        if price_str is None:
                            continue
                        price = float(price_str.replace(",", ""))
                        shares = ps["shares"]
                        value = shares * price
                        collateral_today += Decimal(str(value))
                        conn.execute(
                            """INSERT INTO normalized_holdings
                               (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                                asset_type, quantity, price, value, original_currency,
                                price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (str(uuid.uuid4()), source_run_id, raw_payload_id,
                             ps["symbol"], ps["name"],
                             "tw_stock", shares, price, value, "TWD",
                             "yahoo", date_str, PARSER_VERSION, None, user_id, "yuanta_collateral"),
                        )
                    effective_collateral = collateral_today if collateral_today > 0 else collateral_value
                else:
                    # No individual stock data — write aggregate row as fallback
                    effective_collateral = collateral_value
                    conn.execute(
                        """INSERT INTO normalized_holdings
                           (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                            asset_type, quantity, price, value, original_currency,
                            price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (str(uuid.uuid4()), source_run_id, raw_payload_id,
                         "擔保品", "擔保品",
                         "tw_stock", 0, None, float(collateral_value), "TWD",
                         "statement", date_str, PARSER_VERSION, None, user_id, "yuanta_collateral"),
                    )
                net_asset = float(market_value + effective_collateral + other_assets_total - margin)
            else:
                net_asset = float(market_value + other_assets_total + cum_cash - margin)

            conn.execute(
                """INSERT INTO account_snapshots
                   (id, batch_id, account_id, snapshot_date, total_value, currency, created_at, user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (account_id, snapshot_date, batch_id) DO NOTHING""",
                (str(uuid.uuid4()), batch_id, account_id,
                 date_str, net_asset, "TWD", now, user_id),
            )
            snapshots_written += 1
            last_priced_date = date_str
            last_priced_net_asset = Decimal(str(net_asset))

            # Write other components so holdings page can show full breakdown.
            # Each non-stock category (期貨權益 / 海外有價證券 / ...) becomes its own
            # row, classified via _classify_other_asset.
            for label, (value, asset_type, resource_type) in other_assets.items():
                if value == 0:
                    continue
                conn.execute(
                    """INSERT INTO normalized_holdings
                       (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                        asset_type, quantity, price, value, original_currency,
                        price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()), source_run_id, raw_payload_id,
                     label, label,
                     asset_type, 0, None, float(value), "TWD",
                     "statement", date_str, PARSER_VERSION, None, user_id, resource_type),
                )
            if not has_collateral:
                # No pledged stocks — cum_cash represents actual cash balance
                if cum_cash != 0:
                    conn.execute(
                        """INSERT INTO normalized_holdings
                           (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                            asset_type, quantity, price, value, original_currency,
                            price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (str(uuid.uuid4()), source_run_id, raw_payload_id,
                         "現金", "現金",
                         "cash", 0, None, float(cum_cash), "TWD",
                         "statement", date_str, PARSER_VERSION, None, user_id, "yuanta_cash"),
                    )
            # margin debt (stored as negative value)
            if margin != 0:
                conn.execute(
                    """INSERT INTO normalized_holdings
                       (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                        asset_type, quantity, price, value, original_currency,
                        price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (str(uuid.uuid4()), source_run_id, raw_payload_id,
                     "融資借款", "融資借款",
                     "tw_margin", 0, None, float(-margin), "TWD",
                     "statement", date_str, PARSER_VERSION, None, user_id, "yuanta_margin"),
                )

        # Month-end anchor: align last priced day's net_asset with the PDF's
        # official net_asset. Only applies when there's no collateral path
        # (collateral path already excludes cum_cash from net_asset). The gap
        # represents internal transfers that yuanta's transactions table doesn't
        # record (e.g. sub-brokerage funding, external transfers), which would
        # otherwise inflate cum_cash forever as it carries across months.
        if (
            not has_collateral
            and official_net_asset is not None
            and last_priced_date is not None
            and last_priced_net_asset is not None
        ):
            correction = official_net_asset - last_priced_net_asset
            if correction != 0:
                # Adjust the final snapshot
                conn.execute(
                    """UPDATE account_snapshots
                       SET total_value = %s
                       WHERE account_id=%s AND user_id=%s AND snapshot_date=%s AND batch_id=%s""",
                    (float(official_net_asset), account_id, user_id, last_priced_date, batch_id),
                )
                # Adjust the cash row on that day (insert if absent, else update)
                upd = conn.execute(
                    """UPDATE normalized_holdings
                       SET value = value + %s
                       WHERE source_run_id=%s AND user_id=%s AND snapshot_date=%s
                         AND resource_type='yuanta_cash'""",
                    (float(correction), source_run_id, user_id, last_priced_date),
                )
                if upd.rowcount == 0:
                    # No cash row existed (cum_cash was 0 before anchor) — insert one
                    conn.execute(
                        """INSERT INTO normalized_holdings
                           (id, source_run_id, raw_payload_id, platform_symbol, platform_asset_name,
                            asset_type, quantity, price, value, original_currency,
                            price_source, snapshot_date, parser_version, chain, user_id, resource_type)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (str(uuid.uuid4()), source_run_id, raw_payload_id,
                         "現金", "現金",
                         "cash", 0, None, float(correction), "TWD",
                         "statement", last_priced_date, PARSER_VERSION, None, user_id, "yuanta_cash"),
                    )
                cum_cash += correction

    return snapshots_written, cum_cash


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

# label keyword → (asset_type, resource_type) — matched in order, first hit wins.
# Keep this list ordered: more specific keywords before fallback ("其他").
_OTHER_ASSET_MAPPING: list[tuple[str, str, str]] = [
    ("期貨",       "tw_futures_equity", "yuanta_futures_equity"),
    ("海外有價證券", "tw_stock",          "yuanta_sub_brokerage"),
]
_OTHER_ASSET_FALLBACK = ("tw_stock", "yuanta_other")


def _classify_other_asset(label: str) -> tuple[str, str]:
    """Map a yuanta asset_category label → (asset_type, resource_type)."""
    for keyword, asset_type, resource_type in _OTHER_ASSET_MAPPING:
        if keyword in label:
            return asset_type, resource_type
    return _OTHER_ASSET_FALLBACK


def _extract_other_assets(parsed_json: dict) -> dict[str, tuple[Decimal, str, str]]:
    """Extract non-stock categories from parsed_json (no filesystem).

    Returns: {label: (value, asset_type, resource_type)} so each category is
    written as its own normalized_holdings row with the correct classification.
    """
    cats = parsed_json.get("summary", {}).get("asset_categories") or []
    result: dict[str, tuple[Decimal, str, str]] = {}
    for c in cats:
        cat = c.get("category", "")
        if any(x in cat for x in ["上市", "上櫃", "興櫃", "擔保品", "不限用途"]):
            continue
        try:
            value = Decimal(str(c.get("value", "0")).replace(",", ""))
        except Exception:
            continue
        if value != 0:
            label = cat.split("(")[0].strip() or cat
            asset_type, resource_type = _classify_other_asset(label)
            result[label] = (value, asset_type, resource_type)
    return result


def _extract_pledged_stocks(parsed_json: dict) -> list[dict]:
    """Resolve pledged (collateral) stocks to {symbol, name, shares} dicts."""
    from yuanta_net_asset_poc import resolve_name_to_symbol
    result = []
    for h in parsed_json.get("holdings_pledged", []):
        name = h.get("name", "")
        sym = h.get("symbol") or (resolve_name_to_symbol(name) if name else None)
        shares = int(h.get("shares_balance") or 0)
        if sym and shares > 0:
            result.append({"symbol": sym, "name": name, "shares": shares})
    return result


def _collect_symbols(daily_entries: list[dict]) -> list[str]:
    syms: set[str] = set()
    for entry in daily_entries:
        for h in entry.get("holdings", []):
            sym = h.get("symbol")
            if sym:
                syms.add(sym)
    return sorted(syms)


def _persist_refreshed_token(
    user_id: str,
    platform: str,
    account_key: str,
    old_credentials: dict,
    new_token_json: str,
    encrypt,
) -> None:
    from config.db import get_conn

    updated = {**old_credentials, "gmail_token_json": new_token_json}
    encrypted = encrypt(json.dumps(updated))
    with get_conn() as conn:
        conn.execute(
            "UPDATE user_connectors SET credentials_json=%s "
            "WHERE user_id=%s AND platform_name=%s AND account_key=%s",
            (encrypted, user_id, platform, account_key),
        )

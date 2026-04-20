"""Yuanta E-Statement PDF parse PoC.

Slice 1: decrypt encrypted PDF in memory + dump raw text.
Slice 2: parse PDF into structured parsed.json (meta / summary / holdings_owned /
         holdings_pledged / transactions / margin_transactions).

Run:
    # dump raw text for inspection
    uv run python scripts/yuanta_pdf_parse_poc.py \
        --pdf data/raw/yuanta_poc/2026-02/yuanta_statement.pdf --dump-text
    # parse and write parsed.json
    uv run python scripts/yuanta_pdf_parse_poc.py \
        --pdf data/raw/yuanta_poc/2026-02/yuanta_statement.pdf --parse
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import pdfplumber
import pypdf
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATE_RE = r"(\d{4})/(\d{2})/(\d{2})"


# ---------- decrypt + extract ----------

def decrypt_pdf(path: Path, password: str) -> bytes:
    reader = pypdf.PdfReader(str(path))
    if reader.is_encrypted:
        if reader.decrypt(password) == 0:
            raise ValueError(f"Password rejected for {path}")
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def extract_text_pypdf(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(BytesIO(pdf_bytes))
    return "\n\n".join(p.extract_text() or "" for p in reader.pages)


def extract_text_pdfplumber(pdf_bytes: bytes) -> str:
    chunks = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n\n".join(chunks)


def extract_tables(pdf_bytes: bytes) -> list[list[list[str]]]:
    out = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                out.append(table)
    return out


# ---------- helpers ----------

def _iso_date(yyyy_mm_dd: str) -> str:
    """'2026/02/01' -> '2026-02-01'."""
    return yyyy_mm_dd.replace("/", "-")


def _clean_num(s: str | None) -> str | None:
    """'1,234' or '(1,234)' -> '1234' / '-1234'. None / empty -> None."""
    if s is None:
        return None
    s = s.strip()
    if not s or s == "　":
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return ("-" + s) if neg else s


# ---------- meta ----------

def parse_meta(text: str) -> dict:
    meta: dict = {"source": "yuanta_e_statement", "currency": "TWD"}

    m = re.search(r"親愛的\s*(\S+?)\s*客戶", text)
    if m:
        meta["client_name"] = m.group(1)

    m = re.search(r"帳號：(\S+)", text)
    if m:
        meta["account_number"] = m.group(1)

    m = re.search(r"對帳單期間：" + DATE_RE + r"\s*~\s*" + DATE_RE, text)
    if m:
        start = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        end = f"{m.group(4)}-{m.group(5)}-{m.group(6)}"
        meta["period_start"] = start
        meta["period_end"] = end
        meta["as_of_date"] = end

    return meta


# ---------- summary ----------

def parse_summary(text: str) -> dict:
    summary: dict = {}

    # 帳戶總覽 各類別 (label value pct%) — 只抓「資產小計」之前的條目（資產側，不含借貸側）
    categories = []
    for line in text.splitlines():
        if "資產小計" in line:
            break
        m = re.match(r"^(\S[^\d]+?)\s+([\d,]+)\s+(\d+\.\d+)%(?:\s+\S+)?\s*$", line)
        if m and "小計" not in m.group(1) and "總淨額" not in m.group(1):
            categories.append({
                "category": m.group(1).strip(),
                "value": _clean_num(m.group(2)),
                "weight_pct": m.group(3),
            })
    summary["asset_categories"] = categories

    # 三個 totals
    for key, pat in [
        ("total_asset", r"資產小計\s+([\d,]+)\s+\d+(?:\.\d+)?%"),
        ("total_debt", r"借貸小計\s+([\d,]+)\s+\d+(?:\.\d+)?%"),
        ("net_asset", r"資產總淨額\s+([\d,]+)"),
    ]:
        m = re.search(pat, text)
        summary[key] = _clean_num(m.group(1)) if m else None

    # page 3 ※ 那行：借款餘額、整戶擔保維持率、擔保品總市值
    m = re.search(r"借款餘額.*?：\s*([\d,]+)元", text)
    summary["margin_balance"] = _clean_num(m.group(1)) if m else None

    m = re.search(r"整戶擔保維持率：\s*([\d.]+)%", text)
    summary["margin_maintenance_pct"] = m.group(1) if m else None

    m = re.search(r"擔保品總市值.*?：\s*([\d,]+)元", text)
    summary["collateral_total_value"] = _clean_num(m.group(1)) if m else None

    # 上市/櫃合計：成交金額 / 手續費 / 代繳交易稅 / 客戶淨收(付)
    m = re.search(
        r"上市/櫃\(TWD\)合計\s+成交金額：([\d,]+)\s+手續費：([\d,]+)\s+代繳交易稅：([\d,]+).*?客戶淨收\(付\)：(\(?-?[\d,]+\)?)",
        text,
    )
    if m:
        summary["trading_summary"] = {
            "total_amount": _clean_num(m.group(1)),
            "total_fee": _clean_num(m.group(2)),
            "total_tax": _clean_num(m.group(3)),
            "net_cashflow": _clean_num(m.group(4)),
        }
    else:
        summary["trading_summary"] = None

    return summary


# ---------- holdings owned (page 2 庫存明細) ----------

def parse_holdings_owned(text: str) -> list[dict]:
    """Parse 上市櫃庫存明細 — 3-line groups: symbol / values / name."""
    lines = text.splitlines()
    # locate the section
    try:
        start = next(
            i for i, l in enumerate(lines)
            if "上市、上櫃、興櫃庫存明細" in l
        )
    except StopIteration:
        return []

    holdings: list[dict] = []
    i = start + 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("合計：") or line.startswith("※") or "訊息通知" in line:
            break

        # symbol line: 4-7 alphanumeric chars (e.g. 2330, 00631L, 3665)
        if re.fullmatch(r"\w{4,7}", line):
            symbol = line
            # next line: values (numbers separated by spaces)
            if i + 2 >= len(lines):
                break
            value_line = lines[i + 1].strip()
            name = lines[i + 2].strip()

            nums = re.findall(r"[\d,]+(?:\.\d+)?", value_line)
            # 預期完整欄位順序：集保庫存 融資庫存 融券庫存 抵繳品 參考價 融資金額 融券保證金 融券擔保品 融券市值 市值
            # 這份 PDF 只填了 集保庫存 + 參考價 + 市值（其他空），後續月份若有融資/融券再擴
            holding = {
                "symbol": symbol,
                "name": name,
                "raw_values": [_clean_num(n) for n in nums],
            }
            # 保留通用欄位（簡單情況：3 個數字 = 集保庫存/參考價/市值）
            if len(nums) == 3:
                holding["shares_collateral_free"] = _clean_num(nums[0])
                holding["ref_price"] = _clean_num(nums[1])
                holding["market_value"] = _clean_num(nums[2])
            holdings.append(holding)
            i += 3
        else:
            i += 1

    return holdings


# ---------- holdings pledged (page 3 擔保品名單) ----------

def parse_holdings_pledged(tables: list[list[list[str]]]) -> list[dict]:
    """Find the 擔保品 table by header signature.
    PDF only records Chinese name; symbol is not present in this table.
    """
    for table in tables:
        if not table or not table[0]:
            continue
        header = [c or "" for c in table[0]]
        if "擔保品名稱" not in header or "餘額" not in header:
            continue
        out = []
        # Old format (2 cols): ['擔保品名稱', '餘額'] — only name + total shares
        # New format (4 cols): ['擔保品名稱', '庫存股數'/'餘額', '已使用股數', '剩餘股數']
        two_col = len([c for c in header if c]) <= 2
        for row in table[1:]:
            cells = [c or "" for c in row]
            if not cells[0].strip():
                continue
            if two_col:
                out.append({
                    "symbol": None,
                    "name": cells[0].strip(),
                    "shares_balance": _clean_num(cells[1].rstrip("股")),
                    "shares_used": None,
                    "shares_remaining": None,
                })
            else:
                out.append({
                    "symbol": None,
                    "name": cells[0].strip(),
                    "shares_balance": _clean_num(cells[1].rstrip("股")),
                    "shares_used": _clean_num(cells[2].rstrip("股")),
                    "shares_remaining": _clean_num(cells[3].rstrip("股")),
                })
        return out
    return []


# ---------- transactions (page 2 交易明細) ----------

def parse_transactions(text: str) -> list[dict]:
    """3-line groups: '{trade_date} {symbol}' / '{venue} {currency} {side} ...' / '{settle_date} {name}'."""
    lines = text.splitlines()
    try:
        start = next(
            i for i, l in enumerate(lines)
            if "上市、上櫃、興櫃交易明細" in l
        )
    except StopIteration:
        return []

    txns: list[dict] = []
    i = start + 1
    while i < len(lines) - 2:
        line1 = lines[i].strip()
        # 終止條件：碰到合計或新區塊
        if line1.startswith("上市/櫃") or "庫存明細" in line1 or "訊息通知" in line1:
            break

        m1 = re.match(r"^" + DATE_RE + r"\s+(\w{4,7})$", line1)
        if not m1:
            i += 1
            continue

        trade_date = f"{m1.group(1)}-{m1.group(2)}-{m1.group(3)}"
        symbol = m1.group(4)

        line2 = lines[i + 1].strip()
        line3 = lines[i + 2].strip()

        # line2: {venue} {currency} {side} {shares} {price} {amount} {fee} [{tax}] {net_cashflow}
        m2 = re.match(
            r"^(\S+)\s+(\w+)\s+([買賣])\s+([\d,]+)\s+([\d,.]+)\s+([\d,]+)\s+([\d,]+)(?:\s+([\d,]+))?\s+(\(?-?[\d,]+\)?)\s*$",
            line2,
        )
        m3 = re.match(r"^" + DATE_RE + r"\s+(\S+)$", line3)
        if not (m2 and m3):
            i += 1
            continue

        settle_date = f"{m3.group(1)}-{m3.group(2)}-{m3.group(3)}"
        name = m3.group(4)

        txns.append({
            "trade_date": trade_date,
            "settle_date": settle_date,
            "venue": m2.group(1),
            "currency": m2.group(2),
            "side": m2.group(3),
            "symbol": symbol,
            "name": name,
            "shares": _clean_num(m2.group(4)),
            "price": _clean_num(m2.group(5)),
            "amount": _clean_num(m2.group(6)),
            "fee": _clean_num(m2.group(7)),
            "tax": _clean_num(m2.group(8)) if m2.group(8) else None,
            "net_cashflow": _clean_num(m2.group(9)),
        })
        i += 3

    return txns


# ---------- margin transactions (page 3 不限用途借貸明細) ----------

def parse_margin_transactions(tables: list[list[list[str]]]) -> list[dict]:
    """Parse 不限用途款項借貸交易明細 from pdfplumber table.

    Column layout (12 cols):
      0: 日期
      1: 借貸金額 (borrow)
      2: 預支交割款 (advance_settlement, under 借款)
      3: 現金還款 (cash_repay)
      4: 賣股還款 (repay_via_sell)
      5: 預支交割款 (advance_settlement, under 還款)
      6: 匯費 (wire_fee)
      7: 利息 (interest)
      8: 撥券費/設質費 (pledge_fee)
      9: 客戶淨收(付) (net_cashflow)
     10: 退餘額款 (return_balance)
     11: 備註 (note)
    """
    def _cell(row: list, idx: int) -> str | None:
        val = (row[idx] if idx < len(row) else None) or ""
        val = val.strip()
        return val if val else None

    for table in tables:
        # Identify by scanning entire table for required header strings
        flat = " ".join(str(c) for row in table for c in row if c)
        if "借貸金額" not in flat or "不限用途款項借貸交易明細" not in flat:
            continue

        rows: list[dict] = []
        for row in table:
            date_cell = _cell(row, 0) or ""
            m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", date_cell)
            if not m:
                continue
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            rows.append({
                "date": date,
                "borrow": _clean_num(_cell(row, 1)),
                "advance_settlement_out": _clean_num(_cell(row, 2)),
                "cash_repay": _clean_num(_cell(row, 3)),
                "repay_via_sell": _clean_num(_cell(row, 4)),
                "advance_settlement_in": _clean_num(_cell(row, 5)),
                "wire_fee": _clean_num(_cell(row, 6)),
                "interest": _clean_num(_cell(row, 7)),
                "pledge_fee": _clean_num(_cell(row, 8)),
                "net_cashflow": _clean_num(_cell(row, 9)),
                "return_balance": _clean_num(_cell(row, 10)),
                "note": _cell(row, 11),
            })
        return rows
    return []


# ---------- top-level parse ----------

def parse_pdf(pdf_bytes: bytes) -> dict:
    text = extract_text_pdfplumber(pdf_bytes)
    tables = extract_tables(pdf_bytes)
    return {
        "meta": parse_meta(text),
        "summary": parse_summary(text),
        "holdings_owned": parse_holdings_owned(text),
        "holdings_pledged": parse_holdings_pledged(tables),
        "transactions": parse_transactions(text),
        "margin_transactions": parse_margin_transactions(tables),
    }


def write_parsed_json(parsed: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- CLI ----------

YUANTA_POC_DIR = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"


def parse_one(pdf_path: Path, password: str) -> dict:
    pdf_bytes = decrypt_pdf(pdf_path, password)
    parsed = parse_pdf(pdf_bytes)
    out_path = pdf_path.parent / "parsed.json"
    write_parsed_json(parsed, out_path)
    return parsed


def _summary_line(month: str, parsed: dict) -> str:
    s = parsed["summary"]
    m = parsed["meta"]
    return (
        f"{month}  as_of={m.get('as_of_date')}  "
        f"net={s.get('net_asset')}  asset={s.get('total_asset')}  debt={s.get('total_debt')}  "
        f"owned={len(parsed['holdings_owned'])}  pledged={len(parsed['holdings_pledged'])}  "
        f"txns={len(parsed['transactions'])}  margin_txns={len(parsed['margin_transactions'])}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Yuanta E-Statement PDF PoC")
    parser.add_argument("--pdf", type=Path, help="Path to encrypted PDF (single-file mode)")
    parser.add_argument(
        "--engine", choices=["pypdf", "pdfplumber"], default="pdfplumber",
        help="Text extraction engine for --dump-text (default: pdfplumber)",
    )
    parser.add_argument("--dump-text", action="store_true", help="Dump extracted text to stdout")
    parser.add_argument("--parse", action="store_true", help="Parse PDF and write parsed.json next to it")
    parser.add_argument("--print-parsed", action="store_true", help="Print parsed JSON to stdout (with --parse)")
    parser.add_argument(
        "--batch", action="store_true",
        help=f"Scan {YUANTA_POC_DIR}/*/yuanta_statement.pdf and parse each",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    password = os.environ.get("YUANTA_PDF_PASSWORD")
    if not password:
        print("YUANTA_PDF_PASSWORD not set in .env", file=sys.stderr)
        return 1

    if args.batch:
        pdfs = sorted(YUANTA_POC_DIR.glob("*/yuanta_statement.pdf"))
        if not pdfs:
            print(f"No PDFs found under {YUANTA_POC_DIR}/*/yuanta_statement.pdf", file=sys.stderr)
            return 1
        print(f"# batch: {len(pdfs)} PDFs", file=sys.stderr)
        failures = []
        for pdf in pdfs:
            month = pdf.parent.name
            try:
                parsed = parse_one(pdf, password)
                print(_summary_line(month, parsed))
            except Exception as e:
                failures.append((month, str(e)))
                print(f"{month}  ERROR: {e}", file=sys.stderr)
        if failures:
            print(f"\n# {len(failures)} failures", file=sys.stderr)
            return 1
        return 0

    if not args.pdf:
        print("Either --pdf or --batch is required", file=sys.stderr)
        return 1
    if not args.pdf.exists():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1

    pdf_bytes = decrypt_pdf(args.pdf, password)
    print(f"# decrypted {args.pdf} ({len(pdf_bytes)} bytes)", file=sys.stderr)

    if args.dump_text:
        extractor = extract_text_pypdf if args.engine == "pypdf" else extract_text_pdfplumber
        print(f"# engine: {args.engine}", file=sys.stderr)
        print(extractor(pdf_bytes))

    if args.parse:
        parsed = parse_pdf(pdf_bytes)
        out_path = args.pdf.parent / "parsed.json"
        write_parsed_json(parsed, out_path)
        print(f"# wrote {out_path}", file=sys.stderr)
        if args.print_parsed:
            print(json.dumps(parsed, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

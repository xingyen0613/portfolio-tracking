"""
Download Yuanta e-statement PDFs from Gmail using OAuth.

Setup (one-time):
  1. GCP Console → enable Gmail API → create OAuth 2.0 Desktop credentials
  2. Download credentials.json → place at .secrets/gmail_credentials.json
  3. Run --auth to complete browser OAuth flow

Usage:
  --auth                  Run OAuth flow only
  --list [--all]          List matching emails (no download)
  --fetch [--all]         Search and download new PDFs
  --fetch --month 2026-02 Download a specific month only
"""

import argparse
import base64
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = PROJECT_ROOT / ".secrets"
CREDENTIALS_FILE = SECRETS_DIR / "gmail_credentials.json"
TOKEN_FILE = SECRETS_DIR / "gmail_token.json"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "yuanta_poc"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SENDER = "ebillservice@bhu.yuanta.com.tw"
SUBJECT_KEYWORD = "元大證券電子綜合月對帳單"
MONTH_RE = re.compile(r"\((\d{4})/(\d{2})\)")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def authenticate():
    """Return authenticated Gmail API service. Runs browser flow if no token."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: credentials file not found: {CREDENTIALS_FILE}", file=sys.stderr)
        print("  Download from GCP Console → APIs & Services → Credentials", file=sys.stderr)
        sys.exit(1)

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        SECRETS_DIR.mkdir(exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _parse_month(subject: str) -> str | None:
    """Extract YYYY-MM from subject like '元大證券電子綜合月對帳單(2026/03)'."""
    m = MONTH_RE.search(subject)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def search_messages(service, after: str | None = None) -> list[dict]:
    """
    Search Gmail for Yuanta e-statements.

    after: 'YYYY/MM/DD' string to limit search window, or None for all history.
    Returns list of {id, subject, date, month} dicts.
    """
    query = f"from:{SENDER} subject:{SUBJECT_KEYWORD} has:attachment"
    if after:
        query += f" after:{after}"

    results = []
    page_token = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        messages = resp.get("messages", [])
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata",
                     metadataHeaders=["Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            subject = headers.get("Subject", "")
            email_date = headers.get("Date", "")
            month = _parse_month(subject)
            if month is None:
                print(f"  WARN: cannot parse month from subject: {subject!r}", file=sys.stderr)
            results.append({
                "id": msg["id"],
                "subject": subject,
                "date": email_date,
                "month": month,
            })
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_pdf(service, msg_id: str, month: str) -> Path | None:
    """
    Download the first PDF attachment from msg_id into data/raw/yuanta_poc/<month>/.
    Returns the saved path, or None if the file already existed (skip).
    """
    out_dir = RAW_DIR / month
    out_path = out_dir / "yuanta_statement.pdf"

    if out_path.exists():
        print(f"  [skip] {month} already downloaded: {out_path}", file=sys.stderr)
        return None

    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    pdf_bytes = _extract_pdf_attachment(service, msg)
    if pdf_bytes is None:
        print(f"  WARN: no PDF attachment found in message {msg_id}", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pdf_bytes)
    print(f"  [saved] {month} → {out_path} ({len(pdf_bytes):,} bytes)", file=sys.stderr)
    return out_path


def _extract_pdf_attachment(service, msg: dict) -> bytes | None:
    """Walk message parts and return the first PDF attachment bytes."""
    def walk(parts):
        for part in parts:
            mime = part.get("mimeType", "")
            filename = part.get("filename", "")
            body = part.get("body", {})

            if mime == "application/pdf" or filename.lower().endswith(".pdf"):
                att_id = body.get("attachmentId")
                if att_id:
                    att = (
                        service.users()
                        .messages()
                        .attachments()
                        .get(userId="me", messageId=msg["id"], id=att_id)
                        .execute()
                    )
                    return base64.urlsafe_b64decode(att["data"])
                data = body.get("data")
                if data:
                    return base64.urlsafe_b64decode(data)

            sub_parts = part.get("parts", [])
            if sub_parts:
                result = walk(sub_parts)
                if result:
                    return result
        return None

    return walk(msg["payload"].get("parts", []))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Yuanta e-statement PDFs from Gmail"
    )
    parser.add_argument("--auth", action="store_true", help="Run OAuth flow only")
    parser.add_argument("--list", action="store_true", help="List matching emails")
    parser.add_argument("--fetch", action="store_true", help="Download PDFs")
    parser.add_argument(
        "--all", action="store_true",
        help="Search all history (no after: filter)",
    )
    parser.add_argument("--month", help="Limit to a specific month, e.g. 2026-02")
    args = parser.parse_args()

    if args.auth:
        authenticate()
        print("auth OK", file=sys.stderr)
        return 0

    if not args.list and not args.fetch:
        parser.print_help()
        return 1

    service = authenticate()

    if args.all:
        after = None  # no time filter → full history
    else:
        today = date.today()
        after = f"{today.year}/{today.month:02d}/01"

    messages = search_messages(service, after=after)

    if args.month:
        messages = [m for m in messages if m["month"] == args.month]

    if not messages:
        print("No matching emails found.", file=sys.stderr)
        return 0

    if args.list:
        print(f"{'月份':<10}  {'日期':<35}  主旨")
        print("-" * 80)
        for m in sorted(messages, key=lambda x: x["month"] or ""):
            print(f"{m['month'] or '?':<10}  {m['date']:<35}  {m['subject']}")
        return 0

    if args.fetch:
        saved = 0
        skipped = 0
        failed = 0
        for m in sorted(messages, key=lambda x: x["month"] or ""):
            if not m["month"]:
                print(f"  WARN: skipping message with unparseable month: {m['subject']!r}",
                      file=sys.stderr)
                failed += 1
                continue
            result = download_pdf(service, m["id"], m["month"])
            if result:
                saved += 1
            else:
                skipped += 1
        print(
            f"# done: {saved} saved, {skipped} skipped (already exist), {failed} failed",
            file=sys.stderr,
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())

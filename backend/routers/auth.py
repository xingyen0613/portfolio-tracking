import json
import os
import secrets
import threading
import uuid as _uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from google.auth.exceptions import GoogleAuthError
from google_auth_oauthlib.flow import Flow
from jose import JWTError, jwt
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.auth.encryption import encrypt
from app.auth.google_verify import verify_google_token
from app.auth.jwt_utils import create_jwt
from config.db import get_conn
from config import settings
from config.settings import OWNER_GOOGLE_EMAIL, SYSTEM_OWNER_ID

router = APIRouter()

_GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
_OAUTH_STATE_EXPIRE_MINUTES = 10


def _gmail_flow(state: str | None = None) -> Flow:
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uris": [settings.GMAIL_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=_GMAIL_SCOPES,
        redirect_uri=settings.GMAIL_REDIRECT_URI,
        state=state,
    )


class GoogleLoginRequest(BaseModel):
    credential: str


@router.post("/google")
def google_login(body: GoogleLoginRequest):
    try:
        info = verify_google_token(body.credential)
    except (GoogleAuthError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    sub = info["sub"]
    email = info["email"]
    name = info["name"]
    picture = info["picture"]

    with get_conn() as conn:
        if email == OWNER_GOOGLE_EMAIL:
            conn.execute(
                """UPDATE users SET google_id=%s, name=%s, picture=%s, email=%s
                   WHERE id=%s""",
                (sub, name, picture, email, SYSTEM_OWNER_ID),
            )
            user_id = SYSTEM_OWNER_ID
        else:
            new_id = str(_uuid.uuid4())
            cur = conn.execute(
                """INSERT INTO users (id, google_id, email, name, picture)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (google_id) DO UPDATE
                     SET name=EXCLUDED.name, picture=EXCLUDED.picture, email=EXCLUDED.email
                   RETURNING id""",
                (new_id, sub, email, name, picture),
            )
            row = cur.fetchone()
            user_id = str(row["id"])

    token = create_jwt(user_id)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "picture": picture}}


# ── Yuanta Gmail OAuth ────────────────────────────────────────────────────────

class YuantaAuthorizeRequest(BaseModel):
    pdf_password: str
    login_hint: str | None = None


@router.post("/yuanta/gmail/authorize")
def yuanta_gmail_authorize(
    body: YuantaAuthorizeRequest,
    current_user: dict = Depends(get_current_user),
):
    if not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gmail OAuth not configured on this server",
        )

    user_id = current_user["id"]
    code_verifier = secrets.token_urlsafe(64)
    state = jwt.encode(
        {
            "user_id": user_id,
            "pdf_password": body.pdf_password,
            "gmail_address": body.login_hint or "",
            "code_verifier": code_verifier,
            "nonce": str(_uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_OAUTH_STATE_EXPIRE_MINUTES),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    flow = _gmail_flow()
    flow.code_verifier = code_verifier
    auth_kwargs: dict = dict(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    if body.login_hint:
        auth_kwargs["login_hint"] = body.login_hint
    auth_url, _ = flow.authorization_url(**auth_kwargs)
    return {"authorize_url": auth_url}


@router.get("/yuanta/gmail/callback")
def yuanta_gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    if error or not code or not state:
        reason = error or "missing_params"
        return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_error&reason={reason}")

    # Verify state JWT
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = payload["user_id"]
        pdf_password = payload["pdf_password"]
        gmail_address = payload.get("gmail_address", "")
        code_verifier = payload.get("code_verifier")
    except JWTError:
        return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_error&reason=invalid_state")

    if not code_verifier:
        return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_error&reason=stale_state_please_retry")

    # Exchange code for Gmail token
    try:
        flow = _gmail_flow(state=state)
        flow.code_verifier = code_verifier
        flow.fetch_token(code=code)
        token_json = flow.credentials.to_json()
    except Exception:
        return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_error&reason=token_exchange_failed")

    # Upsert connector
    try:
        credentials = {"gmail_token_json": token_json, "pdf_password": pdf_password, "gmail_address": gmail_address}
        encrypted = encrypt(json.dumps(credentials))

        with get_conn() as conn:
            existing = conn.execute(
                """SELECT id FROM user_connectors
                   WHERE user_id=%s AND platform_name='yuanta' AND account_key='yuanta_main'""",
                (user_id,),
            ).fetchone()

            if existing:
                connector_id = str(existing["id"])
                conn.execute(
                    """UPDATE user_connectors
                       SET credentials_json=%s, status='active'
                       WHERE id=%s""",
                    (encrypted, connector_id),
                )
            else:
                connector_id = str(_uuid.uuid4())
                conn.execute(
                    """INSERT INTO user_connectors
                       (id, user_id, platform_name, account_key, label, credentials_json, status, created_at)
                       VALUES (%s, %s, 'yuanta', 'yuanta_main', '元大證券', %s, 'active', NOW())""",
                    (connector_id, user_id, encrypted),
                )
    except Exception:
        return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_error&reason=db_error")

    # Fire-and-forget initial sync
    def _run_batch():
        try:
            from app.jobs.run_batch import run_batch
            run_batch(["yuanta"], user_id, connector_ids=[connector_id])
        except Exception:
            pass

    threading.Thread(target=_run_batch, daemon=True).start()

    return RedirectResponse(url=f"{frontend_url}/?oauth=yuanta_success")

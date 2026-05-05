from fastapi import APIRouter, HTTPException, status
from google.auth.exceptions import GoogleAuthError
from pydantic import BaseModel

from app.auth.google_verify import verify_google_token
from app.auth.jwt_utils import create_jwt
from config.db import get_conn
from config.settings import OWNER_GOOGLE_EMAIL, SYSTEM_OWNER_ID

router = APIRouter()


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
            # Bind the owner's Google account to SYSTEM_OWNER_ID
            conn.execute(
                """UPDATE users SET google_id=%s, name=%s, picture=%s, email=%s
                   WHERE id=%s""",
                (sub, name, picture, email, SYSTEM_OWNER_ID),
            )
            user_id = SYSTEM_OWNER_ID
        else:
            # Upsert regular user by google_id
            cur = conn.execute(
                """INSERT INTO users (google_id, email, name, picture)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (google_id) DO UPDATE
                     SET name=EXCLUDED.name, picture=EXCLUDED.picture
                   RETURNING id""",
                (sub, email, name, picture),
            )
            row = cur.fetchone()
            user_id = str(row["id"])

    token = create_jwt(user_id)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "picture": picture}}

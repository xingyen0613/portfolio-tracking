import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from config.settings import JWT_EXPIRE_DAYS, JWT_SECRET

ALGORITHM = "HS256"


def create_jwt(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "jti": str(uuid.uuid4())},
        JWT_SECRET,
        algorithm=ALGORITHM,
    )


def decode_jwt(token: str) -> dict:
    """Raises jose.JWTError if token is invalid or expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])

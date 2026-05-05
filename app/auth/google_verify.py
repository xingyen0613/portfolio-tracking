from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from config.settings import GOOGLE_CLIENT_ID


def verify_google_token(credential: str) -> dict:
    """Verify Google ID token. Returns {sub, email, name, picture}."""
    info = id_token.verify_oauth2_token(
        credential, google_requests.Request(), GOOGLE_CLIENT_ID
    )
    return {
        "sub": info["sub"],
        "email": info["email"],
        "name": info.get("name", ""),
        "picture": info.get("picture", ""),
    }

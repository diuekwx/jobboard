import os
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import jwt

from backend.core.config import cookie_secure


load_dotenv()

secret_key = os.getenv("SECRET_KEY")
algorithm = os.getenv("ALGORITHM", "HS256")
TOKEN_ISSUER = "job-api"
TOKEN_AUDIENCE = "job-web"


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    minutes = int(os.getenv("AUTH_SESSION_MINUTES", "480"))
    expire = now + (expires_delta or timedelta(minutes=minutes))
    to_encode.update({
        "exp": expire,
        "iat": now,
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
    })
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(token: str):
    return jwt.decode(
        token,
        secret_key,
        algorithms=[algorithm],
        audience=TOKEN_AUDIENCE,
        issuer=TOKEN_ISSUER,
    )


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(response, token: str, csrf_token: str) -> None:
    common = {
        "secure": cookie_secure(),
        "samesite": "lax",
        "path": "/",
    }
    max_age = int(os.getenv("AUTH_SESSION_MINUTES", "480")) * 60
    response.set_cookie(
        "access_token", token, httponly=True, max_age=max_age, **common
    )
    response.set_cookie(
        "csrf_token", csrf_token, httponly=False, max_age=max_age, **common
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie("access_token", path="/", secure=cookie_secure(), samesite="lax")
    response.delete_cookie("csrf_token", path="/", secure=cookie_secure(), samesite="lax")

"""CSRF and small single-process abuse limits for the initial deployment."""

from __future__ import annotations

from collections import defaultdict, deque
from hmac import compare_digest
from threading import Lock
from time import monotonic

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.core.auth import decode_access_token
from backend.core.config import cors_origins


_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class SecurityMiddleware(BaseHTTPMiddleware):
    """Protect cookie-authenticated mutations and bound obvious request floods.

    The rate limiter is intentionally process-local: the supported initial
    deployment has one API process. Replace it with a shared limiter before
    scaling the API horizontally.
    """

    def __init__(self, app):
        super().__init__(app)
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._origins = set(cors_origins())

    def _limited(self, key: tuple[str, str], maximum: int, window: int = 60) -> bool:
        now = monotonic()
        with self._lock:
            bucket = self._requests[key]
            while bucket and bucket[0] <= now - window:
                bucket.popleft()
            if len(bucket) >= maximum:
                return True
            bucket.append(now)
            return False

    async def dispatch(self, request, call_next):
        path = request.url.path
        client = request.client.host if request.client else "unknown"
        if path.startswith("/gmail/auth/google"):
            if self._limited((client, "oauth"), 20):
                return JSONResponse(
                    {"detail": "Too many authentication attempts"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        elif request.method in _UNSAFE and self._limited((client, "mutation"), 120):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        token = request.cookies.get("access_token")
        if request.method in _UNSAFE and token:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in self._origins:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
            cookie_csrf = request.cookies.get("csrf_token", "")
            header_csrf = request.headers.get("x-csrf-token", "")
            try:
                claim_csrf = str(decode_access_token(token).get("csrf", ""))
            except JWTError:
                return JSONResponse({"detail": "Invalid session"}, status_code=401)
            if not cookie_csrf or not header_csrf or not claim_csrf or not (
                compare_digest(cookie_csrf, header_csrf)
                and compare_digest(cookie_csrf, claim_csrf)
            ):
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)

        return await call_next(request)

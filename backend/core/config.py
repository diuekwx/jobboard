"""Runtime configuration and production security invariants."""

from __future__ import annotations

import os
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    pass


_INSECURE_VALUES = {
    "",
    "lol",
    "secret",
    "changeme",
    "replace-with-a-random-local-signing-key",
    "replace-with-a-different-random-local-session-key",
}


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"


def cookie_secure() -> bool:
    return _bool("AUTH_COOKIE_SECURE", default=is_production())


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


def validate_security_config() -> None:
    """Fail closed when a production process has unsafe auth configuration."""
    errors: list[str] = []
    for name in ("SECRET_KEY", "SESSION_SECRET_KEY"):
        if not os.getenv(name):
            errors.append(f"{name} is required")

    if not is_production():
        if errors:
            raise ConfigurationError("Invalid configuration: " + "; ".join(errors))
        return

    for name in ("SECRET_KEY", "SESSION_SECRET_KEY"):
        value = os.getenv(name, "")
        if value.strip().lower() in _INSECURE_VALUES or len(value) < 32:
            errors.append(f"{name} must be a unique secret of at least 32 characters")

    if os.getenv("SECRET_KEY") == os.getenv("SESSION_SECRET_KEY"):
        errors.append("SECRET_KEY and SESSION_SECRET_KEY must be different")
    if os.getenv("ALGORITHM", "HS256") != "HS256":
        errors.append("ALGORITHM must be HS256")
    if not cookie_secure():
        errors.append("AUTH_COOKIE_SECURE must be enabled")

    for name in ("GOOGLE_REDIRECT_URI", "FRONTEND_REDIRECT"):
        value = os.getenv(name, "")
        if urlparse(value).scheme != "https":
            errors.append(f"{name} must use HTTPS")
    for origin in cors_origins():
        if urlparse(origin).scheme != "https":
            errors.append("every CORS_ORIGINS entry must use HTTPS")

    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
        if not os.getenv(name):
            errors.append(f"{name} is required")

    if errors:
        raise ConfigurationError("Unsafe production configuration: " + "; ".join(errors))

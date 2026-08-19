"""Public XY documentation constants."""

import os
from urllib.parse import urlsplit


def _validated_public_docs_url(value: str) -> str:
    """Return a normalized owned docs origin, or an empty preview value."""
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        msg = "XY_DOCS_PUBLIC_URL must be an HTTPS origin/base path without query or fragment"
        raise ValueError(msg)
    return value


PUBLIC_DOCS_URL = _validated_public_docs_url(os.getenv("XY_DOCS_PUBLIC_URL", ""))
PUBLIC_XY_VERSION = os.getenv("XY_DOCS_PUBLIC_VERSION", "0.0.1").strip()
DOCS_CHANNEL = os.getenv("XY_DOCS_CHANNEL", "preview").strip().lower()
SOCIAL_IMAGE_URL = f"{PUBLIC_DOCS_URL}/xy-social-card.png" if PUBLIC_DOCS_URL else ""
LLMS_TXT_PATH = "/llms.txt"
LLMS_FULL_TXT_PATH = "/llms-full.txt"
DOCS_FRONTEND_PATH = "/docs/xy"


def public_docs_url(path: str, *, origin: str | None = None) -> str | None:
    """Build an absolute public URL only when an owned deployment is configured."""
    base = PUBLIC_DOCS_URL if origin is None else _validated_public_docs_url(origin)
    if not base:
        return None
    return f"{base}/{path.lstrip('/')}"


def agent_docs_url(path: str, *, origin: str | None = None) -> str:
    """Return an absolute owned URL or the truthful host-relative docs asset."""
    return public_docs_url(path, origin=origin) or (
        f"{DOCS_FRONTEND_PATH.rstrip('/')}/{path.lstrip('/')}"
    )


def html_agent_docs_href(path: str) -> str:
    """Return an absolute URL or an app-relative href for Reflex routing."""
    return public_docs_url(path) or f"/{path.lstrip('/')}"


if DOCS_CHANNEL not in {"preview", "stable"}:
    msg = "XY_DOCS_CHANNEL must be either 'preview' or 'stable'"
    raise ValueError(msg)

__all__ = [
    "DOCS_CHANNEL",
    "DOCS_FRONTEND_PATH",
    "LLMS_FULL_TXT_PATH",
    "LLMS_TXT_PATH",
    "PUBLIC_DOCS_URL",
    "PUBLIC_XY_VERSION",
    "SOCIAL_IMAGE_URL",
    "agent_docs_url",
    "html_agent_docs_href",
    "public_docs_url",
]

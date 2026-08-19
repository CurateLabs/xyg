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


def public_docs_url(path: str, *, origin: str | None = None) -> str | None:
    """Build an absolute public URL only when an owned deployment is configured."""
    base = PUBLIC_DOCS_URL if origin is None else _validated_public_docs_url(origin)
    if not base:
        return None
    return f"{base}/{path.lstrip('/')}"


if DOCS_CHANNEL not in {"preview", "stable"}:
    msg = "XY_DOCS_CHANNEL must be either 'preview' or 'stable'"
    raise ValueError(msg)

__all__ = [
    "DOCS_CHANNEL",
    "LLMS_FULL_TXT_PATH",
    "LLMS_TXT_PATH",
    "PUBLIC_DOCS_URL",
    "PUBLIC_XY_VERSION",
    "SOCIAL_IMAGE_URL",
    "public_docs_url",
]

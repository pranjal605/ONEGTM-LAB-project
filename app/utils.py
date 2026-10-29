"""Small, dependency-free helpers."""
import re
from datetime import datetime, timezone
from typing import Any

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "proton.me", "protonmail.com", "aol.com", "live.com", "me.com",
}


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = v.split("/")[0].split("?")[0]
    v = v.removeprefix("www.")
    return v or None


def domain_from_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = normalize_domain(email.rsplit("@", 1)[1])
    return None if domain in FREE_EMAIL_DOMAINS else domain


def linkedin_slug(url: str | None) -> str | None:
    """'https://www.linkedin.com/in/jane-doe/' -> 'jane-doe' (works for /company/ too)."""
    if not url:
        return None
    m = re.search(r"linkedin\.com/(?:in|company)/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pick(d: dict | None, *keys: str) -> Any:
    """Return the first non-empty value among `keys` (Forager field names vary by endpoint)."""
    for k in keys:
        v = (d or {}).get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def as_list(data: Any) -> list:
    """Normalise 'list, wrapped list, single object or nothing' into a list."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "emails", "phone_numbers", "phones", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return [data]


def clean_properties(props: dict) -> dict[str, str]:
    """Drop empty values; HubSpot accepts every property value as a string."""
    return {k: str(v) for k, v in props.items() if v not in (None, "", [], {})}

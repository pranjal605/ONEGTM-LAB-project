"""Job-title filtering.

Two layers, so the filter is reliable even if Forager's text search is fuzzy:
  1. server-side: a boolean query is sent to Forager's `role_title` field (narrows what we pay for)
  2. client-side: every returned person is re-checked against include/exclude rules
"""
import re


def build_boolean_query(include: list[str]) -> str | None:
    """['CEO', 'Head of'] -> '"CEO" OR "Head of"'  (Forager needs phrases quoted)."""
    terms = [t.strip().replace('"', "") for t in include if t.strip()]
    return " OR ".join(f'"{t}"' for t in terms) or None


def _contains(title: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", title, re.I) is not None


def title_matches(title: str | None, include: list[str], exclude: list[str] | None = None) -> bool:
    """True if title contains any include term (or include is empty) and no exclude term."""
    if not title:
        return False
    if exclude and any(_contains(title, t) for t in exclude if t.strip()):
        return False
    if not include:
        return True
    return any(_contains(title, t) for t in include if t.strip())

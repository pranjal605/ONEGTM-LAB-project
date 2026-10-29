"""Forager API client (https://docs.forager.ai).

Credit costs (per docs): person detail 1, work email 5, phone 15, role search 1/page,
organization search 1. Every paid response is cached on disk so a retry or a re-run
never pays twice for the same request.
"""
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .utils import as_list, normalize_domain

log = logging.getLogger(__name__)


class ForagerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Forager API {status}: {message}")
        self.status = status


class DiskCache:
    def __init__(self, directory: str):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def get(self, key: str) -> tuple[bool, Any]:
        p = self._path(key)
        if not p.exists():
            return False, None
        try:
            return True, json.loads(p.read_text())["value"]
        except (OSError, ValueError, KeyError):
            return False, None

    def set(self, key: str, value: Any, label: str = "") -> None:
        try:
            self._path(key).write_text(json.dumps({"label": label, "value": value}))
        except OSError:
            log.warning("could not write cache entry")


class ForagerClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self._api = f"{settings.forager_base_url}/api/{settings.forager_account_id}/datastorage"
        self._root = settings.forager_base_url
        self._http = http or httpx.Client(
            timeout=45,
            headers={"X-API-KEY": settings.forager_api_key, "Content-Type": "application/json"},
        )
        self._cache = DiskCache(settings.cache_dir)

    # -- transport -------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        r: httpx.Response | None = None
        for attempt in range(3):
            try:
                r = self._http.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise ForagerError(0, f"network error: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2**attempt)
                continue
            break
        assert r is not None
        if r.status_code >= 400:
            raise ForagerError(r.status_code, r.text[:300])
        return r

    def _post(self, path: str, body: dict) -> Any:
        """POST with disk cache. Empty bodies (nothing found, no charge) are cached as None."""
        key = f"{path}|{json.dumps(body, sort_keys=True)}"
        hit, value = self._cache.get(key)
        if hit:
            log.info("cache hit: %s", path)
            return value
        resp = self._request("POST", f"{self._api}/{path}/", json=body)
        data = resp.json() if resp.content else None
        self._cache.set(key, data, label=path)
        return data

    # -- account ---------------------------------------------------------
    def current_user(self) -> Any:
        return self._request("GET", f"{self._root}/api/users/current/").json()

    # -- organizations ---------------------------------------------------
    def find_organization(self, domain: str | None = None, linkedin_slug: str | None = None) -> dict | None:
        body: dict[str, Any] = {"page": 0}
        if domain:
            body["domains"] = [domain]
        elif linkedin_slug:
            body["linkedin_public_identifiers"] = [linkedin_slug]
        else:
            raise ValueError("domain or linkedin_slug required")
        data = self._post("organization_search", body) or {}
        results = data.get("search_results") or []
        if domain:
            exact = [o for o in results if normalize_domain(o.get("domain") or o.get("website")) == domain]
            return exact[0] if exact else None  # never accept a non-matching company
        return results[0] if results else None

    # -- people ----------------------------------------------------------
    def search_people(self, domain: str, title_query: str | None, page: int = 0,
                      person_name: str | None = None) -> list[dict]:
        body: dict[str, Any] = {"page": page, "organization_domains": [domain], "role_is_current": True}
        if title_query:
            body["role_title"] = title_query
        if person_name:
            body["person_name"] = f'"{person_name}"'
        data = self._post("person_role_search", body) or {}
        return data.get("search_results") or []

    def person_detail(self, person_id: int | None = None, linkedin_slug: str | None = None) -> dict | None:
        if person_id:
            body = {"person_id": int(person_id)}
        elif linkedin_slug:
            body = {"linkedin_public_identifier": linkedin_slug}
        else:
            raise ValueError("person_id or linkedin_slug required")
        return self._post("person_detail_lookup", body)

    def person_by_email(self, email: str) -> dict | None:
        return self._post("person_detail_reverse_lookup/by_email", {"email": email})

    def work_emails(self, person_id: int) -> list[dict]:
        return as_list(self._post("person_contacts_lookup/work_emails", {"person_id": int(person_id)}))

    def phone_numbers(self, person_id: int) -> list:
        return as_list(self._post("person_contacts_lookup/phone_numbers", {"person_id": int(person_id)}))

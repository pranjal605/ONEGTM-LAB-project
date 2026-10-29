"""Minimal HubSpot CRM v3/v4 client (private-app token auth)."""
import logging
import time
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger(__name__)


class HubSpotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HubSpot API {status}: {message}")
        self.status = status


def _flat(obj: dict) -> dict:
    return {"id": str(obj["id"]), **(obj.get("properties") or {})}


class HubSpotClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self._http = http or httpx.Client(
            base_url=settings.hubspot_base_url,
            timeout=30,
            headers={"Authorization": f"Bearer {settings.hubspot_access_token}"},
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        r: httpx.Response | None = None
        for attempt in range(4):
            try:
                r = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if attempt == 3:
                    raise HubSpotError(0, f"network error: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if (r.status_code == 429 or r.status_code >= 500) and attempt < 3:
                time.sleep(2**attempt)
                continue
            break
        assert r is not None
        if r.status_code >= 400:
            raise HubSpotError(r.status_code, r.text[:400])
        return r.json() if r.content else None

    # -- generic object helpers -----------------------------------------
    def _get(self, obj: str, obj_id: str, props: list[str]) -> dict:
        return _flat(self._request("GET", f"/crm/v3/objects/{obj}/{obj_id}", params={"properties": ",".join(props)}))

    def _update(self, obj: str, obj_id: str, props: dict) -> dict:
        return _flat(self._request("PATCH", f"/crm/v3/objects/{obj}/{obj_id}", json={"properties": props}))

    def _create(self, obj: str, props: dict) -> dict:
        return _flat(self._request("POST", f"/crm/v3/objects/{obj}", json={"properties": props}))

    def _search(self, obj: str, filters: list[dict], props: list[str], limit: int = 10,
                sort: str | None = None) -> list[dict]:
        body: dict[str, Any] = {"filterGroups": [{"filters": filters}], "properties": props, "limit": limit}
        if sort:
            body["sorts"] = [{"propertyName": sort, "direction": "ASCENDING"}]
        return [_flat(o) for o in self._request("POST", f"/crm/v3/objects/{obj}/search", json=body)["results"]]

    # -- companies -------------------------------------------------------
    def get_company(self, company_id: str, props: list[str]) -> dict:
        return self._get("companies", company_id, props)

    def update_company(self, company_id: str, props: dict) -> dict:
        return self._update("companies", company_id, props)

    def create_company(self, props: dict) -> dict:
        return self._create("companies", props)

    def find_company_by_domain(self, domain: str) -> dict | None:
        found = self._search("companies", [{"propertyName": "domain", "operator": "EQ", "value": domain}], ["name", "domain"], 1)
        return found[0] if found else None

    # -- contacts --------------------------------------------------------
    def get_contact(self, contact_id: str, props: list[str]) -> dict:
        return self._get("contacts", contact_id, props)

    def update_contact(self, contact_id: str, props: dict) -> dict:
        return self._update("contacts", contact_id, props)

    def create_contact(self, props: dict) -> dict:
        return self._create("contacts", props)

    def find_contact_by(self, prop: str, value: str) -> dict | None:
        found = self._search("contacts", [{"propertyName": prop, "operator": "EQ", "value": value}], ["email", prop], 1)
        return found[0] if found else None

    # -- associations ----------------------------------------------------
    def contacts_of_company(self, company_id: str, props: list[str]) -> list[dict]:
        data = self._request("GET", f"/crm/v4/objects/companies/{company_id}/associations/contacts", params={"limit": 100})
        ids = [str(r["toObjectId"]) for r in (data or {}).get("results", [])]
        if not ids:
            return []
        batch = self._request("POST", "/crm/v3/objects/contacts/batch/read",
                              json={"properties": props, "inputs": [{"id": i} for i in ids]})
        return [_flat(o) for o in batch["results"]]

    def company_id_of_contact(self, contact_id: str) -> str | None:
        data = self._request("GET", f"/crm/v4/objects/contacts/{contact_id}/associations/companies") or {}
        results = data.get("results", [])
        return str(results[0]["toObjectId"]) if results else None

    def associate_contact_company(self, contact_id: str, company_id: str) -> None:
        self._request("PUT", f"/crm/v4/objects/contacts/{contact_id}/associations/default/companies/{company_id}")

    # -- polling fallback ------------------------------------------------
    def created_since(self, obj: str, since_ms: int) -> list[dict]:
        return self._search(obj, [{"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)}],
                            ["createdate"], limit=50, sort="createdate")

    # -- schema ----------------------------------------------------------
    def ensure_properties(self, obj: str, group: str, label: str, defs: list[tuple[str, str, str]]) -> list[str]:
        """Create the property group + any missing custom properties. defs = (name, label, fieldType)."""
        try:
            self._request("POST", f"/crm/v3/properties/{obj}/groups", json={"name": group, "label": label})
        except HubSpotError as exc:
            if exc.status != 409:
                raise
        existing = {p["name"] for p in self._request("GET", f"/crm/v3/properties/{obj}")["results"]}
        created = []
        for name, plabel, field_type in defs:
            if name in existing:
                continue
            self._request("POST", f"/crm/v3/properties/{obj}", json={
                "name": name, "label": plabel, "type": "string",
                "fieldType": field_type, "groupName": group,
            })
            created.append(name)
        return created

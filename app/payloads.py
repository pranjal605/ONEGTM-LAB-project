"""Pull HubSpot object IDs out of the two webhook shapes HubSpot can send."""
from typing import Any


def extract_object_ids(payload: Any, kind: str) -> list[str]:
    """
    kind = 'company' | 'contact'.
      * developer-app subscription: [{"subscriptionType": "company.creation", "objectId": 123}, ...]
      * workflow 'Send a webhook' : {"object": {"objectId": 123, ...}, ...} or {"objectId": 123} or
                                    {"properties": {"hs_object_id": {"value": "123"}}}
    """
    ids: list[str] = []
    if isinstance(payload, list):
        for ev in payload:
            if isinstance(ev, dict) and ev.get("subscriptionType") == f"{kind}.creation" and ev.get("objectId"):
                ids.append(str(ev["objectId"]))
    elif isinstance(payload, dict):
        candidates = [
            payload.get("objectId"),
            (payload.get("object") or {}).get("objectId"),
            (((payload.get("properties") or {}).get("hs_object_id")) or {}).get("value"),
            ((((payload.get("object") or {}).get("properties") or {}).get("hs_object_id")) or {}).get("value"),
            payload.get("hs_object_id"),
        ]
        ids = [str(c) for c in candidates if c][:1]
    return list(dict.fromkeys(ids))

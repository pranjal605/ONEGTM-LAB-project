"""STEP 5 - make a few real Forager calls and save the raw JSON so field names can be verified.

Costs about 3 credits (org search 1 + role search 1 + person detail 1). Emails/phones are NOT
revealed unless you pass --reveal (that costs ~20 more credits).

    python -m scripts.explore_forager
    python -m scripts.explore_forager --reveal
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-v2.forager.ai"
OUT = Path("samples")


def save(name: str, data) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2))
    print(f"  saved samples/{name}.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="openai.com")
    ap.add_argument("--title", default='"CEO" OR "Chief Executive Officer"')
    ap.add_argument("--reveal", action="store_true", help="also fetch work email + phone (~20 credits)")
    args = ap.parse_args()

    key = os.environ.get("FORAGER_API_KEY")
    if not key:
        print("Set FORAGER_API_KEY in your .env first.")
        return 1
    http = httpx.Client(timeout=45, headers={"X-API-KEY": key, "Content-Type": "application/json"})

    print("1) Who am I? (account id)")
    me = http.get(f"{BASE}/api/users/current/")
    print("  status", me.status_code)
    me_json = me.json() if me.content else {}
    save("0_current_user", me_json)
    print("  ->", json.dumps(me_json)[:300])

    account = os.environ.get("FORAGER_ACCOUNT_ID") or str(me_json.get("id") or me_json.get("account_id") or "")
    if not account:
        print("\nCould not find an account id. Open samples/0_current_user.json, find the numeric id,")
        print("put it in .env as FORAGER_ACCOUNT_ID and run again.")
        return 1
    api = f"{BASE}/api/{account}/datastorage"

    print(f"\n2) Organization search for {args.domain} (1 credit)")
    org = http.post(f"{api}/organization_search/", json={"page": 0, "domains": [args.domain]})
    print("  status", org.status_code)
    save("1_organization", org.json())

    print("\n3) Person role search at that company (1 credit)")
    hits = http.post(f"{api}/person_role_search/", json={
        "page": 0, "organization_domains": [args.domain], "role_is_current": True, "role_title": args.title})
    print("  status", hits.status_code)
    hits_json = hits.json()
    save("2_person_role_search", hits_json)

    results = hits_json.get("search_results") or []
    if not results:
        print("No people returned - send me samples/2_person_role_search.json anyway.")
        return 0
    pid = results[0].get("id")

    print(f"\n4) Person detail for id {pid} (1 credit)")
    detail = http.post(f"{api}/person_detail_lookup/", json={"person_id": pid})
    print("  status", detail.status_code)
    save("3_person_detail", detail.json())

    if args.reveal:
        print("\n5) Work email (5 credits) + phone (15 credits)")
        em = http.post(f"{api}/person_contacts_lookup/work_emails/", json={"person_id": pid})
        save("4_work_email", em.json() if em.content else None)
        ph = http.post(f"{api}/person_contacts_lookup/phone_numbers/", json={"person_id": pid})
        save("5_phone", ph.json() if ph.content else None)

    print("\nDone. Zip or paste the files in samples/ (remove nothing - they contain no API key).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

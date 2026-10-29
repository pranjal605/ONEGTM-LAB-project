"""PRIMARY DELIVERABLE: create + enrich the OpenAI company and 5 enriched contacts in HubSpot.

    python -m scripts.demo_openai                      # asks for confirmation (shows credit estimate)
    python -m scripts.demo_openai --limit 5 --yes
    python -m scripts.demo_openai --titles "CEO,CTO,Chief,Head of"
"""
import argparse
import logging

from app.config import get_settings
from app.enrichment import Enricher
from app.forager import ForagerClient
from app.hubspot import HubSpotClient

DOMAIN = "openai.com"


def estimate_credits(limit: int, reveal_email: bool, reveal_phone: bool, pages: int) -> int:
    per_person = 1 + (5 if reveal_email else 0) + (15 if reveal_phone else 0)
    return 1 + pages + limit * per_person


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--titles", help="comma-separated include list (default: DEFAULT_TITLE_INCLUDE)")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = ap.parse_args()

    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    s = get_settings()
    est = estimate_credits(args.limit, s.reveal_work_email, s.reveal_phone, pages=2)
    print(f"Estimated Forager cost: ~{est} credits (cached responses are free on re-runs).")
    if not args.yes and input("Continue? [y/N] ").strip().lower() != "y":
        return

    hs = HubSpotClient(s)
    enricher = Enricher(ForagerClient(s), hs, s)

    company = hs.find_company_by_domain(DOMAIN) or hs.create_company({"name": "OpenAI", "domain": DOMAIN})
    print(f"Company id: {company['id']}")
    org = enricher.enrich_company(company["id"])
    print(f"Enriched company: {org.get('name')} ({org.get('employees_amount')} employees)")

    include = [t.strip() for t in args.titles.split(",")] if args.titles else None
    result = enricher.find_contacts(company["id"], include=include, limit=args.limit)
    print(f"Created + enriched {len(result.created)} contacts: {result.created}")
    if len(result.created) < args.limit:
        print("Fewer than requested - widen the title list (e.g. add 'VP', 'Director', 'Head of').")


if __name__ == "__main__":
    main()

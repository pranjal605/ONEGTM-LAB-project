"""Core business logic: enrich companies, enrich contacts, find contacts by job title."""
import logging
from dataclasses import dataclass, field

from . import mapping
from .config import Settings
from .forager import ForagerClient
from .hubspot import HubSpotClient
from .properties import COMPANY_READ, CONTACT_READ
from .titles import build_boolean_query, title_matches
from .utils import clean_properties, domain_from_email, linkedin_slug, normalize_domain, now_iso

log = logging.getLogger(__name__)

FILL_ONLY = {"name", "domain"}  # never overwrite what a human already typed for these


class EnrichmentSkipped(Exception):
    """Not an error: we lack the data needed to enrich (e.g. company has no domain)."""


@dataclass
class FindResult:
    company_id: str
    created: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    candidates_seen: int = 0


class Enricher:
    def __init__(self, forager: ForagerClient, hubspot: HubSpotClient, settings: Settings):
        self.forager, self.hs, self.cfg = forager, hubspot, settings

    # ------------------------------------------------------------ companies
    def enrich_company(self, company_id: str) -> dict:
        current = self.hs.get_company(company_id, COMPANY_READ)
        domain = normalize_domain(current.get("domain") or current.get("website"))
        slug = linkedin_slug(current.get("linkedin_company_page"))
        if not (domain or slug):
            raise EnrichmentSkipped(f"company {company_id} has no domain or LinkedIn URL")
        org = self.forager.find_organization(domain=domain, linkedin_slug=None if domain else slug)
        if not org:
            raise EnrichmentSkipped(f"Forager has no match for company {company_id}")
        props = mapping.company_properties(org)
        for key in FILL_ONLY:
            if current.get(key):
                props.pop(key, None)
        props["forager_enriched_at"] = now_iso()
        self.hs.update_company(company_id, props)
        log.info("company %s enriched (%d properties)", company_id, len(props))
        return org

    # ------------------------------------------------------------- contacts
    def _resolve_detail(self, props: dict, domain: str | None) -> dict | None:
        """Find the Forager person for a HubSpot contact, cheapest strategy first."""
        if props.get("forager_person_id"):
            return self.forager.person_detail(person_id=int(props["forager_person_id"]))
        slug = linkedin_slug(props.get("person_linkedin_url"))
        if slug:
            return self.forager.person_detail(linkedin_slug=slug)
        name = " ".join(x for x in (props.get("firstname"), props.get("lastname")) if x)
        if name and domain:
            for hit in self.forager.search_people(domain, None, person_name=name):
                if hit.get("id"):
                    return self.forager.person_detail(person_id=hit["id"])
        if props.get("email"):
            return self.forager.person_by_email(props["email"])
        return None

    def enrich_contact(self, contact_id: str) -> dict:
        props = self.hs.get_contact(contact_id, CONTACT_READ)
        company_id = self.hs.company_id_of_contact(contact_id)
        company = self.hs.get_company(company_id, COMPANY_READ) if company_id else {}
        domain = (normalize_domain(company.get("domain")) or normalize_domain(props.get("forager_company_domain"))
                  or domain_from_email(props.get("email")))

        person = self._resolve_detail(props, domain)
        if not person or not person.get("id"):
            raise EnrichmentSkipped(f"Forager could not identify contact {contact_id}")

        role = mapping.current_role(person, domain)
        org_domain = domain or normalize_domain(((role or {}).get("organization") or {}).get("domain"))
        org = self.forager.find_organization(domain=org_domain) if org_domain else None

        email = None if props.get("email") else (
            mapping.best_email(self.forager.work_emails(person["id"])) if self.cfg.reveal_work_email else None)
        phone = None if props.get("phone") else (
            mapping.best_phone(self.forager.phone_numbers(person["id"])) if self.cfg.reveal_phone else None)

        update = mapping.contact_properties(person, role, org, email, phone)
        for key in ("firstname", "lastname"):
            if props.get(key):
                update.pop(key, None)  # keep what the user typed
        update["forager_enriched_at"] = now_iso()
        self.hs.update_contact(contact_id, update)
        if company_id is None and org_domain:
            found = self.hs.find_company_by_domain(org_domain)
            if found:
                self.hs.associate_contact_company(contact_id, found["id"])
        log.info("contact %s enriched (person %s)", contact_id, person["id"])
        return update

    # ----------------------------------------------------- contact finding
    def search_candidates(self, domain: str, include: list[str], exclude: list[str], limit: int) -> list[dict]:
        """Search Forager by job title (server-side), then re-verify every hit client-side."""
        query = build_boolean_query(include)
        seen: dict[int, dict] = {}
        for page in range(self.cfg.max_search_pages):
            hits = self.forager.search_people(domain, query, page=page)
            if not hits:
                break
            for hit in hits:
                title = mapping.candidate_title(hit, domain)
                if hit.get("id") and title_matches(title, include, exclude):
                    seen.setdefault(hit["id"], hit)
            if len(seen) >= limit:
                break
        return list(seen.values())[:limit]

    def find_contacts(self, company_id: str, include: list[str] | None = None,
                      exclude: list[str] | None = None, limit: int | None = None) -> FindResult:
        include = self.cfg.title_include if include is None else include
        exclude = self.cfg.title_exclude if exclude is None else exclude
        limit = min(limit or self.cfg.max_contacts_per_company, 25)

        company = self.hs.get_company(company_id, COMPANY_READ)
        domain = normalize_domain(company.get("domain") or company.get("website"))
        if not domain:
            raise EnrichmentSkipped(f"company {company_id} has no domain; cannot search for people")

        existing = self.hs.contacts_of_company(company_id, CONTACT_READ)
        known_ids = {c.get("forager_person_id") for c in existing if c.get("forager_person_id")}
        known_names = {f"{c.get('firstname', '')} {c.get('lastname', '')}".strip().lower() for c in existing}

        result = FindResult(company_id=company_id)
        candidates = self.search_candidates(domain, include, exclude, limit + len(existing))
        result.candidates_seen = len(candidates)
        for hit in candidates:
            if len(result.created) >= limit:
                break
            name = (hit.get("full_name") or "").strip().lower()
            if str(hit["id"]) in known_ids or name in known_names:
                result.skipped_existing.append(str(hit["id"]))
                continue
            title = mapping.candidate_title(hit, domain)
            first, last = hit.get("first_name"), hit.get("last_name")
            if not first and hit.get("full_name"):
                first, _, last = hit["full_name"].partition(" ")
            # forager_person_id marks the contact as ours, so the contact webhook skips it
            contact = self.hs.create_contact(clean_properties({
                "firstname": first, "lastname": last, "jobtitle": title, "forager_person_id": hit["id"],
            }))
            self.hs.associate_contact_company(contact["id"], company_id)
            self.enrich_contact(contact["id"])
            result.created.append(contact["id"])
        log.info("find_contacts company=%s created=%d", company_id, len(result.created))
        return result

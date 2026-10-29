"""Translate Forager payloads into HubSpot property dicts.

Forager returns rich nested objects; these functions are the single place that knows both
schemas. They are defensive on purpose: a missing field never raises, it is simply omitted.
"""
from typing import Any

from .utils import as_list, clean_properties, linkedin_slug, normalize_domain, pick

_CITY = {"city", "town", "village", "municipality", "locality", "hamlet", "suburb"}
_STATE = {"state", "region", "province", "state_district", "administrative"}


# ---------------------------------------------------------------- companies
def company_properties(org: dict) -> dict[str, str]:
    linkedin = org.get("linkedin_info") or {}
    addr = next((a for a in org.get("addresses") or [] if a.get("country")), {}) or {}
    street = " ".join(x for x in (addr.get("street_number"), addr.get("street_name")) if x)
    founded = org.get("founded_date") or ""
    props = {
        "name": org.get("name"),
        "domain": normalize_domain(org.get("domain") or org.get("website")),
        "website": org.get("website"),
        "description": org.get("description"),
        "numberofemployees": org.get("employees_amount"),
        "annualrevenue": (org.get("finance_info") or {}).get("revenue"),
        "linkedin_company_page": linkedin.get("public_profile_url"),
        "address": street,
        "city": addr.get("city"),
        "state": addr.get("state"),
        "zip": addr.get("postcode"),
        "country": addr.get("country"),
        "founded_year": founded[:4] if founded else None,
        # custom (see properties.py)
        "forager_company_id": org.get("id"),
        "forager_industry": (linkedin.get("industry") or {}).get("name"),
        "forager_employees_range": org.get("employees_range"),
        "forager_founded_date": founded,
        "forager_operating_status": org.get("operating_status"),
        "forager_keywords": ", ".join(k.get("name", "") for k in org.get("keywords") or [] if k.get("name")),
        "forager_domain_rank": org.get("domain_rank"),
        "forager_logo_url": org.get("logo"),
    }
    return clean_properties(props)


# ------------------------------------------------------------------- people
def split_location(location: dict | None) -> dict[str, str | None]:
    """Forager gives one location object; HubSpot wants city / state / country."""
    out: dict[str, str | None] = {"city": None, "state": None, "country": None}
    for osm in (location or {}).get("osm_locations") or []:
        kind, name = (osm.get("place_type") or "").lower(), osm.get("name")
        if kind in _CITY and not out["city"]:
            out["city"] = name
        elif kind in _STATE and not out["state"]:
            out["state"] = name
        elif kind == "country" and not out["country"]:
            out["country"] = name
    if not all(out.values()):  # fall back to "City, State, Country" text
        parts = [p.strip() for p in ((location or {}).get("name") or "").split(",") if p.strip()]
        if len(parts) >= 3:
            out["city"] = out["city"] or parts[0]
            out["state"] = out["state"] or parts[1]
            out["country"] = out["country"] or parts[-1]
        elif len(parts) == 2:
            out["city"] = out["city"] or parts[0]
            out["country"] = out["country"] or parts[1]
        elif len(parts) == 1:
            out["country"] = out["country"] or parts[0]
    return out


def role_title(role: dict | None) -> str | None:
    return pick(role, "role_title", "title", "name", "position")


def current_role(person: dict, domain: str | None = None) -> dict | None:
    """The person's current role, preferring the one at `domain`."""
    roles = [r for r in person.get("roles") or [] if isinstance(r, dict)]
    current = [r for r in roles if r.get("is_current", r.get("current", True))]

    def at_domain(r: dict) -> bool:
        org = r.get("organization") or {}
        return bool(domain) and normalize_domain(org.get("domain") or org.get("website")) == domain

    return next((r for r in current if at_domain(r)), None) or (current[0] if current else None)


def candidate_title(person: dict, domain: str | None) -> str | None:
    """Job title of a person_role_search hit (used by the client-side title filter)."""
    return role_title(current_role(person, domain)) or pick(person, "role_title", "title", "headline")


def person_linkedin_url(person: dict) -> str | None:
    info = person.get("linkedin_info") or {}
    if info.get("public_profile_url"):
        return info["public_profile_url"]
    return f"https://www.linkedin.com/in/{info['public_identifier']}" if info.get("public_identifier") else None


def best_email(items: Any) -> dict | None:
    rank = {"valid": 0, "risky": 1, "unknown": 2}
    ok = [i for i in as_list(items) if isinstance(i, dict) and i.get("email") and i.get("validation_status") != "invalid"]
    return sorted(ok, key=lambda i: rank.get(i.get("validation_status"), 3))[0] if ok else None


def best_phone(items: Any) -> str | None:
    for item in as_list(items):
        number = item if isinstance(item, str) else pick(item, "phone_number", "phone", "number", "e164")
        if number:
            return str(number)
    return None


def _education_lines(person: dict) -> str:
    lines = []
    for e in person.get("educations") or []:
        school = pick(e, "school_name", "school", "institution", "organization_name", "name")
        degree = pick(e, "degree", "degree_name", "field_of_study")
        if school:
            lines.append(f"{school} - {degree}" if degree else str(school))
    return "\n".join(lines)


def contact_properties(person: dict, role: dict | None, org: dict | None,
                       email: dict | None, phone: str | None) -> dict[str, str]:
    first, last = person.get("first_name"), person.get("last_name")
    if not last and person.get("full_name") and " " in person["full_name"].strip():
        first, last = person["full_name"].strip().split(" ", 1)
    loc = split_location(person.get("location"))
    org = org or {}
    org_linkedin = (org.get("linkedin_info") or {}).get("public_profile_url")
    props = {
        "firstname": first,
        "lastname": last,
        "jobtitle": role_title(role),
        "company": org.get("name") or pick((role or {}).get("organization"), "name"),
        "email": (email or {}).get("email"),
        "phone": phone,
        "city": loc["city"],
        "state": loc["state"],
        "country": loc["country"],
        "person_linkedin_url": person_linkedin_url(person),
        "forager_person_id": person.get("id"),
        "forager_company_name": org.get("name"),
        "forager_company_domain": normalize_domain(org.get("domain") or org.get("website")),
        "forager_company_linkedin_url": org_linkedin,
        "forager_email_status": (email or {}).get("validation_status"),
        # "interesting extras" - flagged for discussion in NOTES_extra_details.md
        "forager_headline": person.get("headline"),
        "forager_about": person.get("description"),
        "forager_skills": ", ".join(s.get("name", "") for s in person.get("skills") or [] if isinstance(s, dict) and s.get("name")),
        "forager_education": _education_lines(person),
        "forager_photo_url": person.get("photo"),
    }
    return clean_properties(props)


def employer_slug(org: dict | None) -> str | None:
    return linkedin_slug(((org or {}).get("linkedin_info") or {}).get("public_profile_url"))

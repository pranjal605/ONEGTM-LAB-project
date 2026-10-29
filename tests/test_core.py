import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import mapping
from app.automation import Automation, Deduper
from app.config import Settings
from app.enrichment import Enricher, EnrichmentSkipped
from app.payloads import extract_object_ids
from app.titles import build_boolean_query, title_matches
from app.utils import linkedin_slug, normalize_domain


# ------------------------------------------------------------------ titles
def test_boolean_query_quotes_phrases():
    assert build_boolean_query(["CEO", "Head of"]) == '"CEO" OR "Head of"'
    assert build_boolean_query([]) is None


@pytest.mark.parametrize("title,expected", [
    ("CEO", True), ("Chief Executive Officer", False), ("Head of Research", True),
    ("Software Engineer", False), ("Executive Assistant to the CEO", False), (None, False),
])
def test_title_filter(title, expected):
    assert title_matches(title, ["CEO", "Head of"], ["assistant"]) is expected


def test_title_filter_word_boundaries():
    assert not title_matches("Director of Cleaning", ["CEO"])
    assert title_matches("Co-Founder & CEO", ["CEO"])


# ----------------------------------------------------------------- mapping
def test_location_from_osm():
    loc = {"name": "x", "osm_locations": [
        {"name": "San Francisco", "place_type": "city"},
        {"name": "California", "place_type": "state"},
        {"name": "United States", "place_type": "country"}]}
    assert mapping.split_location(loc) == {"city": "San Francisco", "state": "California", "country": "United States"}


def test_location_text_fallback():
    assert mapping.split_location({"name": "Austin, Texas, United States", "osm_locations": []}) == {
        "city": "Austin", "state": "Texas", "country": "United States"}


def test_best_email_and_phone():
    emails = [{"email": "bad@x.com", "validation_status": "invalid"},
              {"email": "ok@x.com", "validation_status": "risky"},
              {"email": "good@x.com", "validation_status": "valid"}]
    assert mapping.best_email(emails)["email"] == "good@x.com"
    assert mapping.best_email([{"email": "a@x.com", "validation_status": "invalid"}]) is None
    assert mapping.best_phone([{"phone_number": "+14155550100"}]) == "+14155550100"
    assert mapping.best_phone(None) is None


def test_utils():
    assert normalize_domain("https://www.OpenAI.com/about") == "openai.com"
    assert linkedin_slug("https://www.linkedin.com/in/jane-doe/") == "jane-doe"


def test_payload_shapes():
    assert extract_object_ids([{"subscriptionType": "company.creation", "objectId": 5},
                               {"subscriptionType": "contact.creation", "objectId": 6}], "company") == ["5"]
    assert extract_object_ids({"object": {"objectId": 9}}, "contact") == ["9"]
    assert extract_object_ids({"objectId": 11}, "company") == ["11"]


def test_deduper():
    d = Deduper()
    assert d.claim("company", "1") and not d.claim("company", "1") and d.claim("contact", "1")


# --------------------------------------------------- end-to-end with fakes
class FakeForager:
    def __init__(self):
        self.calls = []

    def find_organization(self, domain=None, linkedin_slug=None):
        self.calls.append("org")
        return {"id": 1, "name": "Acme", "domain": domain, "website": f"https://{domain}", "description": "Rockets",
                "employees_amount": 120, "finance_info": {"revenue": 5000000},
                "linkedin_info": {"public_profile_url": "https://linkedin.com/company/acme"},
                "addresses": [{"city": "SF", "state": "CA", "country": "US"}], "keywords": [{"id": 1, "name": "space"}]}

    def search_people(self, domain, title_query, page=0, person_name=None):
        self.calls.append(f"search:{title_query}:{page}")
        if page:
            return []
        mk = lambda i, t: {"id": i, "full_name": f"P{i} Last", "first_name": f"P{i}", "last_name": "Last",
                           "roles": [{"is_current": True, "role_title": t, "organization": {"domain": domain}}]}
        return [mk(1, "CEO"), mk(2, "Software Engineer"), mk(3, "Head of Sales")]

    def person_detail(self, person_id=None, linkedin_slug=None):
        self.calls.append(f"detail:{person_id}")
        return {"id": person_id, "first_name": f"P{person_id}", "last_name": "Last", "full_name": f"P{person_id} Last",
                "headline": "Builder", "description": "About me", "skills": [{"name": "Python"}],
                "location": {"name": "San Francisco, California, United States", "osm_locations": []},
                "linkedin_info": {"public_profile_url": f"https://linkedin.com/in/p{person_id}"},
                "roles": [{"is_current": True, "role_title": "CEO", "organization": {"domain": "acme.com"}}]}

    def work_emails(self, pid):
        self.calls.append("email")
        return [{"email": f"p{pid}@acme.com", "email_type": "work", "validation_status": "valid"}]

    def phone_numbers(self, pid):
        self.calls.append("phone")
        return [{"phone_number": "+14155550100"}]


class FakeHub:
    def __init__(self):
        self.companies = {"c1": {"id": "c1", "domain": "acme.com", "name": "Acme"}}
        self.contacts, self.assoc, self.n = {}, {}, 0

    def get_company(self, cid, props): return dict(self.companies[cid])
    def update_company(self, cid, props): self.companies[cid].update(props)
    def find_company_by_domain(self, d): return next((c for c in self.companies.values() if c.get("domain") == d), None)
    def get_contact(self, cid, props): return dict(self.contacts[cid])
    def update_contact(self, cid, props): self.contacts[cid].update(props)
    def create_contact(self, props):
        self.n += 1
        cid = f"k{self.n}"
        self.contacts[cid] = {"id": cid, **props}
        return self.contacts[cid]
    def associate_contact_company(self, k, c): self.assoc[k] = c
    def company_id_of_contact(self, k): return self.assoc.get(k)
    def contacts_of_company(self, c, props): return [dict(v) for k, v in self.contacts.items() if self.assoc.get(k) == c]


def make(reveal_phone=True):
    cfg = Settings(forager_api_key="x", forager_account_id=1, hubspot_access_token="y", admin_api_key="z",
                   reveal_phone=reveal_phone, max_contacts_per_company=5)
    f, h = FakeForager(), FakeHub()
    return Enricher(f, h, cfg), f, h


def test_find_contacts_filters_titles_and_enriches():
    enr, f, h = make()
    res = enr.find_contacts("c1", include=["CEO", "Head of"], exclude=[])
    assert len(res.created) == 2  # engineer filtered out client-side
    k = h.contacts[res.created[0]]
    assert (k["email"], k["phone"], k["city"], k["state"], k["country"]) == (
        "p1@acme.com", "+14155550100", "San Francisco", "California", "United States")
    assert k["jobtitle"] == "CEO" and k["forager_about"] == "About me"
    assert k["company"] == "Acme" and k["forager_company_domain"] == "acme.com"
    assert h.assoc[res.created[0]] == "c1"


def test_find_contacts_is_idempotent():
    enr, f, h = make()
    enr.find_contacts("c1", include=["CEO", "Head of"], exclude=[])
    again = enr.find_contacts("c1", include=["CEO", "Head of"], exclude=[])
    assert again.created == [] and len(h.contacts) == 2


def test_phone_reveal_can_be_disabled_to_save_credits():
    enr, f, h = make(reveal_phone=False)
    enr.find_contacts("c1", include=["CEO"], exclude=[])
    assert "phone" not in f.calls


def test_company_webhook_finds_contacts_when_none_exist():
    enr, f, h = make()
    Automation(enr).handle_new_company("c1")
    assert h.companies["c1"]["numberofemployees"] == "120"
    assert len(h.contacts) >= 1


def test_company_webhook_enriches_existing_contacts_instead_of_searching():
    enr, f, h = make()
    h.contacts["k9"] = {"id": "k9", "firstname": "P1", "lastname": "Last", "forager_person_id": "1"}
    h.assoc["k9"] = "c1"
    Automation(enr).handle_new_company("c1")
    assert len(h.contacts) == 1 and h.contacts["k9"]["email"] == "p1@acme.com"
    assert not any(c.startswith("search") for c in f.calls)


def test_contact_webhook_skips_contacts_we_created():
    enr, f, h = make()
    h.contacts["k1"] = {"id": "k1", "forager_person_id": "1"}
    Automation(enr).handle_new_contact("k1")
    assert f.calls == []


def test_company_without_domain_is_skipped():
    enr, f, h = make()
    h.companies["c2"] = {"id": "c2", "name": "NoDomain"}
    with pytest.raises(EnrichmentSkipped):
        enr.enrich_company("c2")


# ----------------------------------------------------------- HTTP layer
@pytest.fixture
def client(monkeypatch):
    for k, v in {"FORAGER_API_KEY": "x", "FORAGER_ACCOUNT_ID": "1", "HUBSPOT_ACCESS_TOKEN": "y",
                 "ADMIN_API_KEY": "adm", "WEBHOOK_SECRET": "whs", "HUBSPOT_CLIENT_SECRET": "cs",
                 "PUBLIC_BASE_URL": "https://example.test"}.items():
        monkeypatch.setenv(k, v)
    from app import main
    main.get_settings.cache_clear()
    main.get_automation.cache_clear()
    seen = []

    class Stub:
        dedupe = Deduper()
        def handle_new_company(self, i): seen.append(("company", i))
        def handle_new_contact(self, i): seen.append(("contact", i))

    monkeypatch.setattr(main, "get_automation", lambda: Stub())
    return TestClient(main.app), seen


def test_webhook_requires_secret(client):
    c, _ = client
    assert c.post("/webhooks/hubspot/company", json={"objectId": 1}).status_code == 401
    assert c.post("/webhooks/hubspot/company?secret=wrong", json={"objectId": 1}).status_code == 401


def test_webhook_accepts_and_dedupes(client):
    c, seen = client
    r = c.post("/webhooks/hubspot/company?secret=whs", json={"object": {"objectId": 42}})
    assert r.status_code == 200 and r.json() == {"accepted": ["42"]}
    assert c.post("/webhooks/hubspot/company?secret=whs", json={"objectId": 42}).json() == {"accepted": []}
    assert ("company", "42") in seen


def test_signature_v3(client):
    c, seen = client
    body = json.dumps([{"subscriptionType": "contact.creation", "objectId": 7}]).encode()
    ts = str(int(time.time() * 1000))
    msg = b"POST" + b"https://example.test/webhooks/hubspot/contact" + body + ts.encode()
    sig = base64.b64encode(hmac.new(b"cs", msg, hashlib.sha256).digest()).decode()
    ok = c.post("/webhooks/hubspot/contact", content=body, headers={
        "X-HubSpot-Signature-v3": sig, "X-HubSpot-Request-Timestamp": ts, "Content-Type": "application/json"})
    assert ok.status_code == 200 and ("contact", "7") in seen
    bad = c.post("/webhooks/hubspot/contact", content=body, headers={
        "X-HubSpot-Signature-v3": "nope", "X-HubSpot-Request-Timestamp": ts})
    assert bad.status_code == 401


def test_admin_endpoints_need_key(client):
    c, _ = client
    assert c.post("/api/find-contacts", json={"company_id": "1"}).status_code == 401
    assert c.get("/health").json() == {"status": "ok"}

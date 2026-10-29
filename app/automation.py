"""Event handlers behind the two webhooks (and the optional poller)."""
import logging
import threading
import time

from .enrichment import Enricher, EnrichmentSkipped
from .properties import CONTACT_READ
from .forager import ForagerError
from .hubspot import HubSpotError

log = logging.getLogger(__name__)


class Deduper:
    """HubSpot retries webhooks and the poller can overlap with them; process each object once."""

    def __init__(self, ttl_seconds: int = 900):
        self._ttl, self._seen, self._lock = ttl_seconds, {}, threading.Lock()

    def claim(self, kind: str, object_id: str) -> bool:
        now, key = time.monotonic(), f"{kind}:{object_id}"
        with self._lock:
            self._seen = {k: t for k, t in self._seen.items() if now - t < self._ttl}
            if key in self._seen:
                return False
            self._seen[key] = now
            return True


class Automation:
    def __init__(self, enricher: Enricher):
        self.enricher = enricher
        self.dedupe = Deduper()

    def handle_new_company(self, company_id: str) -> None:
        """Enrich the company; enrich its existing contacts, or find some if it has none."""
        e = self.enricher
        try:
            e.enrich_company(company_id)
            contacts = e.hs.contacts_of_company(company_id, CONTACT_READ)
            if contacts:
                todo = [c for c in contacts if not c.get("forager_enriched_at")][: e.cfg.max_contacts_per_company]
                log.info("company %s has %d contacts, enriching %d", company_id, len(contacts), len(todo))
                for c in todo:
                    self._safe(e.enrich_contact, c["id"])
            else:
                log.info("company %s has no contacts, searching Forager", company_id)
                e.find_contacts(company_id)
        except EnrichmentSkipped as exc:
            log.info("skipped: %s", exc)
        except (ForagerError, HubSpotError):
            log.exception("company webhook failed for %s", company_id)

    def handle_new_contact(self, contact_id: str) -> None:
        e = self.enricher
        try:
            props = e.hs.get_contact(contact_id, CONTACT_READ)
            if props.get("forager_person_id") or props.get("forager_enriched_at"):
                log.info("contact %s already handled, skipping", contact_id)
                return
            e.enrich_contact(contact_id)
        except EnrichmentSkipped as exc:
            log.info("skipped: %s", exc)
        except (ForagerError, HubSpotError):
            log.exception("contact webhook failed for %s", contact_id)

    @staticmethod
    def _safe(fn, *args) -> None:
        try:
            fn(*args)
        except EnrichmentSkipped as exc:
            log.info("skipped: %s", exc)
        except (ForagerError, HubSpotError):
            log.exception("enrichment failed for %s", args)

"""Optional fallback for HubSpot accounts without webhook support (ENABLE_POLLER=true).

Polls HubSpot for newly created companies/contacts and feeds them to the same handlers
the webhooks use. Prefer real webhooks; this exists so a free HubSpot account still works.
"""
import logging
import threading
import time

from .automation import Automation
from .hubspot import HubSpotClient, HubSpotError

log = logging.getLogger(__name__)


def run_poller(automation: Automation, hs: HubSpotClient, interval: int, stop: threading.Event) -> None:
    since = int(time.time() * 1000)
    log.info("poller started (every %ss)", interval)
    while not stop.wait(interval):
        started = int(time.time() * 1000) - 5000  # small overlap; Deduper absorbs repeats
        for obj, kind, handler in (
            ("companies", "company", automation.handle_new_company),
            ("contacts", "contact", automation.handle_new_contact),
        ):
            try:
                for rec in hs.created_since(obj, since):
                    if automation.dedupe.claim(kind, rec["id"]):
                        handler(rec["id"])
            except HubSpotError:
                log.exception("poll failed for %s", obj)
        since = started

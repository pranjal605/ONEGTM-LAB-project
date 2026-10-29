"""FastAPI entrypoint: HubSpot webhooks + admin endpoints for on-demand enrichment."""
import json
import logging
import threading
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .automation import Automation
from .config import Settings, get_settings
from .enrichment import Enricher, EnrichmentSkipped
from .forager import ForagerClient, ForagerError
from .hubspot import HubSpotClient, HubSpotError
from .payloads import extract_object_ids
from .poller import run_poller
from .security import authorize_admin, authorize_webhook

log = logging.getLogger("app")


@lru_cache
def get_automation() -> Automation:
    s = get_settings()
    return Automation(Enricher(ForagerClient(s), HubSpotClient(s), s))


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    if s.enable_poller:
        auto = get_automation()
        threading.Thread(target=run_poller, args=(auto, auto.enricher.hs, s.poll_interval_seconds, stop),
                         daemon=True).start()
    yield
    stop.set()


app = FastAPI(title="Forager x HubSpot enrichment", version="1.0.0", lifespan=lifespan)


# ------------------------------------------------------------------ models
class CompanyRef(BaseModel):
    company_id: str


class ContactRef(BaseModel):
    contact_id: str


class FindContactsRequest(BaseModel):
    company_id: str
    include_titles: list[str] | None = Field(None, description='e.g. ["CTO", "Head of Engineering"]')
    exclude_titles: list[str] | None = None
    limit: int = Field(5, ge=1, le=25)


def admin(x_api_secret: str | None = Header(None), settings: Settings = Depends(get_settings)) -> None:
    authorize_admin(settings, x_api_secret)


def _run(fn, *args):
    try:
        return fn(*args)
    except EnrichmentSkipped as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ForagerError, HubSpotError) as exc:
        raise HTTPException(502, str(exc)) from exc


# ---------------------------------------------------------------- health
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# -------------------------------------------------------------- webhooks
async def _handle_webhook(kind: str, request: Request, background: BackgroundTasks, secret: str) -> dict:
    settings, auto = get_settings(), get_automation()
    body = await request.body()
    authorize_webhook(settings, request, body, secret)
    try:
        payload = json.loads(body or b"{}")
    except ValueError as exc:
        raise HTTPException(400, "body is not valid JSON") from exc
    handler = auto.handle_new_company if kind == "company" else auto.handle_new_contact
    accepted = []
    for object_id in extract_object_ids(payload, kind):
        if auto.dedupe.claim(kind, object_id):
            background.add_task(handler, object_id)  # respond fast; HubSpot times out after ~5s
            accepted.append(object_id)
    log.info("%s webhook accepted=%s", kind, accepted)
    return {"accepted": accepted}


@app.post("/webhooks/hubspot/company")
async def company_webhook(request: Request, background: BackgroundTasks, secret: str = "") -> dict:
    return await _handle_webhook("company", request, background, secret)


@app.post("/webhooks/hubspot/contact")
async def contact_webhook(request: Request, background: BackgroundTasks, secret: str = "") -> dict:
    return await _handle_webhook("contact", request, background, secret)


# -------------------------------------------------- on-demand (admin) API
@app.post("/api/enrich/company", dependencies=[Depends(admin)])
def enrich_company(req: CompanyRef) -> dict:
    org = _run(get_automation().enricher.enrich_company, req.company_id)
    return {"company_id": req.company_id, "forager_company_id": org.get("id"), "name": org.get("name")}


@app.post("/api/enrich/contact", dependencies=[Depends(admin)])
def enrich_contact(req: ContactRef) -> dict:
    return {"contact_id": req.contact_id, "updated": _run(get_automation().enricher.enrich_contact, req.contact_id)}


@app.post("/api/find-contacts", dependencies=[Depends(admin)])
def find_contacts(req: FindContactsRequest) -> dict:
    r = _run(get_automation().enricher.find_contacts, req.company_id, req.include_titles, req.exclude_titles, req.limit)
    return {"company_id": r.company_id, "created_contact_ids": r.created,
            "skipped_existing": r.skipped_existing, "candidates_seen": r.candidates_seen}


@app.get("/health")
def health_check():
    return {"status": "ok"}
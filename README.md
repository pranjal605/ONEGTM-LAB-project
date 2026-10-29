# Forager x HubSpot Enrichment Automation

Python (FastAPI) service that enriches HubSpot companies and contacts with Forager data,
finds new contacts by job title, and reacts to HubSpot "created" webhooks.

## What it does
| # | Requirement | Where |
|---|---|---|
| 1 | Enrich companies | `Enricher.enrich_company`, `POST /api/enrich/company` |
| 2 | Enrich contacts | `Enricher.enrich_contact`, `POST /api/enrich/contact` |
| 3 | Find contacts by job title | `Enricher.find_contacts`, `POST /api/find-contacts` (`include_titles`, `exclude_titles`, `limit`) |
| 4 | Company webhook | `POST /webhooks/hubspot/company` - enrich company; enrich existing contacts, or find new ones if none |
| 5 | Contact webhook | `POST /webhooks/hubspot/contact` - enrich the new contact |

## Design notes
- **Job-title filtering is two-layered**: a quoted boolean query goes to Forager's `role_title`
  (so we only pay for relevant people), then every hit is re-checked client-side with word-boundary
  include/exclude rules (`app/titles.py`).
- **Credit-aware**: person detail = 1, work email = 5, phone = 15 credits. All Forager responses are
  cached on disk (`CACHE_DIR`), `REVEAL_PHONE` / `REVEAL_WORK_EMAIL` / `MAX_CONTACTS_PER_COMPANY` cap spend,
  and the demo script prints a cost estimate first.
- **No webhook loops / double spend**: contacts we create carry `forager_person_id`, so the contact webhook
  skips them; a TTL de-duplicator absorbs HubSpot retries.
- **Fast webhooks**: they authenticate, return 200 immediately, and process in a background task.
- **Safe writes**: `name` and `domain` and first/last name are only filled, never overwritten.
- **Secrets only via env vars** (`.env.example`). Nothing is hard-coded.
- **Webhook auth**: HubSpot signature v3 (developer-app subscriptions) or a shared `?secret=` (workflows).
- Optional `ENABLE_POLLER=true` polls HubSpot for new records for accounts that cannot send webhooks.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in values
python -m scripts.setup_hubspot # creates custom properties in HubSpot
pytest                          # 25 offline tests
uvicorn app.main:app --reload
```
HubSpot private app scopes: `crm.objects.companies.read/write`, `crm.objects.contacts.read/write`,
`crm.schemas.companies.read/write`, `crm.schemas.contacts.read/write`.

## Primary demo (OpenAI + 5 people)
```bash
python -m scripts.demo_openai --limit 5
```

## Deploy (Railway)
Connect the GitHub repo, add every variable from `.env.example` in the Variables tab, set
`PUBLIC_BASE_URL` to the Railway URL. Start command comes from `Procfile`.

## HubSpot webhook URLs
- Company: `https://<your-app>.up.railway.app/webhooks/hubspot/company?secret=<WEBHOOK_SECRET>`
- Contact: `https://<your-app>.up.railway.app/webhooks/hubspot/contact?secret=<WEBHOOK_SECRET>`

## On-demand API example
```bash
curl -X POST https://<app>/api/find-contacts -H "X-API-Secret: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"company_id":"123","include_titles":["CTO","Head of Engineering"],"limit":2}'
```

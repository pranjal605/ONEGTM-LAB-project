# Video walkthrough script (aim for 4-6 minutes)

1. **Intro (20s)** - "Python FastAPI service connecting Forager and HubSpot, deployed on Railway."
2. **Code tour (60s)** - show `app/forager.py`, `app/enrichment.py`, `app/titles.py`; mention env vars, caching, credit controls.
3. **Primary deliverable (60s)** - open HubSpot: OpenAI company (description, revenue, headcount) and the 5 contacts (email, phone, city, state, country, LinkedIn, employer details).
4. **Job-title filtering (60s)** - call `/api/find-contacts` with `{"include_titles":["CTO"],"limit":1}` (Swagger UI at `/docs`); show only matching titles come back.
5. **Company webhook (60s)** - create a new company in HubSpot (name + domain); show Railway logs receiving the webhook; refresh HubSpot: company enriched + contacts found.
6. **Contact webhook (45s)** - create a new contact with a LinkedIn URL (+ company); show log + enriched fields.
7. **Extras + wrap-up (30s)** - mention `NOTES_extra_details.md`, credit-saving choices.

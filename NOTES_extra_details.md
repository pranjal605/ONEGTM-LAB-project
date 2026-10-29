# Interesting extra details Forager surfaces (for discussion)

Already stored in HubSpot as optional custom properties (easy to drop if not wanted):

**People**
- `forager_about` - the person's description / LinkedIn "About" text (flagged in the brief)
- `forager_headline` - LinkedIn headline
- `forager_skills`, `forager_education` - skills and schools
- `forager_email_status` - validation of the work email (valid / risky / unknown) - useful for deliverability
- `forager_photo_url`

**Companies**
- `forager_industry`, `forager_employees_range`, `forager_founded_date`, `forager_operating_status`
- `forager_keywords` - topic keywords, good for segmentation / personalisation
- `forager_domain_rank` - website popularity signal

Available from Forager but **not** yet pulled (candidates to discuss):
- Funding events (type, total, date) - strong buying-intent signal
- Active job posts per company (title, remote, source) - hiring = budget signal
- Web technologies / tech stack per domain (website lookup endpoint)
- Full role history, certifications, languages, honors, publications, patents
- Personal emails (extra 5 credits) - recommend NOT storing by default (privacy / GDPR)
- Verification-feedback endpoints (report bad phones/emails back to Forager)

Cost reality: phone numbers are 15 credits each, the most expensive field. Suggest enriching phones
only for contacts that pass a qualification step.

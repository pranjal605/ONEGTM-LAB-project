"""Custom HubSpot properties this service writes (standard properties need no setup)."""

GROUP = "forager_enrichment"
GROUP_LABEL = "Forager Enrichment"

# (internal name, label, fieldType)
COMPANY_PROPERTIES = [
    ("forager_company_id", "Forager Company ID", "text"),
    ("forager_industry", "Forager Industry", "text"),
    ("forager_employees_range", "Forager Employees Range", "text"),
    ("forager_founded_date", "Forager Founded Date", "text"),
    ("forager_operating_status", "Forager Operating Status", "text"),
    ("forager_keywords", "Forager Keywords", "textarea"),
    ("forager_domain_rank", "Forager Domain Rank", "text"),
    ("forager_logo_url", "Forager Logo URL", "text"),
    ("forager_enriched_at", "Forager Enriched At", "text"),
]

CONTACT_PROPERTIES = [
    ("forager_person_id", "Forager Person ID", "text"),
    ("forager_enriched_at", "Forager Enriched At", "text"),
    ("person_linkedin_url", "Person LinkedIn URL", "text"),
    ("forager_company_name", "Employer Name", "text"),
    ("forager_company_domain", "Employer Domain", "text"),
    ("forager_company_linkedin_url", "Employer LinkedIn URL", "text"),
    ("forager_email_status", "Email Validation Status", "text"),
    ("forager_headline", "LinkedIn Headline (extra)", "text"),
    ("forager_about", "LinkedIn About (extra)", "textarea"),
    ("forager_skills", "Skills (extra)", "textarea"),
    ("forager_education", "Education (extra)", "textarea"),
    ("forager_photo_url", "Photo URL (extra)", "text"),
]

COMPANY_READ = ["name", "domain", "website", "linkedin_company_page", "forager_company_id", "forager_enriched_at"]
CONTACT_READ = [
    "firstname", "lastname", "email", "phone", "jobtitle", "company", "city", "state", "country",
    "person_linkedin_url", "forager_person_id", "forager_enriched_at", "forager_company_domain",
]

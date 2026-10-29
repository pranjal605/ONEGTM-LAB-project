"""One-off: create the custom HubSpot properties this service writes.  Run:  python -m scripts.setup_hubspot"""
from app.config import get_settings
from app.hubspot import HubSpotClient
from app.properties import COMPANY_PROPERTIES, CONTACT_PROPERTIES, GROUP, GROUP_LABEL

if __name__ == "__main__":
    hs = HubSpotClient(get_settings())
    for obj, defs in (("companies", COMPANY_PROPERTIES), ("contacts", CONTACT_PROPERTIES)):
        created = hs.ensure_properties(obj, GROUP, GROUP_LABEL, defs)
        print(f"{obj}: created {created or 'nothing (already set up)'}")

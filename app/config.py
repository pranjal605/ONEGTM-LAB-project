"""Application settings, loaded from environment variables (or a local .env file)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    forager_api_key: str
    forager_account_id: int
    forager_base_url: str = "https://api-v2.forager.ai"

    hubspot_access_token: str
    hubspot_base_url: str = "https://api.hubapi.com"

    admin_api_key: str
    webhook_secret: str = ""
    hubspot_client_secret: str = ""
    public_base_url: str = ""

    reveal_work_email: bool = True
    reveal_phone: bool = True
    max_contacts_per_company: int = 5
    max_search_pages: int = 3

    default_title_include: str = (
        "CEO,Chief Executive Officer,CTO,Chief Technology Officer,Chief,VP,Vice President,Head of,Director"
    )
    default_title_exclude: str = "intern,assistant"

    cache_dir: str = ".cache"
    enable_poller: bool = False
    poll_interval_seconds: int = 60
    log_level: str = "INFO"

    @property
    def title_include(self) -> list[str]:
        return _split(self.default_title_include)

    @property
    def title_exclude(self) -> list[str]:
        return _split(self.default_title_exclude)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

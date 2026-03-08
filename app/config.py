"""
Application configuration loaded from environment variables.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # Scheduled job hours (24h UTC)
    curve_update_hour: int = 8
    ipca_update_hour: int = 9

    # External APIs
    bcb_sgs_base_url: str = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
    http_timeout: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()

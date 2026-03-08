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

    # LFT (Tesouro Selic) VNA anchor
    # The LFT VNA is computed by accumulating the daily SELIC factor (BCB SGS 12)
    # from a known reference point. Update this pair whenever a reliable VNA is
    # published by Tesouro Nacional / BCB (e.g. monthly).
    lft_vna_anchor: float = 18_503.43   # VNA as of lft_vna_anchor_date
    lft_vna_anchor_date: str = "2026-03-07"  # ISO date of the anchor value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


settings = Settings()

"""Application settings loaded from environment variables and the local .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> app/core -> app -> apps/api
API_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = API_DIR / ".env"

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://copilot:copilot_dev_password@127.0.0.1:5432/copilot"
)
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: str = DEFAULT_CORS_ORIGINS
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_model_complex: str = "deepseek-v4-pro"

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS as a list; empty entries are dropped."""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def ai_configured(self) -> bool:
        """True only when a non-blank DEEPSEEK_API_KEY is present."""
        return bool(self.deepseek_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()

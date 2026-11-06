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
# Upper bound on how much retrieved context one tutor call may carry.
KNOWLEDGE_TOP_K_MAX = 10


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

    # Sprint 4: one upper bound on how long a tutor call may take, and one on how
    # many tokens the tutor may spend per learner per UTC day.
    ai_timeout_seconds: float = 30.0
    ai_daily_token_limit: int = 50000
    # Sprint 5 knowledge base. Ingestion is OFF unless an operator turns it on:
    # the endpoint is a write path, so the default must be a 403 that costs nothing.
    # 研究专栏：抓取技术新闻/论文。默认关闭；关闭时相关端点拒绝请求，不出网。
    news_enabled: bool = False
    # 只接受目录里的键（hn / arxiv-ai / gh-nextjs），不接受 URL。
    news_sources: str = "hn,arxiv-ai,gh-nextjs"
    news_limit_per_source: int = 8
    # 提炼前先抓原文正文；抓多少字进提示。抓不到就退回摘要，不假装看过。
    news_article_chars: int = 2500
    knowledge_ingest_enabled: bool = False
    knowledge_stale_days: int = 30
    knowledge_top_k: int = 3
    # The only pages ingestion may read are docs.python.org document pages listed
    # here. Nothing else is ever fetched - repo lessons come from the lessons table.
    knowledge_doc_urls: str = (
        "https://docs.python.org/3/tutorial/introduction.html,"
        "https://docs.python.org/3/tutorial/controlflow.html,"
        "https://docs.python.org/3/whatsnew/3.13.html"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS_ORIGINS as a list; empty entries are dropped."""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def ai_configured(self) -> bool:
        """True only when a non-blank DEEPSEEK_API_KEY is present."""
        return bool(self.deepseek_api_key.strip())

    @property
    def news_source_key_list(self) -> list[str]:
        return [part.strip() for part in self.news_sources.split(",") if part.strip()]

    @property
    def knowledge_doc_url_list(self) -> list[str]:
        """KNOWLEDGE_DOC_URLS as a list; blank entries are dropped."""
        return [item.strip() for item in self.knowledge_doc_urls.split(",") if item.strip()]

    @property
    def knowledge_stale_days_bounded(self) -> int:
        """At least one day, so a misconfigured 0 can never mark everything stale."""
        return max(int(self.knowledge_stale_days), 1)

    @property
    def knowledge_top_k_bounded(self) -> int:
        """1..KNOWLEDGE_TOP_K_MAX citations per tutor call."""
        return min(max(int(self.knowledge_top_k), 1), KNOWLEDGE_TOP_K_MAX)


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()

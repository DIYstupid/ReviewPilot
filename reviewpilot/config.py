from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReviewPilot"
    app_env: str = "development"
    app_secret_key: str = Field(default="change-me")
    session_signing_key: str = Field(default="change-me")
    session_encryption_key: str = Field(default="change-me")
    database_url: str = "sqlite:///./reviewpilot.db"
    cache_dir: str = ".cache/reviewpilot"
    review_fetch_mode: str = "offline"
    review_llm_provider: str = "offline"
    review_static_validator: str = "none"

    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_pat: str | None = None

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    qwen_api_key: str | None = None
    qwen_base_url: str | None = None
    qwen_model: str = "qwen2.5-coder"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_settings() -> None:
    settings = get_settings()
    if settings.app_env == "development":
        return
    defaults = {"change-me"}
    if settings.session_signing_key in defaults:
        raise RuntimeError("session_signing_key must not use default in production")
    if settings.session_encryption_key in defaults:
        raise RuntimeError("session_encryption_key must not use default in production")

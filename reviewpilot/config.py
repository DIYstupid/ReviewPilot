from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReviewPilot"
    app_env: str = "development"
    app_secret_key: str = Field(default="change-me")
    database_url: str = "sqlite:///./reviewpilot.db"
    cache_dir: str = ".cache/reviewpilot"
    review_fetch_mode: str = "offline"
    review_llm_provider: str = "offline"

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

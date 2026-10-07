from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MangaThai AI"
    app_secret: str = "change-me-in-production"
    database_url: str = "sqlite:///./mangathai.db"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_model: str = "gpt-6-astra"
    mock_mode: bool = True
    max_upload_mb: int = 20
    upload_limit_pages: int = 20
    cookie_https_only: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

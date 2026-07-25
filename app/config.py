from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRACT_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./orchestract.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EDITH-X V2"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    secret_key: str = Field(default="change-me-in-production", min_length=16)
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    database_url: PostgresDsn = "postgresql+psycopg://edith:edith@localhost:5432/edith"
    redis_url: RedisDsn = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    sandbox_image: str = "edith-x/sandbox:latest"
    sandbox_cpu_limit: float = 1.0
    sandbox_memory_mb: int = 512
    self_heal_max_iterations: int = 5

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    rate_limit_per_minute: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()

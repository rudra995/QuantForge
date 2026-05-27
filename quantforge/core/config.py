from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for the QuantForge quantitative trading platform.

    Loads configuration from environment variables or a local .env file.
    """

    ENV: Literal["dev", "prod"] = Field(
        default="dev",
        description="Application environment mode. Must be either 'dev' or 'prod'."
    )

    LOG_LEVEL: Literal["debug", "info", "warning", "error", "critical"] = Field(
        default="info",
        description="Minimum log level for structlog logging output."
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/quantforge",
        description="Asynchronous database connection URL using the asyncpg dialect."
    )

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Connection URL for Redis cache and broker storage."
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


# Instantiate settings for global configuration access
settings = Settings()

"""Validated settings loaded from environment variables and optional .env."""

from functools import lru_cache
import re
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevRelay AI API"
    environment: str = "development"
    log_level: str = "INFO"
    nebius_base_url: str = "https://api.tokenfactory.us-central1.nebius.com/v1/"
    nebius_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nebius_api_key: SecretStr | None = None
    nebius_timeout_seconds: float = Field(default=30.0, gt=0, le=600)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("nebius_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname or ""
            port = parsed.port
        except ValueError as exc:
            raise ValueError("NEBIUS_BASE_URL must be a valid HTTPS URL") from exc

        valid_host = re.fullmatch(
            r"api\.tokenfactory(?:\.[a-z0-9-]+)?\.nebius\.com", hostname
        )
        if parsed.scheme != "https" or not valid_host:
            raise ValueError("NEBIUS_BASE_URL must use an HTTPS Nebius Token Factory API host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("NEBIUS_BASE_URL cannot contain credentials, a query, or a fragment")
        if port not in (None, 443):
            raise ValueError("NEBIUS_BASE_URL must use the standard HTTPS port")
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard logging level")
        return level


@lru_cache
def get_settings() -> Settings:
    return Settings()

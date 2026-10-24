"""Validated settings loaded from environment variables and optional .env."""

from functools import lru_cache
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevRelay AI API"
    environment: str = "development"
    log_level: str = "INFO"
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_model: str = "nvidia/Nemotron-3_5-Lightning"
    nebius_api_key: SecretStr | None = None
    nebius_live_inference_enabled: bool = False
    nebius_total_inference_quota: int = Field(default=0, ge=0, le=100_000)
    nebius_quota_db_path: Path = Path(".devrelay-state/nebius-quota.sqlite3")
    nebius_planning_disable_thinking: bool = False
    nebius_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    nebius_max_output_tokens: int = Field(default=1024, ge=1, le=4096)
    nebius_max_prompt_tokens: int = Field(default=6_000, ge=256, le=32_000)
    nebius_max_in_flight_requests: int = Field(default=1, ge=1, le=4)
    inference_provider: str = "mock"
    enable_local_reviews: bool = False
    enable_isolated_runtime_validation: bool = False
    authorized_repositories: dict[str, Path] = Field(default_factory=dict)
    repository_max_files: int = Field(default=2_000, gt=0, le=20_000)
    repository_max_file_size_bytes: int = Field(default=1_000_000, gt=0, le=20_000_000)
    repository_max_total_bytes: int = Field(default=20_000_000, gt=0, le=200_000_000)
    repository_max_depth: int = Field(default=20, gt=0, le=100)
    repository_max_processing_seconds: float = Field(default=10.0, gt=0, le=120)
    task_planning_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    task_context_max_chars: int = Field(default=16_000, gt=0, le=100_000)

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

    @field_validator("inference_provider")
    @classmethod
    def validate_inference_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in {"nebius", "mock"}:
            raise ValueError("INFERENCE_PROVIDER must be 'nebius' or 'mock'")
        return provider

    @field_validator("authorized_repositories")
    @classmethod
    def validate_authorized_repositories(cls, value: dict[str, Path]) -> dict[str, Path]:
        for repository_id, path in value.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", repository_id):
                raise ValueError("Authorized repository IDs must be simple identifiers")
            if not path.is_absolute():
                raise ValueError("Authorized repository roots must be absolute paths")
        return value

    @model_validator(mode="after")
    def restrict_local_reviews_to_development(self) -> "Settings":
        if self.enable_local_reviews and self.environment.strip().lower() != "development":
            raise ValueError("ENABLE_LOCAL_REVIEWS can only be enabled in development.")
        if self.enable_isolated_runtime_validation and self.environment.strip().lower() != "development":
            raise ValueError("ENABLE_ISOLATED_RUNTIME_VALIDATION can only be enabled in development.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

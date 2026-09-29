from pathlib import Path
import os
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = None if os.getenv("GREENCITY_DISABLE_DOTENV") == "1" else BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8",
        extra="ignore", hide_input_in_errors=True,
    )

    database_url: SecretStr
    app_env: Literal["development", "test", "production"] = "development"
    database_ssl_root_cert: Path | None = None
    private_storage_path: Path = BACKEND_ROOT / ".private-evidence"
    attachment_link_ttl_seconds: int = Field(default=60, ge=1, le=300)
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://localhost:3000",
    ])
    # Required by the HTTP app; migration/probe commands need only DB config.
    secret_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    # Provider use is held off until quota, budget, and retention policy is approved.
    assistant_enabled: bool = False
    # Read only by the demo-data seed command. It stays optional so ordinary
    # application startup, migrations and runtime checks never need demo secrets.
    demo_seed_enabled: bool = False
    demo_seed_credentials_json: SecretStr | None = None
    login_throttle_failure_threshold: int = Field(default=5, ge=2, le=20)
    login_throttle_base_backoff_seconds: int = Field(default=60, ge=1, le=300)
    login_throttle_max_backoff_seconds: int = Field(default=1800, ge=60, le=3600)
    login_throttle_reset_seconds: int = Field(default=86400, ge=600, le=604800)
    login_throttle_retention_days: int = Field(default=30, ge=1, le=365)
    login_throttle_max_identities: int = Field(default=10000, ge=100, le=1000000)

    def auth_secret(self) -> str:
        value = self.secret_key.get_secret_value() if self.secret_key else ""
        normalized = value.strip().lower()
        if (len(value.strip().encode("utf-8")) < 32
                or normalized.startswith((
                    "your_", "greencity-default-development-", "change_me", "replace_",
                ))):
            raise ValueError("SECRET_KEY must be explicitly configured with at least 32 bytes; use a randomly generated key")
        return value

    @model_validator(mode="after")
    def validate_settings(self):
        self.sqlalchemy_url()
        if self.login_throttle_max_backoff_seconds < self.login_throttle_base_backoff_seconds:
            raise ValueError("Login throttle maximum backoff must be at least its base backoff")
        if self.login_throttle_reset_seconds < self.login_throttle_max_backoff_seconds:
            raise ValueError("Login throttle reset window must not be shorter than maximum backoff")
        if "*" in self.cors_origins:
            raise ValueError("CORS requires explicit origins")
        if self.app_env == "production" and any(
            not origin.startswith("https://") for origin in self.cors_origins
        ):
            raise ValueError("Production CORS origins must use HTTPS")
        return self

    def sqlalchemy_url(self) -> URL:
        raw = self.database_url.get_secret_value()
        if raw.startswith("postgres://"):
            raw = "postgresql://" + raw[len("postgres://"):]
        try:
            url = make_url(raw)
        except Exception:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URI") from None
        if url.drivername not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("Only PostgreSQL with psycopg is supported")
        if not url.host or not url.database or not url.username:
            raise ValueError("DATABASE_URL requires host, database and user")
        query = dict(url.query)
        # Do not accept arbitrary libpq options (e.g. service files/search_path).
        if set(query) - {"sslmode", "sslrootcert", "connect_timeout"}:
            raise ValueError("Unsupported DATABASE_URL connection option")
        mode = query.get("sslmode", "require")
        is_local_dev = self.app_env == "development" and url.host in {"localhost", "127.0.0.1", "::1"}
        allowed_modes = {"require", "verify-ca", "verify-full"}
        if is_local_dev:
            allowed_modes.add("disable")
        if mode not in allowed_modes:
            raise ValueError("PostgreSQL TLS is mandatory")
        if self.database_ssl_root_cert:
            mode = "verify-full"
            query["sslrootcert"] = str(self.database_ssl_root_cert)
        if self.app_env == "production" and mode != "verify-full":
            raise ValueError("Production PostgreSQL requires sslmode=verify-full")
        query["sslmode"] = mode
        query["connect_timeout"] = "10"
        return url.set(drivername="postgresql+psycopg", query=query)

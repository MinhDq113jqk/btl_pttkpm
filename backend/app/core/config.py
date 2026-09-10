from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8",
        extra="ignore", hide_input_in_errors=True,
    )

    database_url: SecretStr
    app_env: Literal["development", "test", "production"] = "development"
    database_ssl_root_cert: Path | None = None
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://localhost:3000",
    ])
    # Required by the HTTP app; migration/probe commands need only DB config.
    secret_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    def auth_secret(self) -> str:
        value = self.secret_key.get_secret_value() if self.secret_key else ""
        if (len(value.strip().encode("utf-8")) < 32
                or value.startswith(("your_", "greencity-default-development-"))):
            raise ValueError("SECRET_KEY must be explicitly configured with at least 32 bytes; use a randomly generated key")
        return value

    @model_validator(mode="after")
    def validate_settings(self):
        self.sqlalchemy_url()
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
        if mode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("PostgreSQL TLS is mandatory")
        if self.database_ssl_root_cert:
            mode = "verify-full"
            query["sslrootcert"] = str(self.database_ssl_root_cert)
        if self.app_env == "production" and mode != "verify-full":
            raise ValueError("Production PostgreSQL requires sslmode=verify-full")
        query["sslmode"] = mode
        query["connect_timeout"] = "10"
        return url.set(drivername="postgresql+psycopg", query=query)

"""Validate effective pilot runtime configuration without exposing secrets."""

import json
import sys

from app.core.config import Settings


EXPECTED_SCHEMA_REVISION = "0015"


def validate_runtime(settings: Settings | None = None) -> dict[str, object]:
    """Validate settings and return only non-sensitive configuration metadata."""

    effective = settings or Settings()
    effective.auth_secret()
    raw_database_url = effective.database_url.get_secret_value().lower()
    if any(marker in raw_database_url for marker in (
        "change_me", "replace_me", "your_postgresql_connection_string",
    )):
        raise ValueError("DATABASE_URL still contains a template placeholder")
    database_url = effective.sqlalchemy_url()
    return {
        "status": "valid",
        "app_env": effective.app_env,
        "database": "configured",
        "database_sslmode": dict(database_url.query).get("sslmode"),
        "cors_origins_count": len(effective.cors_origins),
        "schema_revision_required": EXPECTED_SCHEMA_REVISION,
    }


def main() -> int:
    try:
        summary = validate_runtime()
    except Exception:
        # Do not print the Pydantic/driver exception: it can contain a URI,
        # username, host, or a provider-specific connection detail.
        print(
            "Runtime configuration invalid; configure DATABASE_URL, SECRET_KEY, "
            "APP_ENV and CORS_ORIGINS in backend/.env or the process environment."
        )
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

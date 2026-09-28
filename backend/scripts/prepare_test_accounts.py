"""Rotate disposable demo accounts through the authenticated API for regression tests."""
import json
import logging
import os

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app


def main() -> int:
    settings = Settings(_env_file=None)
    old_credentials = json.loads(settings.demo_seed_credentials_json.get_secret_value())
    new_credentials = json.loads(os.environ["ROTATED_DEMO_CREDENTIALS_JSON"])
    if set(old_credentials) != set(new_credentials) or len(set(new_credentials.values())) != len(new_credentials):
        raise RuntimeError("Disposable account rotation map is invalid")

    database = Database(settings)
    try:
        app = create_app(settings, database)
        logging.getLogger("greencity").disabled = True
        with TestClient(app) as client:
            for index, (username, old_password) in enumerate(old_credentials.items(), start=1):
                print(f"Forced password rotation {index}/10: login", flush=True)
                login = client.post("/api/v1/auth/login", json={
                    "username": username, "password": old_password,
                })
                if login.status_code != 200 or login.json().get("user", {}).get("must_change_password") is not True:
                    raise RuntimeError(f"Disposable demo login or forced-state check failed (status {login.status_code})")
                token = login.json().get("access_token")
                print(f"Forced password rotation {index}/10: change", flush=True)
                changed = client.post(
                    "/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"current_password": old_password, "new_password": new_credentials[username]},
                )
                if changed.status_code != 204:
                    raise RuntimeError(f"Disposable demo password-change route failed (status {changed.status_code})")
                print(f"Forced password rotation {index}/10: PASS", flush=True)
        print("Disposable demo-account password rotation: PASS")
        return 0
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Fail-closed role checks before resource lookup; SQL behavior tested on PostgreSQL."""
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.policy import UserContext, get_current_user_context
from app.main import create_app


@pytest.mark.parametrize("role,status", [("cleaning", 403), ("auditor", 403),
                                       ("unknown", 403), ("technician", 404)])
def test_role_without_resource_authority_does_not_load_unit(role, status):
    tenant, site, unit_id = uuid4(), uuid4(), uuid4()
    database = MagicMock()
    unit = SimpleNamespace(id=unit_id, unit_number="FIXTURE", floor=1, area_m2=50,
                           status="occupied", version=1, relationships=[],
                           building=SimpleNamespace(id=uuid4(), code="B", name="B",
                                                    site=SimpleNamespace(id=site, code="S", name="S")))
    database.get_session.return_value.__enter__.return_value.execute.return_value.scalar_one_or_none.return_value = unit
    config = Settings(_env_file=None, database_url="postgresql://fixture@db.invalid/fixture",
                      secret_key=secrets.token_urlsafe(32))
    app = create_app(config, database)
    context = UserContext(uuid4(), tenant, "fixture", "Fixture", [role], site, [site])
    app.dependency_overrides[get_current_user_context] = lambda: context
    with TestClient(app) as client:
        response = client.get(f"/api/v1/units/{unit_id}/360")
    assert response.status_code == status
    database.get_session.return_value.__enter__.return_value.execute.assert_not_called()

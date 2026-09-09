"""Explicit opt-in; use deployed schema, rollback all inserted test records."""
import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models import Tenant

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1", reason="Set RUN_DB_INTEGRATION=1 explicitly",
)]


@pytest.fixture
def db():
    database = Database(Settings())
    yield database
    database.close()


def test_postgres_tls_schema_and_migration(db):
    with db.engine.connect() as conn:
        assert conn.execute(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")).scalar_one() is True
        assert conn.execute(text("SHOW timezone")).scalar_one() == "UTC"
        assert "tenants" in inspect(conn).get_table_names(schema="greencity")
        assert conn.execute(text("SELECT version_num FROM greencity.alembic_version")).scalar_one()
        columns = {column["name"]: column for column in inspect(conn).get_columns("tenants", schema="greencity")}
        assert columns["created_at"]["type"].timezone
        assert columns["updated_at"]["type"].timezone


def test_postgres_model_roundtrip_rolled_back(db):
    with db.engine.connect() as conn:
        transaction = conn.begin()
        try:
            with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
                tenant = Tenant(name="Phase 1 transient integration fixture")
                session.add(tenant)
                session.flush()
                assert isinstance(tenant.id, UUID)
                assert tenant.created_at.utcoffset().total_seconds() == 0
                assert tenant.updated_at is not None
        finally:
            transaction.rollback()


def test_health_against_real_postgres(db):
    with TestClient(create_app(Settings(), db)) as http:
        response = http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}

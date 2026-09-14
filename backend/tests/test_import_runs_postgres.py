"""PostgreSQL acceptance evidence for durable, scoped Unit CSV ImportRun."""

import csv
import io
import os
import secrets
import shutil
from threading import Barrier, Thread
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Database
from app.core.security import create_token, hash_password
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.import_run import ImportRun
from app.models.platform import AuditEvent, DomainEvent, IdempotencyRecord
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.services.import_runs import (
    APPLY_OPERATION,
    PREVIEW_OPERATION,
    RESOURCE_TYPE,
    UPLOAD_OPERATION,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
        reason="Run scripts.test_isolated; ImportRun tests require disposable PostgreSQL",
    ),
]


@pytest.fixture(scope="module")
def import_run_case():
    settings = Settings()
    assert settings.app_env == "test"
    assert settings.sqlalchemy_url().host == "127.0.0.1"
    storage_root = (settings.private_storage_path / f"import-runs-{uuid4().hex}").resolve()
    settings.private_storage_path = storage_root
    database = Database(settings)
    connection = database.engine.connect()
    transaction = connection.begin()
    database.sessions = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    password = secrets.token_urlsafe(24)
    with database.get_session() as session:
        tenant = Tenant(name=f"ImportRun tenant {uuid4()}")
        foreign_tenant = Tenant(name=f"ImportRun foreign tenant {uuid4()}")
        session.add_all((tenant, foreign_tenant))
        session.flush()
        west = Site(
            tenant_id=tenant.id,
            code=f"AA-IMPORT-WEST-{uuid4().hex[:6]}",
            name="Import West",
            address="Synthetic",
        )
        east = Site(
            tenant_id=tenant.id,
            code=f"ZZ-IMPORT-EAST-{uuid4().hex[:6]}",
            name="Import East",
            address="Synthetic",
        )
        foreign_site = Site(
            tenant_id=foreign_tenant.id,
            code=f"IMPORT-FOREIGN-{uuid4().hex[:6]}",
            name="Import Foreign",
            address="Synthetic",
        )
        session.add_all((west, east, foreign_site))
        session.flush()
        buildings = {
            "B1": Building(site_id=west.id, code="B1", name="Permitted", floors_count=80),
            "B2": Building(site_id=west.id, code="B2", name="Other west", floors_count=80),
            "E1": Building(site_id=east.id, code="E1", name="East", floors_count=80),
            "F1": Building(site_id=foreign_site.id, code="F1", name="Foreign", floors_count=80),
        }
        session.add_all(buildings.values())
        session.flush()
        session.add(Unit(
            building_id=buildings["B1"].id,
            unit_number="EXIST-0001",
            floor=1,
            area_m2=50,
            status="occupied",
        ))
        hashed_password = hash_password(password)
        accounts = {
            "admin": Account(
                tenant_id=tenant.id,
                username=f"import_run_admin_{uuid4().hex}",
                full_name="ImportRun admin",
                hashed_password=hashed_password,
            ),
            "cskh": Account(
                tenant_id=tenant.id,
                username=f"import_run_cskh_{uuid4().hex}",
                full_name="ImportRun CSKH",
                hashed_password=hashed_password,
            ),
            "technician": Account(
                tenant_id=tenant.id,
                username=f"import_run_technician_{uuid4().hex}",
                full_name="ImportRun technician",
                hashed_password=hashed_password,
            ),
            "foreign_admin": Account(
                tenant_id=foreign_tenant.id,
                username=f"import_run_foreign_{uuid4().hex}",
                full_name="ImportRun foreign admin",
                hashed_password=hashed_password,
            ),
        }
        session.add_all(accounts.values())
        session.flush()
        session.add_all((
            AccountRole(account_id=accounts["admin"].id, role="admin", site_id=None),
            AccountRole(
                account_id=accounts["cskh"].id,
                role="cskh",
                site_id=west.id,
                building_id=buildings["B1"].id,
            ),
            AccountRole(
                account_id=accounts["technician"].id,
                role="technician",
                site_id=west.id,
            ),
            AccountRole(account_id=accounts["foreign_admin"].id, role="admin", site_id=None),
        ))
        session.commit()

    app = create_app(settings, database)
    with TestClient(app) as client:
        auth = {}
        for label, account in accounts.items():
            response = client.post("/api/v1/auth/login", json={
                "username": account.username,
                "password": password,
            })
            assert response.status_code == 200
            auth[label] = {"Authorization": "Bearer " + response.json()["access_token"]}
        yield {
            "client": client,
            "database": database,
            "settings": settings,
            "tenant": tenant,
            "sites": {"west": west, "east": east, "foreign": foreign_site},
            "buildings": buildings,
            "accounts": accounts,
            "auth": auth,
            "storage_root": storage_root,
        }
    transaction.rollback()
    connection.close()
    database.close()
    shutil.rmtree(storage_root, ignore_errors=True)


def csv_bytes(rows, *, headers=("unit_number", "floor", "area_m2", "status")):
    target = io.StringIO(newline="")
    writer = csv.writer(target)
    writer.writerow(headers)
    writer.writerows(rows)
    return target.getvalue().encode("utf-8")


def csv_headers(case, actor, key, *, filename="units.csv", mime="text/csv"):
    return case["auth"][actor] | {
        "Idempotency-Key": key,
        "Content-Type": mime,
        "X-File-Name": filename,
    }


def upload(case, actor, key, content, *, building="B1", mode="PARTIAL", **headers):
    request_headers = csv_headers(case, actor, key) | headers
    return case["client"].post(
        "/api/v1/import-runs",
        params={"building_code": building, "mode": mode},
        headers=request_headers,
        content=content,
    )


def preview(case, actor, run_id, key, expected_version, mapping=None):
    return case["client"].post(
        f"/api/v1/import-runs/{run_id}/preview",
        headers=case["auth"][actor] | {"Idempotency-Key": key},
        json={
            "expected_version": expected_version,
            "mapping": mapping or {
                "unit_number": "unit_number",
                "floor": "floor",
                "area_m2": "area_m2",
                "status": "status",
            },
        },
    )


def apply(case, actor, run_id, key, expected_version):
    return case["client"].post(
        f"/api/v1/import-runs/{run_id}/apply",
        headers=case["auth"][actor] | {"Idempotency-Key": key},
        json={"expected_version": expected_version},
    )


def count_units(case, building_code):
    with case["database"].get_session() as session:
        return session.scalar(select(func.count(Unit.id)).where(
            Unit.building_id == case["buildings"][building_code].id,
        ))


def run_for_key(case, key, operation=UPLOAD_OPERATION):
    with case["database"].get_session() as session:
        receipt = session.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == key,
        ))
        assert receipt is not None
        run = session.get(ImportRun, receipt.resource_id)
        assert run is not None
        return run


def test_csv_import_run_1000_rows_preview_apply_and_replay(import_run_case):
    case = import_run_case
    rows = [
        (f"B1-BULK-{number:04d}", "1", "55.50", "occupied")
        for number in range(1, 901)
    ]
    rows.extend(
        (f"B1-BULK-{number:04d} ", "1", "55.50", "occupied")
        for number in range(901, 951)
    )
    rows.extend(
        (f"B1-BULK-{number:04d}", "1", "55.50", "occupied")
        for number in range(1, 26)
    )
    rows.extend(
        (f"B1-BULK-INVALID-{number:02d}", "0", "55.50", "occupied")
        for number in range(1, 26)
    )
    source = csv_bytes(rows)
    before = count_units(case, "B1")

    uploaded = upload(case, "admin", "run-1000-upload-001", source)
    assert uploaded.status_code == 201, uploaded.text
    uploaded_body = uploaded.json()
    assert uploaded_body["status"] == "UPLOADED"
    assert uploaded_body["version"] == 1
    assert uploaded_body["source_sha256"]
    assert upload(case, "admin", "run-1000-upload-001", source).json() == uploaded_body

    run_id = uploaded_body["id"]
    previewed = preview(case, "admin", run_id, "run-1000-preview-001", 1)
    assert previewed.status_code == 200, previewed.text
    previewed_body = previewed.json()
    assert (previewed_body["status"], previewed_body["version"], previewed_body["total_rows"],
            previewed_body["valid_rows"], previewed_body["warning_rows"],
            previewed_body["error_rows"], previewed_body["skipped_rows"]) == (
                "PREVIEWED", 2, 1000, 950, 75, 25, 25,
            )
    replayed_preview = preview(case, "admin", run_id, "run-1000-preview-001", 1)
    assert replayed_preview.status_code == 200
    assert replayed_preview.json() == previewed_body

    page = case["client"].get(
        f"/api/v1/import-runs/{run_id}/rows?page=3&page_size=200",
        headers=case["auth"]["admin"],
    )
    assert page.status_code == 200
    assert page.json()["total"] == 1000
    assert [row["row_number"] for row in page.json()["items"]] == list(range(401, 601))
    assert {row["status"] for row in page.json()["items"]} == {"VALIDATED"}

    applied = apply(case, "admin", run_id, "run-1000-apply-001", 2)
    assert applied.status_code == 200, applied.text
    applied_body = applied.json()
    assert (applied_body["status"], applied_body["version"], applied_body["applied_rows"],
            applied_body["error_rows"], applied_body["skipped_rows"]) == ("APPLIED", 3, 950, 25, 25)
    assert count_units(case, "B1") == before + 950
    original_upload_replay = upload(case, "admin", "run-1000-upload-001", source)
    assert original_upload_replay.status_code == 201
    assert original_upload_replay.json() == uploaded_body
    original_preview_replay = preview(case, "admin", run_id, "run-1000-preview-001", 1)
    assert original_preview_replay.status_code == 200
    assert original_preview_replay.json() == previewed_body
    replayed_apply = apply(case, "admin", run_id, "run-1000-apply-001", 2)
    assert replayed_apply.status_code == 200
    assert replayed_apply.json() == applied_body
    assert count_units(case, "B1") == before + 950

    with case["database"].get_session() as session:
        assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
            IdempotencyRecord.operation.in_([UPLOAD_OPERATION, PREVIEW_OPERATION, APPLY_OPERATION]),
            IdempotencyRecord.resource_id == run_id,
        )) == 3
        audit_actions = set(session.scalars(select(AuditEvent.event_type).where(
            AuditEvent.resource_type == RESOURCE_TYPE,
            AuditEvent.resource_id == run_id,
        )))
        assert {"ImportRunUploaded", "ImportRunPreviewed", "ImportRunApplied"}.issubset(audit_actions)
        completed = session.scalar(select(DomainEvent).where(
            DomainEvent.resource_type == RESOURCE_TYPE,
            DomainEvent.resource_id == run_id,
            DomainEvent.event_type == "ImportRunCompleted",
        ))
        assert completed is not None
        assert completed.payload["applied_rows"] == 950


def test_import_run_scope_and_client_scope_spoofing_are_denied(import_run_case):
    case = import_run_case
    source = csv_bytes([("SCOPE-0001", "1", "50", "occupied")])
    denied_building = upload(case, "cskh", "run-scope-cskh-b2", source, building="B2")
    assert denied_building.status_code == 404
    assert denied_building.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    denied_spoof = case["client"].post(
        "/api/v1/import-runs",
        params={
            "building_code": "B2",
            "mode": "PARTIAL",
            "tenant_id": str(uuid4()),
            "site_id": str(uuid4()),
            "building_id": str(case["buildings"]["B1"].id),
            "role": "admin",
        },
        headers=csv_headers(case, "cskh", "run-scope-spoof-b2") | {"X-Role": "admin"},
        content=source,
    )
    assert denied_spoof.status_code == 404
    assert denied_spoof.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    allowed = upload(case, "cskh", "run-scope-cskh-b1", source)
    assert allowed.status_code == 201
    run_id = allowed.json()["id"]
    technician = upload(case, "technician", "run-scope-tech-b1", source)
    assert technician.status_code == 403
    assert technician.json()["error"]["code"] == "ERR-FORBIDDEN"
    foreign_building = upload(case, "admin", "run-scope-foreign-b1", source, building="F1")
    assert foreign_building.status_code == 404
    assert foreign_building.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    cross_tenant_run = case["client"].get(
        f"/api/v1/import-runs/{run_id}", headers=case["auth"]["foreign_admin"],
    )
    assert cross_tenant_run.status_code == 404
    assert cross_tenant_run.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    east_before = count_units(case, "E1")
    wrong_active_site = upload(case, "admin", "run-scope-east-denied", source, building="E1")
    assert wrong_active_site.status_code == 404
    switch = case["client"].post(
        "/api/v1/auth/switch-site",
        headers=case["auth"]["admin"],
        json={"site_id": str(case["sites"]["east"].id)},
    )
    assert switch.status_code == 200
    east_auth = {"Authorization": "Bearer " + switch.json()["access_token"]}
    allowed_east = case["client"].post(
        "/api/v1/import-runs",
        params={"building_code": "E1", "mode": "PARTIAL"},
        headers=east_auth | {
            "Idempotency-Key": "run-scope-east-allowed",
            "Content-Type": "text/csv",
            "X-File-Name": "east.csv",
        },
        content=source,
    )
    assert allowed_east.status_code == 201
    assert count_units(case, "E1") == east_before


def test_csv_validation_quarantines_bad_files_and_rejects_bad_mapping(import_run_case):
    case = import_run_case
    valid = csv_bytes([("VALID-0001", "1", "50", "occupied")])
    bad_filename = upload(
        case,
        "admin",
        "run-quarantine-filename",
        valid,
        **{"X-File-Name": "..\\unsafe.csv"},
    )
    assert bad_filename.status_code == 422
    assert bad_filename.json()["error"]["code"] == "ERR-FILE-QUARANTINED"
    filename_run = run_for_key(case, "run-quarantine-filename")
    assert filename_run.source_is_quarantined
    assert filename_run.source_quarantine_reason == "unsafe-file-name"
    assert filename_run.source_storage_key.startswith("quarantine/imports/")
    assert (case["storage_root"] / filename_run.source_storage_key).is_file()

    bad_mime = upload(
        case,
        "admin",
        "run-quarantine-mime-001",
        valid,
        **{"Content-Type": "application/pdf"},
    )
    assert bad_mime.status_code == 422
    mime_run = run_for_key(case, "run-quarantine-mime-001")
    assert mime_run.source_quarantine_reason == "mime-not-allowed"

    malformed = upload(case, "admin", "run-quarantine-utf8-1", b"unit_number\n\xff")
    assert malformed.status_code == 422
    malformed_run = run_for_key(case, "run-quarantine-utf8-1")
    assert malformed_run.source_quarantine_reason == "content-not-csv"

    duplicated_headers = upload(
        case,
        "admin",
        "run-quarantine-header",
        csv_bytes([("DUP-0001", "1", "50", "occupied")], headers=("unit_number", "unit_number", "area_m2", "status")),
    )
    assert duplicated_headers.status_code == 422
    assert run_for_key(case, "run-quarantine-header").source_quarantine_reason == "content-not-csv"

    valid_upload = upload(case, "admin", "run-bad-mapping-0001", valid)
    assert valid_upload.status_code == 201
    bad_mapping = preview(
        case,
        "admin",
        valid_upload.json()["id"],
        "run-bad-mapping-0001",
        1,
        mapping={
            "unit_number": "absent",
            "floor": "floor",
            "area_m2": "area_m2",
            "status": "status",
        },
    )
    assert bad_mapping.status_code == 422
    assert bad_mapping.json()["error"]["code"] == "ERR-VALIDATION"
    assert run_for_key(case, "run-bad-mapping-0001").status == "UPLOADED"

    with case["database"].get_session() as session:
        events = set(session.scalars(select(DomainEvent.event_type).where(
            DomainEvent.resource_type == RESOURCE_TYPE,
            DomainEvent.event_type == "AttachmentQuarantined",
        )))
        assert events == {"AttachmentQuarantined"}


def test_partial_apply_keeps_valid_rows_when_other_rows_fail(import_run_case):
    case = import_run_case
    before = count_units(case, "B1")
    source = csv_bytes([
        ("PARTIAL-0001", "1", "50", "occupied"),
        ("NOT A VALID UNIT", "1", "50", "occupied"),
    ])
    uploaded = upload(case, "admin", "run-partial-upload-01", source)
    assert uploaded.status_code == 201
    run_id = uploaded.json()["id"]
    previewed = preview(case, "admin", run_id, "run-partial-preview-01", 1)
    assert previewed.status_code == 200
    assert (previewed.json()["valid_rows"], previewed.json()["error_rows"]) == (1, 1)
    applied = apply(case, "admin", run_id, "run-partial-apply-001", 2)
    assert applied.status_code == 200
    assert applied.json()["status"] == "APPLIED"
    assert (applied.json()["applied_rows"], applied.json()["error_rows"]) == (1, 1)
    assert count_units(case, "B1") == before + 1


def test_tampered_private_source_fails_closed_without_creating_a_receipt(import_run_case):
    case = import_run_case
    source = csv_bytes([("TAMPER-0001", "1", "50", "occupied")])
    uploaded = upload(case, "admin", "run-tamper-upload-01", source)
    assert uploaded.status_code == 201
    run = run_for_key(case, "run-tamper-upload-01")
    (case["storage_root"] / run.source_storage_key).write_bytes(b"tampered")
    previewed = preview(case, "admin", run.id, "run-tamper-preview-1", 1)
    assert previewed.status_code == 409
    assert previewed.json()["error"]["code"] == "ERR-FILE-INTEGRITY"
    with case["database"].get_session() as session:
        assert session.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.operation == PREVIEW_OPERATION,
            IdempotencyRecord.idempotency_key == "run-tamper-preview-1",
        )) is None


def test_concurrent_upload_replay_and_apply_are_serialized(import_run_case):
    """Use separate engines so PostgreSQL, rather than a shared test session, arbitrates locks."""
    base_settings = import_run_case["settings"]
    storage_root = (base_settings.private_storage_path / f"concurrent-import-{uuid4().hex}").resolve()
    settings = base_settings.model_copy(update={"private_storage_path": storage_root})
    coordinator = Database(settings)
    try:
        with coordinator.get_session() as session:
            tenant = Tenant(name=f"Concurrent import tenant {uuid4()}")
            session.add(tenant)
            session.flush()
            site = Site(
                tenant_id=tenant.id,
                code=f"CONCURRENT-{uuid4().hex[:8]}",
                name="Concurrent import site",
                address="Synthetic",
            )
            session.add(site)
            session.flush()
            building = Building(
                site_id=site.id,
                code="C1",
                name="Concurrent import building",
                floors_count=10,
            )
            account = Account(
                tenant_id=tenant.id,
                username=f"concurrent_import_{uuid4().hex}",
                full_name="Concurrent import admin",
                hashed_password=hash_password(secrets.token_urlsafe(24)),
            )
            session.add_all((building, account))
            session.flush()
            session.add(AccountRole(account_id=account.id, role="admin", site_id=None))
            session.commit()
            site_id, building_id, account_id = site.id, building.id, account.id

        auth = {
            "Authorization": "Bearer " + create_token({
                "sub": str(account_id),
                "active_site_id": str(site_id),
                "purpose": "session",
            }, settings.auth_secret()),
        }
        source = csv_bytes([
            ("C1-CONCURRENT-0001", "1", "50", "occupied"),
            ("C1-CONCURRENT-0002", "1", "51", "occupied"),
        ])

        def parallel_post(specifications):
            gate = Barrier(len(specifications) + 1)
            results, failures = {}, []

            def worker(label, path, params, headers, content):
                worker_database = Database(settings)
                try:
                    with TestClient(create_app(settings, worker_database)) as client:
                        gate.wait(timeout=5)
                        response = client.post(path, params=params, headers=headers, content=content)
                        results[label] = (response.status_code, response.json())
                except BaseException as exc:  # Report worker failures in the assertion below.
                    failures.append(exc)
                finally:
                    worker_database.close()

            workers = [Thread(target=worker, args=specification, daemon=True)
                       for specification in specifications]
            for worker_thread in workers:
                worker_thread.start()
            gate.wait(timeout=5)
            for worker_thread in workers:
                worker_thread.join(timeout=10)
            assert not any(worker_thread.is_alive() for worker_thread in workers)
            assert not failures
            return results

        upload_headers = auth | {
            "Idempotency-Key": "concurrent-upload-key-001",
            "Content-Type": "text/csv",
            "X-File-Name": "concurrent.csv",
        }
        uploads = parallel_post([
            ("first", "/api/v1/import-runs", {"building_code": "C1", "mode": "PARTIAL"}, upload_headers, source),
            ("second", "/api/v1/import-runs", {"building_code": "C1", "mode": "PARTIAL"}, upload_headers, source),
        ])
        assert {result[0] for result in uploads.values()} == {201}
        assert uploads["first"][1] == uploads["second"][1]
        run_id = uploads["first"][1]["id"]
        run_uuid = UUID(run_id)

        with TestClient(create_app(settings, coordinator)) as client:
            previewed = client.post(
                f"/api/v1/import-runs/{run_id}/preview",
                headers=auth | {"Idempotency-Key": "concurrent-preview-key-1"},
                json={
                    "expected_version": 1,
                    "mapping": {
                        "unit_number": "unit_number",
                        "floor": "floor",
                        "area_m2": "area_m2",
                        "status": "status",
                    },
                },
            )
        assert previewed.status_code == 200, previewed.text
        assert previewed.json()["version"] == 2

        apply_results = parallel_post([
            ("first", f"/api/v1/import-runs/{run_id}/apply", None,
             auth | {"Idempotency-Key": "concurrent-apply-key-01", "Content-Type": "application/json"},
             b'{"expected_version":2}'),
            ("second", f"/api/v1/import-runs/{run_id}/apply", None,
             auth | {"Idempotency-Key": "concurrent-apply-key-02", "Content-Type": "application/json"},
             b'{"expected_version":2}'),
        ])
        assert sorted(result[0] for result in apply_results.values()) == [200, 409]
        rejected = next(body for status, body in apply_results.values() if status == 409)
        assert rejected["error"]["code"] == "ERR-STATE-TRANSITION"

        with coordinator.get_session() as session:
            assert session.scalar(select(func.count(Unit.id)).where(Unit.building_id == building_id)) == 2
            assert session.scalar(select(func.count(ImportRun.id)).where(ImportRun.id == run_uuid)) == 1
            assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.resource_id == run_uuid,
                IdempotencyRecord.operation == UPLOAD_OPERATION,
            )) == 1
            assert session.scalar(select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.resource_id == run_uuid,
                IdempotencyRecord.operation == APPLY_OPERATION,
            )) == 1
    finally:
        # This test only runs against the isolated runner's disposable cluster.
        # Audit events are intentionally append-only, so cascade cleanup here
        # would violate the database policy before the runner drops the cluster.
        coordinator.close()
        shutil.rmtree(storage_root, ignore_errors=True)


def test_all_or_nothing_error_file_link_is_private_and_expiring(import_run_case):
    case = import_run_case
    raw_private_value = "=PRIVATE-FORMULA"
    source = csv_bytes([
        ("ATOMIC-0001", "1", "50", "occupied"),
        (raw_private_value, "1", "50", "occupied"),
    ])
    before = count_units(case, "B1")
    uploaded = upload(case, "admin", "run-atomic-upload-01", source, mode="ALL_OR_NOTHING")
    assert uploaded.status_code == 201
    run_id = uploaded.json()["id"]
    previewed = preview(case, "admin", run_id, "run-atomic-preview-01", 1)
    assert previewed.status_code == 200
    assert previewed.json()["error_rows"] == 1
    applied = apply(case, "admin", run_id, "run-atomic-apply-001", 2)
    assert applied.status_code == 200
    assert applied.json()["status"] == "FAILED"
    assert applied.json()["applied_rows"] == 0
    assert applied.json()["error_file_available"] is True
    assert count_units(case, "B1") == before

    signed = case["client"].get(
        f"/api/v1/import-runs/{run_id}/error-file/signed-link",
        headers=case["auth"]["admin"],
    )
    assert signed.status_code == 200
    url = signed.json()["url"]
    signed_token = parse_qs(urlsplit(url).query)["signed_token"][0]
    signed_as_session = {"Authorization": "Bearer " + signed_token}
    assert case["client"].get("/api/v1/auth/me", headers=signed_as_session).status_code == 401
    signed_import = case["client"].post(
        "/api/v1/import-runs?building_code=B1&mode=PARTIAL",
        headers=signed_as_session | {
            "Idempotency-Key": "signed-token-import-denied",
            "Content-Type": "text/csv",
            "X-File-Name": "denied.csv",
        },
        content=source,
    )
    assert signed_import.status_code == 401
    other_actor = case["client"].get(url, headers=case["auth"]["cskh"])
    assert other_actor.status_code == 404
    assert other_actor.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"
    downloaded = case["client"].get(url, headers=case["auth"]["admin"])
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert raw_private_value not in downloaded.text
    assert "ERR-IMPORT-ROW" in downloaded.text

    run = run_for_key(case, "run-atomic-upload-01")
    (case["storage_root"] / run.error_storage_key).write_bytes(b"tampered-error-file")
    tampered_error = case["client"].get(url, headers=case["auth"]["admin"])
    assert tampered_error.status_code == 409
    assert tampered_error.json()["error"]["code"] == "ERR-FILE-INTEGRITY"

    east_session = case["client"].post(
        "/api/v1/auth/switch-site",
        headers=case["auth"]["admin"],
        json={"site_id": str(case["sites"]["east"].id)},
    )
    assert east_session.status_code == 200
    cross_site = case["client"].get(
        url,
        headers={"Authorization": "Bearer " + east_session.json()["access_token"]},
    )
    assert cross_site.status_code == 404
    assert cross_site.json()["error"]["code"] == "ERR-SCOPE-NOTFOUND"

    expired_token = create_token({
        "sub": str(case["accounts"]["admin"].id),
        "tenant_id": str(case["tenant"].id),
        "active_site_id": str(case["sites"]["west"].id),
        "building_id": str(run.building_id),
        "import_run_id": str(run.id),
        "purpose": "import-error-download",
    }, case["settings"].auth_secret(), expires_in_seconds=-1)
    expired = case["client"].get(
        f"/api/v1/import-runs/{run_id}/error-file?signed_token={expired_token}",
        headers=case["auth"]["admin"],
    )
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "ERR-LINK-EXPIRED"

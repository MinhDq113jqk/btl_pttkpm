"""FCS-14 security and parcel replay checks."""

from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.operations import (
    IncidentEscalation,
    IncidentEscalationAcknowledgement,
    PatrolLog,
    PatrolPoint,
    PatrolWindow,
    SecurityIncident,
    SecurityShift,
)
from app.models.parcel import Parcel
from app.models.platform import IdempotencyRecord
from app.models.submission_import import SubmissionExternalReference, SubmissionImportRun
from app.services.submission_data_import import canonical_payload_sha256
from app.services.submission_data_operational_replay import (
    OperationalReplayError,
    _deterministic_pin,
    replay_security_parcels,
)
from test_r2_integration import r2_case


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; FCS-14 requires disposable PostgreSQL",
)]


def test_fcs14_patrol_incident_and_parcel_replay_are_idempotent(monkeypatch, r2_case):
    secret = "fcs14-local-pin-secret-0123456789"
    monkeypatch.setenv("GREENCITY_SUBMISSION_PIN_SECRET", secret)
    case = r2_case
    with case["database"].get_session() as session:
        tenant = session.get(type(case["tenant"]), case["tenant"].id)
        tenant.code = tenant.code or f"R2-TENANT-{uuid4().hex[:8]}"
        site = session.get(type(case["sites"][0]), case["sites"][0].id)
        building = session.get(type(case["buildings"][0]), case["buildings"][0].id)
        point_owner_building = Building(
            site_id=site.id,
            code=f"FCS14-POINT-{uuid4().hex[:8]}",
            name="FCS14 point owner",
        )
        session.add(point_owner_building)
        session.flush()
        director = session.get(type(case["accounts"]["director"]), case["accounts"]["director"].id)
        guard = Account(
            tenant_id=tenant.id,
            username=f"fcs14_guard_{uuid4().hex[:8]}",
            full_name="FCS14 guard",
            hashed_password=director.hashed_password,
        )
        second_guard = Account(
            tenant_id=tenant.id,
            username=f"fcs14_guard2_{uuid4().hex[:8]}",
            full_name="FCS14 guard two",
            hashed_password=director.hashed_password,
        )
        session.add_all([guard, second_guard])
        session.flush()
        session.add_all(AccountRole(
            account_id=account.id,
            role="security",
            site_id=site.id,
            building_id=building.id,
        ) for account in (guard, second_guard))
        point = PatrolPoint(
            tenant_id=tenant.id,
            site_id=site.id,
            # The loader creates a site-scoped point once, then later source
            # rows may reuse it for a different building's own patrol window.
            building_id=point_owner_building.id,
            code="FCS14-P1",
            name="FCS14 point",
            created_by_id=director.id,
            updated_by_id=director.id,
        )
        session.add(point)
        session.flush()
        start = datetime.now(UTC) - timedelta(hours=3)
        shift = SecurityShift(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            assigned_to_id=guard.id,
            scheduled_start_at=start,
            scheduled_end_at=start + timedelta(hours=2),
            created_by_id=director.id,
            updated_by_id=director.id,
        )
        session.add(shift)
        session.flush()
        window = PatrolWindow(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            security_shift_id=shift.id,
            patrol_point_id=point.id,
            window_start_at=start,
            window_end_at=start + timedelta(minutes=30),
            created_by_id=guard.id,
            updated_by_id=guard.id,
        )
        incident = SecurityIncident(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            code="FCS14-INC-HIGH",
            incident_type="SECURITY",
            severity="HIGH",
            status="NEW",
            title="FCS14 incident",
            description="Synthetic high severity incident",
            occurred_at=start,
            reported_by_id=guard.id,
            created_by_id=guard.id,
            updated_by_id=guard.id,
        )
        session.add_all([window, incident])
        session.flush()
        pin = _deterministic_pin("FCS14-PARCEL")
        parcel = Parcel(
            tenant_id=tenant.id,
            site_id=site.id,
            building_id=building.id,
            unit_id=case["units"][0].id,
            parcel_code="FCS14-PARCEL",
            recipient_name_snapshot="Synthetic recipient",
            recipient_contact_snapshot="***1234",
            storage_location="LOCKER-01",
            pin_hash=hash_password(pin),
            status="RECEIVED",
            received_at=start,
            created_by_id=director.id,
            updated_by_id=director.id,
        )
        session.add(parcel)
        session.flush()
        run = SubmissionImportRun(
            manifest_sha256=uuid4().hex + uuid4().hex,
            schema_version="fcs-test",
            source_kind="synthetic",
            stage="replay",
            status="APPLYING",
            correlation_id=uuid4(),
            workbook_count=12,
            total_rows=3,
        )
        session.add(run)
        session.flush()
        session.add_all([
            SubmissionExternalReference(
                import_run_id=run.id,
                tenant_id=tenant.id,
                source="security",
                entity_type="SecurityShift",
                source_key=f"{site.code}:{building.code}:FCS14-SHIFT",
                target_id=shift.id,
                payload_sha256=canonical_payload_sha256({"shift_code": "FCS14-SHIFT"}),
            ),
            SubmissionExternalReference(
                import_run_id=run.id,
                tenant_id=tenant.id,
                source="parcel",
                entity_type="Parcel",
                source_key=f"{site.code}:FCS14-PARCEL",
                target_id=parcel.id,
                payload_sha256=canonical_payload_sha256({"parcel_code": "FCS14-PARCEL"}),
            ),
        ])
        session.flush()
        now = datetime.now(UTC)
        patrol_row = {
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "shift_code": "FCS14-SHIFT",
            "patrol_point_code": point.code,
            "window_start": window.window_start_at,
            "patrol_status": "COMPLETED",
            "event_type": "CHECK_IN",
        }
        incident_row = {
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "incident_code": incident.code,
            "status": "IN_PROGRESS",
        }
        parcel_row = {
            "tenant_code": tenant.code,
            "site_code": site.code,
            "building_code": building.code,
            "unit_number": case["units"][0].unit_number,
            "parcel_code": parcel.parcel_code,
            "status": "HANDED_OVER",
            "ready_at": now - timedelta(minutes=2),
            "handed_over_at": now - timedelta(minutes=1),
            "case_required": False,
        }
        first = replay_security_parcels(
            session,
            [patrol_row],
            [incident_row],
            [parcel_row],
            run,
            as_of_utc=now,
        )
        second = replay_security_parcels(
            session,
            [patrol_row],
            [incident_row],
            [parcel_row],
            run,
            as_of_utc=now,
        )
        assert first["patrol_logs_created"] == 1
        assert first["incident_escalations_created"] == 2
        assert first["incident_acknowledgements_created"] == 2
        assert second["patrol_rows"] == 1 and second["parcel_rows"] == 1
        assert session.scalar(select(func.count(PatrolLog.id)).where(PatrolLog.patrol_window_id == window.id)) == 1
        assert session.scalar(select(func.count(IncidentEscalation.id)).where(IncidentEscalation.security_incident_id == incident.id)) == 2
        escalation_ids = select(IncidentEscalation.id).where(IncidentEscalation.security_incident_id == incident.id)
        assert session.scalar(select(func.count(IncidentEscalationAcknowledgement.id)).where(
            IncidentEscalationAcknowledgement.incident_escalation_id.in_(escalation_ids),
        )) == 2
        assert session.get(PatrolWindow, window.id).status == "COMPLETED"
        assert session.get(SecurityIncident, incident.id).status == "IN_PROGRESS"
        stored_parcel = session.get(Parcel, parcel.id)
        assert stored_parcel.status == "HANDED_OVER"
        assert stored_parcel.pin_hash != secret and pin not in stored_parcel.pin_hash
        session.commit()


def test_fcs14_missed_patrol_requires_an_explicit_reason():
    with pytest.raises(OperationalReplayError) as error:
        from app.services.submission_data_operational_replay import _security_window_reason

        _security_window_reason({"patrol_status": "MISSED"})
    assert error.value.code == "PATROL_MISSED_REASON_REQUIRED"

"""Unit-level contract checks for the V1 parcel data foundation."""
from sqlalchemy import DateTime, Integer, String

from app.models import PARCEL_STATUS_TRANSITIONS, Parcel, ParcelStatusEnum


def constraint_names() -> set[str]:
    return {constraint.name for constraint in Parcel.__table__.constraints}


def test_parcel_status_enum_and_transition_contract_is_explicit():
    assert {status.value for status in ParcelStatusEnum} == {
        "RECEIVED", "READY_FOR_PICKUP", "HANDED_OVER", "RETURNED", "LOST", "DAMAGED",
    }
    assert PARCEL_STATUS_TRANSITIONS["RECEIVED"] == frozenset({
        "READY_FOR_PICKUP", "RETURNED", "LOST", "DAMAGED",
    })
    assert PARCEL_STATUS_TRANSITIONS["READY_FOR_PICKUP"] == frozenset({
        "HANDED_OVER", "RETURNED", "LOST", "DAMAGED",
    })
    for terminal in ("HANDED_OVER", "RETURNED", "LOST", "DAMAGED"):
        assert PARCEL_STATUS_TRANSITIONS[terminal] == frozenset()


def test_parcel_is_scoped_and_keeps_snapshots_and_pin_hash_only():
    columns = Parcel.__table__.c
    assert isinstance(columns.pin_hash.type, String)
    assert isinstance(columns.received_at.type, DateTime)
    assert isinstance(columns.pin_attempt_count.type, Integer)
    assert "pin" in columns.pin_hash.name
    assert "pin_value" not in columns
    assert "pin_plaintext" not in columns
    assert {"tenant_id", "site_id", "building_id", "unit_id"}.issubset(columns.keys())
    assert columns.recipient_name_snapshot.nullable is False
    assert columns.pin_hash.nullable is False


def test_parcel_constraints_cover_scope_uniqueness_and_state_semantics():
    names = constraint_names()
    assert "uq_parcels_site_code" in names
    assert {
        "fk_parcels_tenant_id_tenants",
        "fk_parcels_site_tenant",
        "fk_parcels_building_site",
        "fk_parcels_unit_building",
        "fk_parcels_recipient_person_tenant",
        "fk_parcels_created_by_tenant",
        "fk_parcels_updated_by_tenant",
        "fk_parcels_handed_over_by_tenant",
    }.issubset(names)
    assert {
        "ck_parcels_parcel_code_not_blank",
        "ck_parcels_recipient_name_snapshot_not_blank",
        "ck_parcels_pin_hash_min_length",
        "ck_parcels_pin_attempts_range",
        "ck_parcels_version_positive",
        "ck_parcels_status_allowed",
        "ck_parcels_exception_reason_required",
        "ck_parcels_handover_fields_semantics",
    }.issubset(names)
    assert {
        "ix_parcels_scope_status",
        "ix_parcels_unit_status_received",
        "ix_parcels_recipient_status",
    } == {index.name for index in Parcel.__table__.indexes}

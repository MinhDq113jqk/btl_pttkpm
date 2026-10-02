"""FCS-12 service-request replay checks."""

from datetime import datetime
import os
from uuid import uuid4

import pytest

from app.models.account import Account, AccountRole
from app.models.building import Building
from app.services.submission_data_replay import (
    SubmissionReplayError,
    _validate_submission_evidence,
    _unique_role_account,
    replay_service_requests,
)
from test_r2_integration import r2_case


def test_service_request_replay_requires_timezone_aware_as_of_before_database_work():
    try:
        replay_service_requests([], [], object(), as_of_utc=datetime(2026, 9, 27))
    except SubmissionReplayError as error:
        assert error.code == "REPLAY_AS_OF_NOT_TIMEZONE_AWARE"
    else:
        raise AssertionError("naive replay cutoff was accepted")


def test_submission_replay_accepts_only_verified_png_or_jpeg_evidence():
    png = b"\x89PNG\r\n\x1a\nsynthetic\x00\x00\x00\x00IEND\xaeB`\x82"
    jpeg = b"\xff\xd8\xffsynthetic\xff\xd9"

    assert _validate_submission_evidence(png) == ("image/png", "png")
    assert _validate_submission_evidence(jpeg) == ("image/jpeg", "jpg")


def test_submission_replay_rejects_non_image_evidence():
    try:
        _validate_submission_evidence(b"not-an-image")
    except SubmissionReplayError as error:
        assert error.code == "REPLAY_EVIDENCE_INVALID"
    else:
        raise AssertionError("non-image evidence was accepted")


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("GREENCITY_ISOLATED_SECURITY_TESTS") != "1",
    reason="Run scripts.test_isolated; triage scope resolution requires disposable PostgreSQL",
)
def test_triage_account_resolution_accepts_site_wide_cskh_but_rejects_two_accounts(r2_case):
    case = r2_case
    with case["database"].get_session() as session:
        site = case["sites"][0]
        building = Building(
            site_id=site.id,
            code=f"FCS12-SCOPE-{uuid4().hex[:8]}",
            name="FCS12 scope building",
        )
        session.add(building)
        session.flush()

        site_wide = session.get(Account, case["accounts"]["cskh_no_building"].id)
        selected = _unique_role_account(
            session,
            case["tenant"].id,
            site_id=site.id,
            building_id=building.id,
            role="cskh",
            error_code="TRIAGE_ACTOR_AMBIGUOUS",
        )
        assert selected.id == site_wide.id

        competing = Account(
            tenant_id=case["tenant"].id,
            username=f"fcs12_cskh_{uuid4().hex[:8]}",
            full_name="FCS12 competing CSKH",
            hashed_password=site_wide.hashed_password,
        )
        session.add(competing)
        session.flush()
        session.add(AccountRole(
            account_id=competing.id,
            role="cskh",
            site_id=site.id,
            building_id=building.id,
        ))
        session.flush()

        assert competing.id != site_wide.id
        with pytest.raises(SubmissionReplayError) as error:
            _unique_role_account(
                session,
                case["tenant"].id,
                site_id=site.id,
                building_id=building.id,
                role="cskh",
                error_code="TRIAGE_ACTOR_AMBIGUOUS",
            )
        assert error.value.code == "TRIAGE_ACTOR_AMBIGUOUS"

"""Pure FCS-12 replay checks that do not require a shared database."""

from datetime import datetime

from app.services.submission_data_replay import (
    SubmissionReplayError,
    _validate_submission_evidence,
    replay_service_requests,
)


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

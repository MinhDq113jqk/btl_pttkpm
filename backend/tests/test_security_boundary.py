"""Offline token/config and policy tests; PostgreSQL coverage is separate."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import uuid4
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import AppError
from app.core.policy import UserContext
from app.core.security import create_token, decode_token
from app.main import create_app


def signed_token(secret, payload, header=None):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    body = encode(header if header is not None else {"alg": "HS256", "typ": "JWT"}) + "." + encode(payload)
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode()


@pytest.mark.parametrize("secret", [None, "", "short", " " * 48, "your_jwt_secret"])
def test_app_rejects_missing_or_weak_signing_key(secret):
    config = Settings(_env_file=None, database_url="postgresql://fixture@db.invalid/fixture",
                      secret_key=secret)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app(config, Mock(spec=Database))


def test_strong_explicit_key_starts_app():
    config = Settings(_env_file=None, database_url="postgresql://fixture@db.invalid/fixture",
                      secret_key=secrets.token_urlsafe(32))
    with TestClient(create_app(config, Mock(spec=Database))) as client:
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize("claims", [
    {"sub": "not-a-uuid"}, {"sub": None}, {"sub": 123}, {"sub": []},
    {"exp": None}, {"exp": True}, {"exp": "99999999999"}, {"exp": float("nan")},
    {"active_site_id": []}, {"active_site_id": 123}, {"active_site_id": "invalid"},
])
def test_signed_malformed_claims_are_unauthorized(claims):
    key = secrets.token_urlsafe(32)
    payload = {"sub": str(uuid4()), "exp": int(time.time()) + 3600, **claims}
    with pytest.raises(AppError) as exc:
        decode_token(signed_token(key, payload), key)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("header", [{"alg": "none"}, {"alg": "HS512"}, [], None])
def test_invalid_header_rejected(header):
    key = secrets.token_urlsafe(32)
    payload = {"sub": str(uuid4()), "exp": int(time.time()) + 3600}
    # None is deliberately encoded as JSON null, not the helper's default header.
    raw_header = header if header is not None else "null"
    with pytest.raises(AppError):
        decode_token(signed_token(key, payload, raw_header), key)


def test_expiration_boundary_wrong_key_and_valid_control(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 2000000000)
    key = secrets.token_urlsafe(32)
    payload = {"sub": str(uuid4()), "active_site_id": str(uuid4())}
    token = create_token(payload, key, expires_in_seconds=60)
    assert decode_token(token, key)["sub"] == payload["sub"]
    with pytest.raises(AppError):
        decode_token(token, secrets.token_urlsafe(32))
    with pytest.raises(AppError):
        decode_token(create_token(payload, key, expires_in_seconds=0), key)


@pytest.mark.parametrize("roles", [["admin"], ["cskh"], []])
def test_none_site_membership_is_never_unrestricted(roles):
    context = UserContext(uuid4(), uuid4(), "fixture", "Fixture", roles, None, None)
    assert context.can_access_site(uuid4()) is False


def test_admin_still_requires_explicit_site_membership():
    site = uuid4()
    context = UserContext(uuid4(), uuid4(), "fixture", "Fixture", ["admin"], site, [site])
    assert context.can_access_site(site)
    assert not context.can_access_site(uuid4())

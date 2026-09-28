import secrets
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import assistant as assistant_api
from app.core.config import Settings
from app.core.database import Database
from app.core.policy import UnitGrant, UserContext, get_current_user_context
from app.main import create_app
from app.services.gemini_client import GeminiClientError


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://fixture@db.invalid/fixture",
        secret_key=secrets.token_urlsafe(32),
        assistant_enabled=True,
    )


@pytest.fixture
def assistant_case(monkeypatch):
    tenant_id, site_id, building_id = uuid4(), uuid4(), uuid4()
    database = MagicMock(spec=Database)
    session = MagicMock()
    database.get_session.return_value.__enter__.return_value = session
    session.scalars.return_value.all.return_value = [building_id]
    app = create_app(_settings(), database)
    context = UserContext(
        account_id=uuid4(),
        tenant_id=tenant_id,
        username="assistant-user",
        full_name="Assistant User",
        roles=["cskh"],
        active_site_id=site_id,
        allowed_site_ids=[site_id],
        unit_grants=(UnitGrant("cskh", building_id),),
        role_grants=(UnitGrant("cskh", building_id),),
    )
    app.dependency_overrides[get_current_user_context] = lambda: context
    calls = []

    class FakeGeminiClient:
        def generate_content(self, prompt, *, correlation_id):
            calls.append((prompt, correlation_id))
            return "Câu trả lời từ Gemini"

    monkeypatch.setattr(assistant_api, "GeminiClient", FakeGeminiClient)
    with TestClient(app) as client:
        yield client, context, building_id, calls


def test_assistant_chat_requires_login():
    app = create_app(_settings(), MagicMock(spec=Database))
    with TestClient(app) as client:
        response = client.post("/api/v1/assistant/chat", json={"message": "Xin chào"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ERR-UNAUTHORIZED"
    UUID(response.headers["x-correlation-id"])
    assert response.headers["cache-control"] == "private, no-store"


def test_assistant_disabled_does_not_call_provider(monkeypatch):
    settings = _settings().model_copy(update={"assistant_enabled": False})
    app = create_app(settings, MagicMock(spec=Database))
    context = UserContext(
        account_id=uuid4(), tenant_id=uuid4(), username="assistant-user",
        full_name="Assistant User", roles=["cskh"], active_site_id=uuid4(),
        allowed_site_ids=[], unit_grants=(), role_grants=(),
    )
    app.dependency_overrides[get_current_user_context] = lambda: context
    calls = []

    class ShouldNotCallGemini:
        def generate_content(self, prompt, *, correlation_id):
            calls.append(prompt)
            raise AssertionError("disabled assistant reached Gemini")

    monkeypatch.setattr(assistant_api, "GeminiClient", ShouldNotCallGemini)
    with TestClient(app) as client:
        response = client.post("/api/v1/assistant/chat", json={"message": "Xin chào"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ERR-ASSISTANT-DISABLED"
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == []


def test_assistant_enabled_defaults_to_false():
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql://fixture@db.invalid/fixture",
        secret_key=secrets.token_urlsafe(32),
    )
    assert settings.assistant_enabled is False


def test_assistant_chat_uses_server_derived_scope(assistant_case):
    client, context, building_id, calls = assistant_case
    correlation_id = str(uuid4())

    response = client.post(
        "/api/v1/assistant/chat",
        headers={"X-Correlation-ID": correlation_id},
        json={"message": "Tôi có thể xem công việc nào?"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"reply": "Câu trả lời từ Gemini"}
    assert response.headers["x-correlation-id"] == correlation_id
    assert response.headers["cache-control"] == "private, no-store"
    assert len(calls) == 1
    prompt, sent_correlation_id = calls[0]
    assert str(context.tenant_id) in prompt
    assert str(context.active_site_id) in prompt
    assert str(building_id) in prompt
    assert '"roles": ["cskh"]' in prompt
    assert sent_correlation_id == correlation_id


def test_assistant_chat_rejects_client_scope_fields(assistant_case):
    client, _, _, calls = assistant_case

    response = client.post(
        "/api/v1/assistant/chat",
        json={
            "message": "Xin chào",
            "tenant_id": str(uuid4()),
            "site_id": str(uuid4()),
            "building_id": str(uuid4()),
            "role": "admin",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ERR-VALIDATION"
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == []


def test_assistant_chat_hides_gemini_failure(assistant_case, monkeypatch):
    client, _, _, _ = assistant_case
    private_detail = "server-only-gemini-key"

    def fail(self, prompt, *, correlation_id):
        raise GeminiClientError(private_detail, correlation_id=correlation_id)

    monkeypatch.setattr(assistant_api.GeminiClient, "generate_content", fail)
    response = client.post("/api/v1/assistant/chat", json={"message": "Xin chào"})

    assert response.status_code == 503
    assert private_detail not in response.text
    assert response.json()["error"]["message"] == "Trợ lý tạm thời không khả dụng."
    assert response.headers["cache-control"] == "private, no-store"

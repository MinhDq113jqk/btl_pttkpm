import httpx
import pytest

from app.services import gemini_client
from app.services.gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfigurationError,
    GeminiResponseError,
    GeminiTimeoutError,
)


def _file_key(monkeypatch, value="file-key"):
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    monkeypatch.setattr(
        gemini_client,
        "dotenv_values",
        lambda path, **kwargs: {"GEMINI_API_KEY": value},
    )


def test_generate_content_reads_key_from_backend_env_and_sends_correlation(monkeypatch):
    _file_key(monkeypatch)
    seen = {}

    def fake_post(url, *, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "Xin chào"}]}}],
        })

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)
    correlation_id = "2f7e9b1a-9f47-4c17-9d8c-9b2c4e2c0f11"

    result = GeminiClient(model="gemini-test", timeout=7.5).generate_content(
        "Viết lời chào ngắn.", correlation_id=correlation_id,
    )

    assert result == "Xin chào"
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "file-key"
    assert seen["headers"]["X-Correlation-ID"] == correlation_id
    assert seen["json"] == {"contents": [{"parts": [{"text": "Viết lời chào ngắn."}]}]}
    assert seen["timeout"] == 7.5


def test_timeout_is_wrapped_with_correlation_id(monkeypatch):
    _file_key(monkeypatch)

    def fake_post(*args, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)

    with pytest.raises(GeminiTimeoutError) as exc_info:
        GeminiClient().generate_content("hello", correlation_id="not-a-uuid")

    assert exc_info.value.correlation_id
    assert str(exc_info.value) == "Gemini request timed out."
    assert "ReadTimeout" not in str(exc_info.value)


def test_http_error_is_wrapped_without_response_body(monkeypatch):
    _file_key(monkeypatch)
    monkeypatch.setattr(
        gemini_client.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(429, text="private upstream detail"),
    )

    with pytest.raises(GeminiAPIError) as exc_info:
        GeminiClient().generate_content("hello")

    assert exc_info.value.status_code == 429
    assert "private upstream detail" not in str(exc_info.value)
    assert exc_info.value.correlation_id


def test_invalid_response_is_reported(monkeypatch):
    _file_key(monkeypatch)
    monkeypatch.setattr(
        gemini_client.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(200, json={"candidates": []}),
    )

    with pytest.raises(GeminiResponseError) as exc_info:
        GeminiClient().generate_content("hello")

    assert exc_info.value.correlation_id


def test_missing_file_key_fails_before_http_call(monkeypatch):
    monkeypatch.setattr(gemini_client, "dotenv_values", lambda path, **kwargs: {})
    called = False

    def fake_post(*args, **kwargs):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    monkeypatch.setattr(gemini_client.httpx, "post", fake_post)

    with pytest.raises(GeminiConfigurationError) as exc_info:
        GeminiClient().generate_content("hello")

    assert called is False
    assert exc_info.value.correlation_id

"""Small, synchronous Gemini REST client for backend services."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from dotenv import dotenv_values


logger = logging.getLogger("greencity")

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


class GeminiClientError(RuntimeError):
    """Base error with a safe, caller-visible correlation ID."""

    code = "ERR-GEMINI"

    def __init__(
        self,
        message: str,
        *,
        correlation_id: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.correlation_id = correlation_id
        self.status_code = status_code


class GeminiRequestError(GeminiClientError):
    code = "ERR-GEMINI-REQUEST"


class GeminiConfigurationError(GeminiClientError):
    code = "ERR-GEMINI-CONFIG"


class GeminiTimeoutError(GeminiClientError):
    code = "ERR-GEMINI-TIMEOUT"


class GeminiTransportError(GeminiClientError):
    code = "ERR-GEMINI-TRANSPORT"


class GeminiAPIError(GeminiClientError):
    code = "ERR-GEMINI-API"


class GeminiResponseError(GeminiClientError):
    code = "ERR-GEMINI-RESPONSE"


def _normalize_correlation_id(value: str | UUID | None) -> str:
    try:
        return str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        return str(uuid4())


def _load_api_key(correlation_id: str) -> str:
    """Read the key from backend/.env without consulting process variables."""
    try:
        values = dotenv_values(ENV_FILE, interpolate=False)
    except OSError as exc:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY could not be read from backend/.env.",
            correlation_id=correlation_id,
        ) from exc

    raw_key = values.get("GEMINI_API_KEY")
    api_key = raw_key.strip() if isinstance(raw_key, str) else ""
    if not api_key:
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is missing from backend/.env.",
            correlation_id=correlation_id,
        )
    return api_key


def _response_text(payload: Any, correlation_id: str) -> str:
    if not isinstance(payload, dict):
        raise GeminiResponseError(
            "Gemini returned an invalid response.",
            correlation_id=correlation_id,
        )

    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiResponseError(
            "Gemini returned no candidate content.",
            correlation_id=correlation_id,
        )

    candidate = candidates[0]
    content = candidate.get("content") if isinstance(candidate, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    text = "".join(
        part.get("text", "")
        for part in parts or []
        if isinstance(part, dict) and isinstance(part.get("text", ""), str)
    )
    if not text.strip():
        raise GeminiResponseError(
            "Gemini returned no text content.",
            correlation_id=correlation_id,
        )
    return text


class GeminiClient:
    """Call Gemini's generateContent REST endpoint with safe error context."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self.model = model.strip()
        self.timeout = timeout

    def generate_content(
        self,
        prompt: str,
        *,
        correlation_id: str | UUID | None = None,
    ) -> str:
        """Generate text for prompt and return the first candidate's text."""
        request_correlation_id = _normalize_correlation_id(correlation_id)
        if not isinstance(prompt, str) or not prompt.strip():
            raise GeminiRequestError(
                "prompt must be a non-empty string.",
                correlation_id=request_correlation_id,
            )

        api_key = _load_api_key(request_correlation_id)
        url = (
            f"{GEMINI_API_BASE_URL}/models/"
            f"{quote(self.model, safe='')}:generateContent"
        )
        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": request_correlation_id,
            "x-goog-api-key": api_key,
        }
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            logger.warning("gemini_timeout correlation_id=%s", request_correlation_id)
            raise GeminiTimeoutError(
                "Gemini request timed out.",
                correlation_id=request_correlation_id,
            ) from None
        except httpx.RequestError:
            logger.warning("gemini_transport_error correlation_id=%s", request_correlation_id)
            raise GeminiTransportError(
                "Gemini request could not be completed.",
                correlation_id=request_correlation_id,
            ) from None

        if not 200 <= response.status_code < 300:
            logger.warning(
                "gemini_api_error status_code=%s correlation_id=%s",
                response.status_code,
                request_correlation_id,
            )
            raise GeminiAPIError(
                "Gemini returned an error response.",
                correlation_id=request_correlation_id,
                status_code=response.status_code,
            )

        try:
            response_payload = response.json()
        except ValueError as exc:
            logger.warning("gemini_invalid_json correlation_id=%s", request_correlation_id)
            raise GeminiResponseError(
                "Gemini returned invalid JSON.",
                correlation_id=request_correlation_id,
            ) from exc

        try:
            return _response_text(response_payload, request_correlation_id)
        except GeminiResponseError:
            logger.warning("gemini_invalid_payload correlation_id=%s", request_correlation_id)
            raise


__all__ = [
    "GeminiAPIError",
    "GeminiClient",
    "GeminiClientError",
    "GeminiConfigurationError",
    "GeminiRequestError",
    "GeminiResponseError",
    "GeminiTimeoutError",
    "GeminiTransportError",
]

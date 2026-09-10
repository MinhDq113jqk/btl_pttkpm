import base64
import hashlib
import hmac
import json
import math
import secrets
import time
from typing import Any
from uuid import UUID

from app.core.exceptions import AppError


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256${salt}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        algorithm, salt, stored_key = hashed.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return hmac.compare_digest(key.hex(), stored_key)
    except Exception:
        return False


def create_token(payload: dict[str, Any], secret: str, expires_in_seconds: int = 86400) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    exp = int(time.time()) + expires_in_seconds
    claims = {**payload, "exp": exp}

    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=").decode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).rstrip(b"=").decode("utf-8")
    signing_input = f"{header_b64}.{payload_b64}"

    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("utf-8")

    return f"{signing_input}.{sig_b64}"


def decode_token(token: str, secret: str) -> dict[str, Any]:
    try:
        if len(token) > 16384:
            raise ValueError("Token too large")
        parts = token.split(".")
        if len(parts) != 3:
            raise AppError("ERR-UNAUTHORIZED", "Token không hợp lệ", 401)
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        def decode_part(value: str) -> bytes:
            decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value:
                raise ValueError("Non-canonical base64url")
            return decoded

        expected_sig = decode_part(sig_b64)

        actual_sig = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AppError("ERR-UNAUTHORIZED", "Chữ ký token không hợp lệ", 401)

        def unique_object(pairs):
            result = {}
            for name, value in pairs:
                if name in result:
                    raise ValueError("Duplicate JSON key")
                result[name] = value
            return result

        header = json.loads(decode_part(header_b64), object_pairs_hook=unique_object)
        if (not isinstance(header, dict) or header.get("alg") != "HS256"
                or header.get("typ", "JWT") != "JWT" or "crit" in header or "b64" in header):
            raise ValueError("Unsupported JWT header")
        payload = json.loads(decode_part(payload_b64), object_pairs_hook=unique_object)
        if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
            raise ValueError("Invalid identity")
        UUID(payload["sub"])
        active_site = payload.get("active_site_id")
        if active_site is not None:
            if not isinstance(active_site, str):
                raise ValueError("Invalid site claim")
            UUID(active_site)

        expiration = payload.get("exp")
        if (type(expiration) not in (int, float) or not math.isfinite(expiration)
                or expiration <= time.time()):
            raise AppError("ERR-UNAUTHORIZED", "Phiên đăng nhập đã hết hạn", 401)

        return payload
    except AppError:
        raise
    except Exception:
        raise AppError("ERR-UNAUTHORIZED", "Xác thực token thất bại", 401)

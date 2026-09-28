from datetime import datetime, timedelta
import hashlib
import hmac
import math

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.login_throttle import LoginThrottle

_IDENTITY_DOMAIN = b"greencity/login-throttle/v1"
_ADMISSION_LOCK_NAMESPACE = 1196573516


def login_identity_key(username: str, secret: str) -> str:
    derived_key = hmac.new(secret.encode("utf-8"), _IDENTITY_DOMAIN, hashlib.sha256).digest()
    return hmac.new(derived_key, username.encode("utf-8"), hashlib.sha256).hexdigest()


def lock_login_identity(session: Session, identity_key: str) -> None:
    lock_key = int.from_bytes(bytes.fromhex(identity_key[:16]), "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def lock_new_identity_admission(session: Session) -> None:
    session.execute(text(
        "SELECT pg_advisory_xact_lock(:namespace, :lock_key)"
    ), {"namespace": _ADMISSION_LOCK_NAMESPACE, "lock_key": 1})


def login_throttle_has_capacity(session: Session, settings: Settings) -> bool:
    identity_count = session.scalar(select(func.count()).select_from(LoginThrottle))
    return identity_count < settings.login_throttle_max_identities


def prune_expired_login_identities(session: Session, now: datetime, settings: Settings) -> None:
    cutoff = now - timedelta(days=settings.login_throttle_retention_days)
    stale_keys = select(LoginThrottle.identity_key).where(LoginThrottle.updated_at < cutoff)
    session.execute(delete(LoginThrottle).where(LoginThrottle.identity_key.in_(stale_keys)))


def load_active_throttle(session: Session, identity_key: str, now: datetime,
                         settings: Settings) -> LoginThrottle | None:
    state = session.scalar(select(LoginThrottle).where(
        LoginThrottle.identity_key == identity_key,
    ).with_for_update())
    if (state is not None
            and state.last_failure_at <= now - timedelta(seconds=settings.login_throttle_reset_seconds)
            and (state.locked_until is None or state.locked_until <= now)):
        session.delete(state)
        session.flush()
        return None
    return state


def retry_after_seconds(state: LoginThrottle, now: datetime) -> int:
    if state.locked_until is None:
        return 0
    return max(1, math.ceil((state.locked_until - now).total_seconds()))


def record_login_failure(session: Session, identity_key: str, state: LoginThrottle | None,
                         now: datetime, settings: Settings) -> LoginThrottle:
    if state is None:
        state = LoginThrottle(
            identity_key=identity_key,
            failure_count=0,
            last_failure_at=now,
        )
        session.add(state)
    state.failure_count += 1
    state.last_failure_at = now
    state.locked_until = None
    if state.failure_count >= settings.login_throttle_failure_threshold:
        exponent = min(state.failure_count - settings.login_throttle_failure_threshold, 16)
        cooldown = min(
            settings.login_throttle_base_backoff_seconds * (2 ** exponent),
            settings.login_throttle_max_backoff_seconds,
        )
        state.locked_until = now + timedelta(seconds=cooldown)
    return state

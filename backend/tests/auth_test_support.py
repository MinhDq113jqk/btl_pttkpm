"""Issue a genuine database-backed session for adversarial token fixtures."""
from datetime import UTC, datetime
import time
from uuid import UUID, uuid4

from app.core.security import create_token
from app.models.account import Account
from app.models.auth_session import AuthSession


def mint_session_token(database, account_id: UUID, secret: str, *, claims: dict | None = None,
                       expires_in_seconds: int = 86400) -> str:
    issued_at = int(time.time())
    session_id = uuid4()
    with database.get_session() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError("A persisted account is required for a session token")
        account_version = account.session_version
        payload = {
            "sub": str(account.id),
            "tenant_id": str(account.tenant_id),
            "active_site_id": None,
            "purpose": "session",
        }
        payload.update(claims or {})
        payload.update({"sid": str(session_id), "sv": account_version, "iat": issued_at})
        session.add(AuthSession(
            id=session_id,
            account_id=account.id,
            session_version=account_version,
            created_at=datetime.fromtimestamp(issued_at, UTC),
            expires_at=datetime.fromtimestamp(issued_at + expires_in_seconds + 1, UTC),
        ))
        session.commit()
    return create_token(payload, secret, expires_in_seconds=expires_in_seconds)

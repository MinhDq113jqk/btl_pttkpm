"""Use revision-compatible SQL fixtures in migration path tests."""
from uuid import uuid4

from sqlalchemy import text


def add_legacy_account(session, *, tenant_id, username: str, full_name: str,
                      person_id=None):
    account_id = uuid4()
    session.execute(text(
        """INSERT INTO greencity.accounts
           (id, tenant_id, username, hashed_password, full_name, is_active, person_id)
           VALUES (:id, :tenant_id, :username, :password, :full_name, TRUE, :person_id)"""
    ), {
        "id": account_id,
        "tenant_id": tenant_id,
        "username": username,
        "password": "migration-fixture-placeholder",
        "full_name": full_name,
        "person_id": person_id,
    })
    return account_id

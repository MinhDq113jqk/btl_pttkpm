from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


class AuthSession(IdentityTimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint("session_version >= 1", name="session_version_positive"),
        CheckConstraint("expires_at > created_at", name="expires_after_creation"),
        Index("ix_auth_sessions_account_expires", "account_id", "expires_at"),
    )

    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("greencity.accounts.id", ondelete="CASCADE"), nullable=False,
    )
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

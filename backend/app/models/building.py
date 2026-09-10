from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin


class Building(IdentityTimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("site_id", "code", name="uq_buildings_site_id_code"),
        UniqueConstraint("id", "site_id", name="uq_buildings_id_site_id"),
    )

    site_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.sites.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    floors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    site = relationship("Site", backref="buildings")

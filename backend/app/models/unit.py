from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityTimestampMixin
from app.models.person import UnitPersonRelationship


class Unit(IdentityTimestampMixin, Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("building_id", "unit_number", name="uq_units_building_id_unit_number"),
    )

    building_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    area_m2: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="occupied")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    building = relationship("Building", backref="units")
    relationships = relationship("UnitPersonRelationship", backref="unit", cascade="all, delete-orphan")

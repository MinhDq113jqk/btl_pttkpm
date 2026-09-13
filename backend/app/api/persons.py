from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.policy import RESIDENT_READ_ROLES, UserContext, get_current_user_context, scope_not_found
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.unit import Unit
from app.schemas.person import PersonUnitRelationshipView, PersonUnitsResponse


router = APIRouter(prefix="/persons", tags=["persons"])


@router.get("/{person_id}/units", response_model=PersonUnitsResponse)
def get_person_units(
    person_id: UUID,
    request: Request,
    as_of: date = Query(default_factory=date.today),
    current_user: UserContext = Depends(get_current_user_context),
):
    """Return effective Person--Unit relationships inside the active server scope."""
    current_user.assert_role(*RESIDENT_READ_ROLES)
    scoped_unit_ids = current_user.units_query().with_only_columns(Unit.id)
    with request.app.state.database.get_session() as session:
        relationships = session.scalars(
            select(UnitPersonRelationship)
            .join(Person, UnitPersonRelationship.person_id == Person.id)
            .join(Unit, UnitPersonRelationship.unit_id == Unit.id)
            .where(
                Person.id == person_id,
                Person.tenant_id == current_user.tenant_id,
                Unit.id.in_(scoped_unit_ids),
                UnitPersonRelationship.valid_from <= as_of,
                or_(
                    UnitPersonRelationship.valid_to.is_(None),
                    UnitPersonRelationship.valid_to > as_of,
                ),
            )
            .options(
                selectinload(UnitPersonRelationship.person),
                selectinload(UnitPersonRelationship.unit)
                .selectinload(Unit.building)
                .selectinload(Building.site),
            )
            .order_by(Unit.unit_number, UnitPersonRelationship.id)
        ).all()
        if not relationships:
            raise scope_not_found()

        person = relationships[0].person
        return PersonUnitsResponse(
            person_id=person.id,
            full_name=person.full_name,
            phone_masked=person.phone_masked,
            email_masked=person.email_masked,
            as_of=as_of,
            items=[
                PersonUnitRelationshipView(
                    unit_id=relationship.unit.id,
                    unit_number=relationship.unit.unit_number,
                    building_id=relationship.unit.building.id,
                    building_code=relationship.unit.building.code,
                    site_id=relationship.unit.building.site.id,
                    site_code=relationship.unit.building.site.code,
                    relationship_type=relationship.relationship_type,
                    ownership_ratio=relationship.ownership_ratio,
                    valid_from=relationship.valid_from,
                    valid_to=relationship.valid_to,
                )
                for relationship in relationships
            ],
        )

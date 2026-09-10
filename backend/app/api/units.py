from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.database import Database
from app.core.policy import UserContext, get_current_user_context, scope_not_found
from app.models.building import Building
from app.models.person import Person, UnitPersonRelationship
from app.models.unit import Unit
from app.schemas.unit import ResidentInfo, Unit360Response

router = APIRouter(prefix="/units", tags=["units"])


@router.get("/{unit_id}/360", response_model=Unit360Response)
def get_unit_360(
    unit_id: UUID,
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    database: Database = request.app.state.database
    with database.get_session() as session:
        unit = session.execute(
            current_user.units_query()
            .where(Unit.id == unit_id)
            .options(
                selectinload(Unit.building).selectinload(Building.site),
            )
        ).scalar_one_or_none()

        if unit is None:
            raise scope_not_found()

        residents_visible, full_details = current_user.unit_projection(unit.building_id)
        # Do not even load household identity/relations for restricted projections.
        if residents_visible:
            loaded = session.execute(current_user.units_query().where(Unit.id == unit.id).options(
                selectinload(Unit.relationships).selectinload(UnitPersonRelationship.person),
                with_loader_criteria(Person, Person.tenant_id == current_user.tenant_id),
            )).scalar_one_or_none()
            if loaded is None:
                raise scope_not_found()

        residents = [
            ResidentInfo(
                person_id=rel.person.id,
                full_name=rel.person.full_name,
                phone_masked=rel.person.phone_masked,
                email_masked=rel.person.email_masked,
                relationship_type=rel.relationship_type,
                is_active=rel.is_active,
            )
            for rel in (unit.relationships if residents_visible else [])
            if rel.person is not None
        ]

        return Unit360Response(
            id=unit.id,
            unit_number=unit.unit_number,
            floor=unit.floor,
            area_m2=unit.area_m2 if full_details else None,
            status=unit.status if full_details else None,
            version=unit.version,
            building_id=unit.building.id,
            building_code=unit.building.code,
            building_name=unit.building.name,
            site_id=unit.building.site.id,
            site_code=unit.building.site.code,
            site_name=unit.building.site.name,
            residents=residents,
            residents_visible=residents_visible,
        )

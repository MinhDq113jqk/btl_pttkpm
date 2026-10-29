"""Resolve asset work orders through their immutable maintenance source."""
from sqlalchemy import select, or_
from app.models.maintenance import MaintenanceOccurrence, MaintenancePlan
from app.models.service import WorkOrder


def asset_work_orders(asset_id):
    return (select(WorkOrder)
            .outerjoin(MaintenanceOccurrence, WorkOrder.maintenance_occurrence_id == MaintenanceOccurrence.id)
            .outerjoin(MaintenancePlan, MaintenanceOccurrence.plan_id == MaintenancePlan.id)
            .where(or_(WorkOrder.asset_id == asset_id, MaintenancePlan.asset_id == asset_id)))

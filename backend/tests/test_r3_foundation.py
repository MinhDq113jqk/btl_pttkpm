from app.models import (
    CleaningChecklistResult,
    CleaningTask,
    CleaningTaskStatusEnum,
    IncidentEscalation,
    IncidentEscalationAcknowledgement,
    PatrolLog,
    PatrolWindow,
    PatrolWindowStatusEnum,
    SecurityIncident,
    SecurityIncidentEvidence,
    SecurityIncidentSeverityEnum,
    SecurityIncidentStatusEnum,
    SecurityShiftHandoff,
    SecurityVisitorLog,
)
from app.models.service import WorkOrder


def names(constraints):
    return {constraint.name for constraint in constraints}


def test_r3_state_enums_match_the_baselined_state_machines():
    assert {state.value for state in CleaningTaskStatusEnum} == {
        "PLANNED", "ASSIGNED", "IN_PROGRESS", "SUBMITTED", "ACCEPTED",
        "MISSED", "REWORK_REQUIRED", "CANCELLED",
    }
    assert {state.value for state in PatrolWindowStatusEnum} == {
        "SCHEDULED", "COMPLETED", "MISSED", "CANCELLED",
    }
    assert {state.value for state in SecurityIncidentStatusEnum} == {
        "NEW", "TRIAGED", "IN_PROGRESS", "RESOLVED", "CLOSED",
    }
    assert {severity.value for severity in SecurityIncidentSeverityEnum} == {
        "LOW", "MEDIUM", "HIGH", "CRITICAL",
    }


def test_r3_constraints_preserve_rework_and_patrol_idempotency_anchors():
    assert {
        "uq_cleaning_tasks_shift_stop",
        "uq_cleaning_tasks_rework_source",
        "ck_cleaning_tasks_cleaning_tasks_status",
    }.issubset(names(CleaningTask.__table__.constraints))
    assert {
        "uq_patrol_windows_shift_point_start",
        "ck_patrol_windows_patrol_windows_status",
        "ck_patrol_windows_patrol_windows_missed_reason",
    }.issubset(names(PatrolWindow.__table__.constraints))
    assert "uq_cleaning_checklist_results_task_position" in names(CleaningChecklistResult.__table__.constraints)
    assert "uq_work_orders_cleaning_task" in names(WorkOrder.__table__.constraints)
    assert "cleaning_task_id" in WorkOrder.__table__.c


def test_r3_timeline_models_are_separate_from_mutable_shift_and_incident_state():
    assert {
        SecurityShiftHandoff.__tablename__,
        SecurityVisitorLog.__tablename__,
        PatrolLog.__tablename__,
        IncidentEscalation.__tablename__,
        IncidentEscalationAcknowledgement.__tablename__,
        SecurityIncidentEvidence.__tablename__,
    } == {
        "security_shift_handoffs", "security_visitor_logs", "patrol_logs", "incident_escalations",
        "incident_escalation_acknowledgements", "security_incident_evidence",
    }
    assert {
        "ck_security_incidents_security_incidents_severity",
        "ck_security_incidents_security_incidents_status",
    }.issubset(names(SecurityIncident.__table__.constraints))

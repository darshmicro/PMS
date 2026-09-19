from datetime import date

from fastapi import HTTPException
import pytest

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import PerformanceCycle
from app.services.workflow_engine_service import (
    compute_sla_status,
    ensure_within_stage_window,
    get_next_stages,
    record_transition,
)


def _seed_performance(db_session, status="MANAGER_REVIEW", **cycle_kwargs) -> EmployeePerformance:
    employee = Employee(EmployeeCode="EMP-WE1", ADUsername="COMPANY\\we1", FullName="Workflow Engine Employee")
    cycle = PerformanceCycle(CycleName="WE-TEST-CYCLE", **cycle_kwargs)
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.commit()
    return performance


# ----------------------------------------------------------------- get_next_stages

def test_get_next_stages_returns_forward_and_return_edges():
    edges = get_next_stages("HOD_REVIEW")
    assert edges["forward"] == ["HR_REVIEW"]
    assert set(edges["return"]) == {"MANAGER_REVIEW", "SELF_ASSESSMENT"}


def test_get_next_stages_unknown_status_is_empty():
    assert get_next_stages("SOMETHING_MADE_UP") == {"forward": [], "return": []}


def test_final_approved_has_no_further_edges():
    assert get_next_stages("FINAL_APPROVED") == {"forward": [], "return": []}


# ------------------------------------------------------------ ensure_within_stage_window

def test_no_configured_window_never_gates(db_session):
    performance = _seed_performance(db_session, status="MANAGER_REVIEW")
    ensure_within_stage_window(performance)  # no dates set at all - should not raise


def test_status_with_no_window_mapping_never_gates(db_session):
    performance = _seed_performance(db_session, status="KPI_ASSIGNED", ManagerReviewStart=date(2026, 1, 1))
    ensure_within_stage_window(performance)  # KPI_ASSIGNED has no entry in STAGE_WINDOWS


def test_before_window_start_is_blocked(db_session):
    performance = _seed_performance(
        db_session, status="MANAGER_REVIEW", ManagerReviewStart=date(2026, 6, 1), ManagerReviewEnd=date(2026, 6, 30),
    )
    with pytest.raises(HTTPException) as exc_info:
        ensure_within_stage_window(performance, today=date(2026, 5, 15))
    assert exc_info.value.status_code == 409


def test_within_window_passes(db_session):
    performance = _seed_performance(
        db_session, status="MANAGER_REVIEW", ManagerReviewStart=date(2026, 6, 1), ManagerReviewEnd=date(2026, 6, 30),
    )
    ensure_within_stage_window(performance, today=date(2026, 6, 15))  # should not raise


def test_after_window_end_is_not_blocked(db_session):
    """Lateness is surfaced via compute_sla_status, not hard-gated - see
    workflow_engine_service module docstring for why."""
    performance = _seed_performance(
        db_session, status="MANAGER_REVIEW", ManagerReviewStart=date(2026, 6, 1), ManagerReviewEnd=date(2026, 6, 30),
    )
    ensure_within_stage_window(performance, today=date(2026, 7, 15))  # should not raise


# ----------------------------------------------------------------- compute_sla_status

def test_sla_status_not_overdue_within_window(db_session):
    performance = _seed_performance(
        db_session, status="HOD_REVIEW", HODReviewStart=date(2026, 6, 1), HODReviewEnd=date(2026, 6, 30),
    )
    sla = compute_sla_status(performance, today=date(2026, 6, 15))
    assert sla.is_overdue is False
    assert sla.days_overdue is None


def test_sla_status_overdue_after_window_end(db_session):
    performance = _seed_performance(
        db_session, status="HOD_REVIEW", HODReviewStart=date(2026, 6, 1), HODReviewEnd=date(2026, 6, 30),
    )
    sla = compute_sla_status(performance, today=date(2026, 7, 5))
    assert sla.is_overdue is True
    assert sla.days_overdue == 5


def test_sla_status_no_window_configured_is_never_overdue(db_session):
    performance = _seed_performance(db_session, status="HOD_REVIEW")
    sla = compute_sla_status(performance, today=date(2026, 7, 5))
    assert sla.is_overdue is False


# ------------------------------------------------------------------- record_transition

def test_record_transition_writes_a_row(db_session):
    performance = _seed_performance(db_session, status="HR_REVIEW")
    entry = record_transition(
        db_session, performance_id=performance.PerformanceID, from_status="HOD_REVIEW", to_status="HR_REVIEW",
        actioned_by_user_id=1, comments="approved",
    )
    assert entry.WorkflowHistoryID is not None
    assert entry.FromStatus == "HOD_REVIEW"
    assert entry.ToStatus == "HR_REVIEW"
    assert entry.Comments == "approved"

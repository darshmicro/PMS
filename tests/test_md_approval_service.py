import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hr_review import HRReview
from app.models.performance_masters import PerformanceCycle
from app.services.md_approval_service import (
    ensure_stage_editable,
    finalize_and_lock,
    get_hr_score,
    validate_return_has_comments,
)


def _seed_performance(db_session, status="MD_APPROVAL", hr_score=None) -> EmployeePerformance:
    employee = Employee(EmployeeCode="EMP-MDA1", ADUsername="COMPANY\\mda1", FullName="MD Approval Employee")
    cycle = PerformanceCycle(CycleName="MDA-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.flush()

    if hr_score is not None:
        db_session.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=hr_score))
    db_session.commit()
    return performance


# --------------------------------------------------------------------- get_hr_score

def test_get_hr_score_returns_the_score(db_session):
    performance = _seed_performance(db_session, hr_score=91.0)
    assert get_hr_score(db_session, performance.PerformanceID) == 91.0


def test_get_hr_score_fails_when_no_hr_review_exists(db_session):
    performance = _seed_performance(db_session, hr_score=None)
    with pytest.raises(HTTPException) as exc_info:
        get_hr_score(db_session, performance.PerformanceID)
    assert exc_info.value.status_code == 409


# ------------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_only_at_md_approval(db_session):
    performance = _seed_performance(db_session, status="MD_APPROVAL")
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_md_approval(db_session):
    performance = _seed_performance(db_session, status="PLANT_HEAD_APPROVAL")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_locked_record_never_editable(db_session):
    performance = _seed_performance(db_session, status="MD_APPROVAL")
    performance.IsLocked = True
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


# ------------------------------------------------------------- validate_return_has_comments

def test_return_without_comments_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_return_has_comments(None)
    assert exc_info.value.status_code == 400
    with pytest.raises(HTTPException):
        validate_return_has_comments("   ")


def test_return_with_comments_passes():
    validate_return_has_comments("Need clarification on the training recommendation")  # should not raise


# ------------------------------------------------------------------- finalize_and_lock

def test_finalize_and_lock_sets_status_and_locks(db_session):
    performance = _seed_performance(db_session, status="MD_APPROVAL")
    assert performance.IsLocked is False
    finalize_and_lock(performance)
    assert performance.Status == "FINAL_APPROVED"
    assert performance.IsLocked is True

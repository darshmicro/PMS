import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hod_review import HODReview
from app.models.hr_review import HRReview
from app.models.performance_masters import PerformanceCycle
from app.services.hr_review_service import (
    compute_hr_score,
    ensure_complete_ready,
    ensure_stage_editable,
    get_hod_score,
    validate_calibration_adjustment_reason,
    validate_hr_score_bounds,
)


def _seed_performance(db_session, status="HR_REVIEW", hod_score=None) -> EmployeePerformance:
    employee = Employee(EmployeeCode="EMP-HR1", ADUsername="COMPANY\\hr1", FullName="HR Review Employee")
    cycle = PerformanceCycle(CycleName="HR-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.flush()

    if hod_score is not None:
        db_session.add(HODReview(PerformanceID=performance.PerformanceID, HODScore=hod_score))
    db_session.commit()
    return performance


# --------------------------------------------------------------------- get_hod_score

def test_get_hod_score_returns_the_score(db_session):
    performance = _seed_performance(db_session, hod_score=82.5)
    assert get_hod_score(db_session, performance.PerformanceID) == 82.5


def test_get_hod_score_fails_when_no_hod_review_exists(db_session):
    performance = _seed_performance(db_session, hod_score=None)
    with pytest.raises(HTTPException) as exc_info:
        get_hod_score(db_session, performance.PerformanceID)
    assert exc_info.value.status_code == 409


# ------------------------------------------------------- validate_calibration_adjustment_reason

def test_zero_adjustment_never_requires_a_reason():
    validate_calibration_adjustment_reason(0, None)  # should not raise


def test_nonzero_adjustment_requires_a_reason():
    with pytest.raises(HTTPException) as exc_info:
        validate_calibration_adjustment_reason(5.0, None)
    assert exc_info.value.status_code == 400


def test_nonzero_adjustment_with_reason_passes():
    validate_calibration_adjustment_reason(-3.0, "Department-wide distribution skewed high")  # should not raise


def test_blank_reason_string_is_treated_as_missing():
    with pytest.raises(HTTPException):
        validate_calibration_adjustment_reason(2.0, "   ")


# ------------------------------------------------------------------- compute_hr_score

def test_hr_score_is_hod_score_plus_adjustment():
    assert compute_hr_score(80.0, 5.0) == 85.0
    assert compute_hr_score(80.0, -5.0) == 75.0
    assert compute_hr_score(80.0, 0) == 80.0


# -------------------------------------------------------------- validate_hr_score_bounds

def test_hr_score_bounds():
    validate_hr_score_bounds(0)
    validate_hr_score_bounds(100)
    with pytest.raises(HTTPException):
        validate_hr_score_bounds(-0.01)
    with pytest.raises(HTTPException):
        validate_hr_score_bounds(100.01)


# ------------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_only_at_hr_review(db_session):
    performance = _seed_performance(db_session, status="HR_REVIEW")
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_hr_review(db_session):
    performance = _seed_performance(db_session, status="HOD_REVIEW")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_locked_record_never_editable(db_session):
    performance = _seed_performance(db_session, status="HR_REVIEW")
    performance.IsLocked = True
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


# ----------------------------------------------------------------- ensure_complete_ready

def test_complete_blocked_when_no_review_row_exists():
    with pytest.raises(HTTPException) as exc_info:
        ensure_complete_ready(None)
    assert exc_info.value.status_code == 400


def test_complete_blocked_when_score_not_set():
    with pytest.raises(HTTPException):
        ensure_complete_ready(HRReview(PerformanceID=1, HRScore=None))


def test_complete_succeeds_once_scored():
    ensure_complete_ready(HRReview(PerformanceID=1, HRScore=80.0))  # should not raise

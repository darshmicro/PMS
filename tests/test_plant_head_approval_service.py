import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hr_review import HRReview
from app.models.performance_masters import PerformanceCycle
from app.services.plant_head_approval_service import (
    ensure_is_reviewing_plant_head,
    ensure_stage_editable,
    get_hr_score,
    validate_return_has_comments,
)


def _seed_performance(db_session, status="PLANT_HEAD_APPROVAL", hr_score=None, employee_plant_id=None) -> tuple[EmployeePerformance, Employee]:
    employee = Employee(
        EmployeeCode="EMP-PHA1", ADUsername="COMPANY\\pha1", FullName="Plant Head Approval Employee",
        PlantID=employee_plant_id,
    )
    cycle = PerformanceCycle(CycleName="PHA-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.flush()

    if hr_score is not None:
        db_session.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=hr_score))
    db_session.commit()
    return performance, employee


# --------------------------------------------------------------------- get_hr_score

def test_get_hr_score_returns_the_score(db_session):
    performance, _ = _seed_performance(db_session, hr_score=88.0)
    assert get_hr_score(db_session, performance.PerformanceID) == 88.0


def test_get_hr_score_fails_when_no_hr_review_exists(db_session):
    performance, _ = _seed_performance(db_session, hr_score=None)
    with pytest.raises(HTTPException) as exc_info:
        get_hr_score(db_session, performance.PerformanceID)
    assert exc_info.value.status_code == 409


# --------------------------------------------------------------- ensure_is_reviewing_plant_head

def test_matching_plant_head_passes(db_session):
    performance, _ = _seed_performance(db_session, employee_plant_id=1)
    plant_head = Employee(EmployeeCode="EMP-PH-BOSS", ADUsername="COMPANY\\phboss", FullName="Plant Head", PlantID=1)
    db_session.add(plant_head)
    db_session.commit()
    ensure_is_reviewing_plant_head(performance, db_session, plant_head.EmployeeID)  # should not raise


def test_mismatched_plant_is_forbidden(db_session):
    performance, _ = _seed_performance(db_session, employee_plant_id=1)
    other_plant_head = Employee(
        EmployeeCode="EMP-PH-OTHER", ADUsername="COMPANY\\phother", FullName="Other Plant Head", PlantID=2
    )
    db_session.add(other_plant_head)
    db_session.commit()
    with pytest.raises(HTTPException) as exc_info:
        ensure_is_reviewing_plant_head(performance, db_session, other_plant_head.EmployeeID)
    assert exc_info.value.status_code == 403


def test_no_plant_at_all_is_forbidden(db_session):
    performance, _ = _seed_performance(db_session, employee_plant_id=None)
    plant_head = Employee(EmployeeCode="EMP-PH-NOPLANT", ADUsername="COMPANY\\phnoplant", FullName="Plant Head", PlantID=None)
    db_session.add(plant_head)
    db_session.commit()
    with pytest.raises(HTTPException) as exc_info:
        ensure_is_reviewing_plant_head(performance, db_session, plant_head.EmployeeID)
    assert exc_info.value.status_code == 403


def test_unknown_employee_id_is_forbidden(db_session):
    performance, _ = _seed_performance(db_session, employee_plant_id=1)
    with pytest.raises(HTTPException):
        ensure_is_reviewing_plant_head(performance, db_session, 999999)


# ------------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_only_at_plant_head_approval(db_session):
    performance, _ = _seed_performance(db_session, status="PLANT_HEAD_APPROVAL")
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_plant_head_approval(db_session):
    performance, _ = _seed_performance(db_session, status="HR_REVIEW")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_locked_record_never_editable(db_session):
    performance, _ = _seed_performance(db_session, status="PLANT_HEAD_APPROVAL")
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
    validate_return_has_comments("Score seems inconsistent with peer group - please recheck")  # should not raise

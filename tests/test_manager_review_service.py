import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.manager_review import ManagerReview
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.models.self_assessment import SelfAssessment
from app.services.manager_review_service import (
    ensure_is_reviewing_manager,
    ensure_stage_editable,
    validate_manager_score,
    validate_override_has_comments,
    validate_submission_ready,
)


def _seed_performance(db_session, status="MANAGER_REVIEW", with_manager=True) -> EmployeePerformance:
    manager = Employee(EmployeeCode="EMP-MGR1", ADUsername="COMPANY\\mgr1", FullName="Manager One")
    db_session.add(manager)
    db_session.flush()

    employee = Employee(
        EmployeeCode="EMP-MR1", ADUsername="COMPANY\\mr1", FullName="Manager Review Employee",
        ManagerID=manager.EmployeeID if with_manager else None,
    )
    cycle = PerformanceCycle(CycleName="MR-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.commit()
    performance._manager_id = manager.EmployeeID
    return performance


def _seed_kpi(db_session, performance, kpi_code="KPI-MR1", weightage=100.0):
    kpa = KPAMaster(KPACode=f"{kpi_code}-KPA", KPAName=f"{kpi_code} KPA", IsActive=True)
    db_session.add(kpa)
    db_session.flush()
    kpi = KPIMaster(KPICode=kpi_code, KPIName=f"{kpi_code} name", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    db_session.add(kpi)
    db_session.flush()

    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=weightage)
    db_session.add(ek)
    db_session.flush()
    employee_kpi = EmployeeKPI(
        EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE",
        Weightage=weightage, Target=100.0,
    )
    db_session.add(employee_kpi)
    db_session.commit()
    return kpi, employee_kpi


# --------------------------------------------------------------- validate_manager_score

def test_manager_score_bounds():
    validate_manager_score(1)
    validate_manager_score(5)
    with pytest.raises(HTTPException):
        validate_manager_score(0)
    with pytest.raises(HTTPException):
        validate_manager_score(6)


# ------------------------------------------------------------ validate_override_has_comments

def test_override_without_comments_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_override_has_comments(manager_score=4, self_score=2, manager_comments=None)
    assert exc_info.value.status_code == 400


def test_override_with_comments_passes():
    validate_override_has_comments(manager_score=4, self_score=2, manager_comments="Adjusted for quality issues")


def test_matching_score_never_requires_comments():
    validate_override_has_comments(manager_score=3, self_score=3, manager_comments=None)  # should not raise


def test_no_self_score_means_nothing_to_override():
    validate_override_has_comments(manager_score=4, self_score=None, manager_comments=None)  # should not raise


# ------------------------------------------------------------ ensure_is_reviewing_manager

def test_direct_manager_may_edit(db_session):
    performance = _seed_performance(db_session)
    ensure_is_reviewing_manager(performance, db_session, performance._manager_id)  # should not raise


def test_non_manager_is_blocked(db_session):
    performance = _seed_performance(db_session)
    with pytest.raises(HTTPException) as exc_info:
        ensure_is_reviewing_manager(performance, db_session, performance._manager_id + 999)
    assert exc_info.value.status_code == 403


def test_employee_with_no_manager_set_blocks_everyone(db_session):
    performance = _seed_performance(db_session, with_manager=False)
    with pytest.raises(HTTPException):
        ensure_is_reviewing_manager(performance, db_session, 1)


# ------------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_only_at_manager_review(db_session):
    performance = _seed_performance(db_session, status="MANAGER_REVIEW")
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_manager_review(db_session):
    performance = _seed_performance(db_session, status="SELF_ASSESSMENT")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_locked_record_never_editable(db_session):
    performance = _seed_performance(db_session, status="MANAGER_REVIEW")
    performance.IsLocked = True
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


# --------------------------------------------------------------- validate_submission_ready

def test_submission_blocked_when_a_kpi_has_no_manager_score(db_session):
    performance = _seed_performance(db_session)
    kpi, employee_kpi = _seed_kpi(db_session, performance)
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance, [], [])
    assert exc_info.value.status_code == 400
    assert kpi.KPIName in exc_info.value.detail


def test_submission_blocked_on_unexplained_override(db_session):
    performance = _seed_performance(db_session)
    kpi, employee_kpi = _seed_kpi(db_session, performance)
    sa = SelfAssessment(EmployeeKPIID=employee_kpi.EmployeeKPIID, Achievement=80, AchievementPct=80, SelfScore=3)
    review = ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=5, ManagerComments=None)
    db_session.add_all([sa, review])
    db_session.commit()
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance, [review], [sa])
    assert "override" in exc_info.value.detail.lower()


def test_submission_succeeds_when_every_kpi_scored_and_overrides_explained(db_session):
    performance = _seed_performance(db_session)
    kpi, employee_kpi = _seed_kpi(db_session, performance)
    sa = SelfAssessment(EmployeeKPIID=employee_kpi.EmployeeKPIID, Achievement=80, AchievementPct=80, SelfScore=3)
    review = ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=5, ManagerComments="Exceeded expectations on quality")
    db_session.add_all([sa, review])
    db_session.commit()
    db_session.refresh(performance)

    validate_submission_ready(performance, [review], [sa])  # should not raise

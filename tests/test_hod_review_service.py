import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.hod_review import HODReview
from app.models.manager_review import ManagerReview
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.services.hod_review_service import (
    compute_manager_weighted_score_pct,
    ensure_approve_ready,
    ensure_is_reviewing_hod,
    ensure_stage_editable,
    validate_hod_score,
    validate_override_has_comments,
)


def _seed_performance(db_session, status="HOD_REVIEW", with_hod=True) -> EmployeePerformance:
    hod = Employee(EmployeeCode="EMP-HOD1", ADUsername="COMPANY\\hod1", FullName="HOD One")
    db_session.add(hod)
    db_session.flush()

    employee = Employee(
        EmployeeCode="EMP-HR1", ADUsername="COMPANY\\hodemp1", FullName="HOD Review Employee",
        HODID=hod.EmployeeID if with_hod else None,
    )
    cycle = PerformanceCycle(CycleName="HOD-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.commit()
    performance._hod_id = hod.EmployeeID
    return performance


def _seed_kpi_with_manager_score(db_session, performance, kpi_code, weightage, manager_score):
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
        EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=weightage, Target=100.0,
    )
    db_session.add(employee_kpi)
    db_session.flush()
    review = ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=manager_score) if manager_score is not None else None
    if review is not None:
        db_session.add(review)
    db_session.commit()
    return employee_kpi, review


# --------------------------------------------------- compute_manager_weighted_score_pct

def test_weighted_score_computed_across_all_kpis(db_session):
    performance = _seed_performance(db_session)
    _, r1 = _seed_kpi_with_manager_score(db_session, performance, "KPI-W1", 60, 4)  # 4*60/5 = 48
    _, r2 = _seed_kpi_with_manager_score(db_session, performance, "KPI-W2", 40, 5)  # 5*40/5 = 40
    db_session.refresh(performance)

    result = compute_manager_weighted_score_pct(performance, [r1, r2])
    assert result == 88.0


def test_weighted_score_none_when_a_kpi_is_unscored(db_session):
    performance = _seed_performance(db_session)
    _, r1 = _seed_kpi_with_manager_score(db_session, performance, "KPI-W3", 60, 4)
    _seed_kpi_with_manager_score(db_session, performance, "KPI-W4", 40, None)  # unscored
    db_session.refresh(performance)

    assert compute_manager_weighted_score_pct(performance, [r1]) is None


# --------------------------------------------------------------- validate_hod_score

def test_hod_score_bounds():
    validate_hod_score(0)
    validate_hod_score(100)
    with pytest.raises(HTTPException):
        validate_hod_score(-1)
    with pytest.raises(HTTPException):
        validate_hod_score(101)


# ------------------------------------------------------------ validate_override_has_comments

def test_override_without_comments_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        validate_override_has_comments(hod_score=90, reference_pct=70, hod_comments=None)
    assert exc_info.value.status_code == 400


def test_override_with_comments_passes():
    validate_override_has_comments(hod_score=90, reference_pct=70, hod_comments="Adjusted for cross-team contribution")


def test_matching_score_never_requires_comments():
    validate_override_has_comments(hod_score=88, reference_pct=88, hod_comments=None)  # should not raise


def test_no_reference_means_nothing_to_override():
    validate_override_has_comments(hod_score=90, reference_pct=None, hod_comments=None)  # should not raise


def test_tiny_rounding_difference_does_not_require_comments():
    validate_override_has_comments(hod_score=88.005, reference_pct=88.0, hod_comments=None)  # should not raise


# ------------------------------------------------------------ ensure_is_reviewing_hod

def test_direct_hod_may_edit(db_session):
    performance = _seed_performance(db_session)
    ensure_is_reviewing_hod(performance, db_session, performance._hod_id)  # should not raise


def test_non_hod_is_blocked(db_session):
    performance = _seed_performance(db_session)
    with pytest.raises(HTTPException) as exc_info:
        ensure_is_reviewing_hod(performance, db_session, performance._hod_id + 999)
    assert exc_info.value.status_code == 403


def test_employee_with_no_hod_set_blocks_everyone(db_session):
    performance = _seed_performance(db_session, with_hod=False)
    with pytest.raises(HTTPException):
        ensure_is_reviewing_hod(performance, db_session, 1)


# ------------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_only_at_hod_review(db_session):
    performance = _seed_performance(db_session, status="HOD_REVIEW")
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_hod_review(db_session):
    performance = _seed_performance(db_session, status="MANAGER_REVIEW")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_locked_record_never_editable(db_session):
    performance = _seed_performance(db_session, status="HOD_REVIEW")
    performance.IsLocked = True
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


# ----------------------------------------------------------------- ensure_approve_ready

def test_approve_blocked_when_no_review_row_exists():
    with pytest.raises(HTTPException) as exc_info:
        ensure_approve_ready(None)
    assert exc_info.value.status_code == 400


def test_approve_blocked_when_score_not_set():
    with pytest.raises(HTTPException):
        ensure_approve_ready(HODReview(PerformanceID=1, HODScore=None))


def test_approve_succeeds_once_scored():
    ensure_approve_ready(HODReview(PerformanceID=1, HODScore=85.0))  # should not raise

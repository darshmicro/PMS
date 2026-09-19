import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import KPAMaster, KPIMaster, KPIScoringRule, PerformanceCycle
from app.models.self_assessment import SelfAssessment
from app.services.self_assessment_service import (
    EMPLOYEE_ACKNOWLEDGED,
    compute_achievement_pct,
    ensure_own_record,
    ensure_stage_editable,
    lookup_self_score,
    validate_self_score,
    validate_submission_ready,
)


def _seed_performance(db_session, status="EMPLOYEE_ACKNOWLEDGED") -> EmployeePerformance:
    employee = Employee(EmployeeCode="EMP-SA1", ADUsername="COMPANY\\sa1", FullName="Self Assess One")
    cycle = PerformanceCycle(CycleName="SA-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.commit()
    return performance


def _seed_kpi(db_session, performance, kpi_code="KPI-SA1", measurement_type="PERCENTAGE", weightage=100.0, target=100.0):
    kpa = KPAMaster(KPACode=f"{kpi_code}-KPA", KPAName=f"{kpi_code} KPA", IsActive=True)
    db_session.add(kpa)
    db_session.flush()
    kpi = KPIMaster(KPICode=kpi_code, KPIName=f"{kpi_code} name", KPAID=kpa.KPAID, MeasurementType=measurement_type, IsActive=True)
    db_session.add(kpi)
    db_session.flush()

    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=weightage)
    db_session.add(ek)
    db_session.flush()
    employee_kpi = EmployeeKPI(
        EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType=measurement_type,
        Weightage=weightage, Target=target,
    )
    db_session.add(employee_kpi)
    db_session.commit()
    return kpi, employee_kpi


# ------------------------------------------------------------- compute_achievement_pct

def test_numeric_type_computes_percentage_against_target():
    assert compute_achievement_pct("PERCENTAGE", 80.0, 100.0) == 80.0


def test_non_numeric_type_returns_none():
    assert compute_achievement_pct("QUALITATIVE", 80.0, 100.0) is None


def test_missing_target_returns_none():
    assert compute_achievement_pct("PERCENTAGE", 80.0, None) is None


def test_zero_target_returns_none_instead_of_dividing_by_zero():
    assert compute_achievement_pct("PERCENTAGE", 80.0, 0.0) is None


# ----------------------------------------------------------------- lookup_self_score

def test_lookup_prefers_kpi_specific_rule_over_global(db_session):
    performance = _seed_performance(db_session)
    kpi, _ = _seed_kpi(db_session, performance)
    db_session.add_all([
        KPIScoringRule(KPIID=kpi.KPIID, MinAchievement=0, MaxAchievement=100, Score=5, IsActive=True),
        KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=100, Score=1, IsActive=True),
    ])
    db_session.commit()

    assert lookup_self_score(db_session, kpi.KPIID, 50.0) == 5


def test_lookup_falls_back_to_global_default(db_session):
    performance = _seed_performance(db_session)
    kpi, _ = _seed_kpi(db_session, performance)
    db_session.add(KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=100, Score=3, IsActive=True))
    db_session.commit()

    assert lookup_self_score(db_session, kpi.KPIID, 50.0) == 3


def test_lookup_raises_when_no_band_covers_the_percentage(db_session):
    performance = _seed_performance(db_session)
    kpi, _ = _seed_kpi(db_session, performance)
    db_session.add(KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=50, Score=3, IsActive=True))
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        lookup_self_score(db_session, kpi.KPIID, 75.0)
    assert exc_info.value.status_code == 400


# --------------------------------------------------------------- validate_self_score

def test_self_score_bounds():
    validate_self_score(1)
    validate_self_score(5)
    with pytest.raises(HTTPException):
        validate_self_score(0)
    with pytest.raises(HTTPException):
        validate_self_score(6)


# ----------------------------------------------------------------- ensure_own_record

def test_ensure_own_record_allows_the_owning_employee(db_session):
    performance = _seed_performance(db_session)
    ensure_own_record(performance, performance.EmployeeID)  # should not raise


def test_ensure_own_record_blocks_everyone_else(db_session):
    performance = _seed_performance(db_session)
    with pytest.raises(HTTPException) as exc_info:
        ensure_own_record(performance, performance.EmployeeID + 999)
    assert exc_info.value.status_code == 403


# --------------------------------------------------------------- ensure_stage_editable

def test_stage_editable_in_acknowledged_and_in_progress(db_session):
    performance = _seed_performance(db_session, status="EMPLOYEE_ACKNOWLEDGED")
    ensure_stage_editable(performance)  # should not raise
    performance.Status = "SELF_ASSESSMENT"
    ensure_stage_editable(performance)  # should not raise


def test_stage_not_editable_before_acknowledgement(db_session):
    performance = _seed_performance(db_session, status="KPI_ASSIGNED")
    with pytest.raises(HTTPException) as exc_info:
        ensure_stage_editable(performance)
    assert exc_info.value.status_code == 409


def test_stage_not_editable_once_submitted(db_session):
    performance = _seed_performance(db_session, status="MANAGER_REVIEW")
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


def test_locked_record_is_never_editable(db_session):
    performance = _seed_performance(db_session, status="SELF_ASSESSMENT")
    performance.IsLocked = True
    with pytest.raises(HTTPException):
        ensure_stage_editable(performance)


# ------------------------------------------------------------- validate_submission_ready

def test_submission_blocked_when_a_kpi_has_no_achievement_recorded(db_session):
    performance = _seed_performance(db_session)
    kpi, employee_kpi = _seed_kpi(db_session, performance)
    sa = SelfAssessment(EmployeeKPIID=employee_kpi.EmployeeKPIID, Achievement=None, SelfScore=None)
    db_session.add(sa)
    db_session.commit()
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance, [sa])
    assert exc_info.value.status_code == 400
    assert kpi.KPIName in exc_info.value.detail


def test_submission_succeeds_when_every_kpi_is_assessed(db_session):
    performance = _seed_performance(db_session)
    kpi, employee_kpi = _seed_kpi(db_session, performance)
    sa = SelfAssessment(EmployeeKPIID=employee_kpi.EmployeeKPIID, Achievement=90.0, AchievementPct=90.0, SelfScore=4)
    db_session.add(sa)
    db_session.commit()
    db_session.refresh(performance)

    validate_submission_ready(performance, [sa])  # should not raise

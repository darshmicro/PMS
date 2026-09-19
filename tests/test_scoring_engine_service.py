import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.employee_competency import EmployeeCompetency
from app.models.hr_review import HRReview
from app.models.manager_review import ManagerReview
from app.models.performance_masters import CompetencyMaster, KPAMaster, KPIMaster, PerformanceCycle, RatingMaster
from app.models.performance_score import PerformanceRating
from app.services.scoring_engine_service import (
    compute_competency_weighted_pct,
    compute_kpi_weighted_pct,
    get_final_score,
    lookup_rating_band,
    run_scoring_engine,
)


def _seed_base(db_session, status="MD_APPROVAL", hr_score=None):
    employee = Employee(EmployeeCode="EMP-SE1", ADUsername="COMPANY\\se1", FullName="Scoring Engine Employee")
    cycle = PerformanceCycle(CycleName="SE-TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status=status)
    db_session.add(performance)
    db_session.flush()

    kpa_master = KPAMaster(KPACode="KPA-SE1", KPAName="Quality")
    db_session.add(kpa_master)
    db_session.flush()

    kpi_master = KPIMaster(KPICode="KPI-SE1", KPIName="Defect Rate", KPAID=kpa_master.KPAID, MeasurementType="PERCENTAGE")
    db_session.add(kpi_master)
    db_session.flush()

    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa_master.KPAID, Weightage=100)
    db_session.add(employee_kpa)
    db_session.flush()

    employee_kpi = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_master.KPIID, MeasurementType="PERCENTAGE", Weightage=100,
    )
    db_session.add(employee_kpi)
    db_session.flush()

    if hr_score is not None:
        db_session.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=hr_score))

    db_session.commit()
    return performance, employee_kpi


# --------------------------------------------------------------------- compute_kpi_weighted_pct

def test_kpi_weighted_pct_none_when_unscored(db_session):
    performance, _ = _seed_base(db_session)
    assert compute_kpi_weighted_pct(db_session, performance) is None


def test_kpi_weighted_pct_computes_correctly(db_session):
    performance, employee_kpi = _seed_base(db_session)
    db_session.add(ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=4))
    db_session.commit()
    # ManagerScore(4) * Weightage(100) / 5 = 80.0
    assert compute_kpi_weighted_pct(db_session, performance) == 80.0


# ------------------------------------------------------------- compute_competency_weighted_pct

def test_competency_weighted_pct_zero_when_none_assigned(db_session):
    performance, _ = _seed_base(db_session)
    assert compute_competency_weighted_pct(db_session, performance.PerformanceID) == 0.0


def test_competency_weighted_pct_computes_correctly(db_session):
    performance, _ = _seed_base(db_session)
    competency = CompetencyMaster(CompetencyCode="COMP-SE1", CompetencyName="Teamwork")
    db_session.add(competency)
    db_session.flush()
    db_session.add(EmployeeCompetency(
        PerformanceID=performance.PerformanceID, CompetencyID=competency.CompetencyID, Weightage=100, Score=5,
    ))
    db_session.commit()
    # Score(5) * Weightage(100) / 5 = 100.0
    assert compute_competency_weighted_pct(db_session, performance.PerformanceID) == 100.0


def test_competency_weighted_pct_blocks_when_unscored(db_session):
    performance, _ = _seed_base(db_session)
    competency = CompetencyMaster(CompetencyCode="COMP-SE2", CompetencyName="Communication")
    db_session.add(competency)
    db_session.flush()
    db_session.add(EmployeeCompetency(
        PerformanceID=performance.PerformanceID, CompetencyID=competency.CompetencyID, Weightage=100, Score=None,
    ))
    db_session.commit()
    with pytest.raises(HTTPException) as exc_info:
        compute_competency_weighted_pct(db_session, performance.PerformanceID)
    assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- get_final_score

def test_get_final_score_returns_hr_score(db_session):
    performance, _ = _seed_base(db_session, hr_score=88.0)
    assert get_final_score(db_session, performance.PerformanceID) == 88.0


def test_get_final_score_fails_without_hr_review(db_session):
    performance, _ = _seed_base(db_session, hr_score=None)
    with pytest.raises(HTTPException) as exc_info:
        get_final_score(db_session, performance.PerformanceID)
    assert exc_info.value.status_code == 409


# ------------------------------------------------------------------------- lookup_rating_band

def test_lookup_rating_band_found(db_session):
    db_session.add(RatingMaster(RatingLabel="Excellent", MinPercent=80, MaxPercent=100))
    db_session.add(RatingMaster(RatingLabel="Good", MinPercent=60, MaxPercent=79.99))
    db_session.commit()
    band = lookup_rating_band(db_session, 85.0)
    assert band.RatingLabel == "Excellent"


def test_lookup_rating_band_not_found_is_409(db_session):
    db_session.add(RatingMaster(RatingLabel="Excellent", MinPercent=80, MaxPercent=100))
    db_session.commit()
    with pytest.raises(HTTPException) as exc_info:
        lookup_rating_band(db_session, 50.0)
    assert exc_info.value.status_code == 409


def test_lookup_rating_band_ignores_inactive_bands(db_session):
    db_session.add(RatingMaster(RatingLabel="Old Band", MinPercent=0, MaxPercent=100, IsActive=False))
    db_session.commit()
    with pytest.raises(HTTPException):
        lookup_rating_band(db_session, 50.0)


# ----------------------------------------------------------------------- run_scoring_engine

def test_run_scoring_engine_end_to_end(db_session):
    performance, employee_kpi = _seed_base(db_session, hr_score=82.0)
    db_session.add(ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=4))
    db_session.add(RatingMaster(RatingLabel="Very Good", MinPercent=80, MaxPercent=89.99))
    db_session.commit()

    rating = run_scoring_engine(db_session, performance, actioned_by_user_id=1)
    db_session.commit()

    assert rating.FinalScorePct == 82.0
    assert performance.FinalScorePct == 82.0
    assert performance.FinalRatingID == rating.RatingID


def test_run_scoring_engine_is_idempotent(db_session):
    performance, employee_kpi = _seed_base(db_session, hr_score=82.0)
    db_session.add(ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=4))
    db_session.add(RatingMaster(RatingLabel="Very Good", MinPercent=80, MaxPercent=89.99))
    db_session.commit()

    first = run_scoring_engine(db_session, performance, actioned_by_user_id=1)
    db_session.commit()
    second = run_scoring_engine(db_session, performance, actioned_by_user_id=1)
    db_session.commit()

    assert first.PerformanceRatingID == second.PerformanceRatingID
    assert db_session.query(PerformanceRating).filter(
        PerformanceRating.PerformanceID == performance.PerformanceID
    ).count() == 1

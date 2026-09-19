import pytest
from fastapi import HTTPException

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.services.assignment_service import (
    check_duplicate_kpi,
    recompute_rollups,
    validate_row_weightage,
    validate_submission_ready,
    validate_target,
)


def _seed_performance(db_session) -> EmployeePerformance:
    employee = Employee(EmployeeCode="EMP-A1", ADUsername="COMPANY\\a1", FullName="Assignee One")
    cycle = PerformanceCycle(CycleName="TEST-CYCLE")
    db_session.add_all([employee, cycle])
    db_session.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="DRAFT")
    db_session.add(performance)
    db_session.commit()
    return performance


def _seed_kpa_kpi(db_session, kpa_code="KPA-A1", kpi_code="KPI-A1", measurement_type="PERCENTAGE"):
    kpa = KPAMaster(KPACode=kpa_code, KPAName=f"{kpa_code} name", IsActive=True)
    db_session.add(kpa)
    db_session.flush()
    kpi = KPIMaster(KPICode=kpi_code, KPIName=f"{kpi_code} name", KPAID=kpa.KPAID, MeasurementType=measurement_type, IsActive=True)
    db_session.add(kpi)
    db_session.commit()
    return kpa, kpi


# ---------------------------------------------------------------- validate_target

def test_numeric_measurement_type_requires_target():
    with pytest.raises(HTTPException) as exc_info:
        validate_target("PERCENTAGE", None)
    assert exc_info.value.status_code == 400


def test_numeric_measurement_type_rejects_negative_target():
    with pytest.raises(HTTPException):
        validate_target("NUMERIC", -5.0)


def test_qualitative_type_does_not_require_target():
    validate_target("QUALITATIVE", None)  # should not raise


def test_yesno_type_does_not_require_target():
    validate_target("YESNO", None)  # should not raise


# ------------------------------------------------------------- validate_row_weightage

def test_weightage_must_be_positive_and_at_most_100():
    validate_row_weightage(50.0)  # fine
    with pytest.raises(HTTPException):
        validate_row_weightage(0)
    with pytest.raises(HTTPException):
        validate_row_weightage(-10)
    with pytest.raises(HTTPException):
        validate_row_weightage(101)


# ----------------------------------------------------------------- check_duplicate_kpi

def test_duplicate_kpi_across_different_kpas_is_rejected(db_session):
    performance = _seed_performance(db_session)
    kpa1, kpi1 = _seed_kpa_kpi(db_session, "KPA-D1", "KPI-D1")
    kpa2, _ = _seed_kpa_kpi(db_session, "KPA-D2", "KPI-D2")  # different KPA, but we'll reuse kpi1's ID

    ek1 = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa1.KPAID, Weightage=0)
    db_session.add(ek1)
    db_session.flush()
    db_session.add(EmployeeKPI(
        EmployeeKPAID=ek1.EmployeeKPAID, KPIID=kpi1.KPIID, MeasurementType="PERCENTAGE", Weightage=50,
    ))
    db_session.commit()

    # Same KPI, even filed under a conceptually different EmployeeKPA, must be rejected
    with pytest.raises(HTTPException) as exc_info:
        check_duplicate_kpi(db_session, performance.PerformanceID, kpi1.KPIID)
    assert exc_info.value.status_code == 409


def test_duplicate_check_excludes_the_row_being_edited(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi = _seed_kpa_kpi(db_session, "KPA-D3", "KPI-D3")
    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    row = EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=50)
    db_session.add(row)
    db_session.commit()

    # Editing this exact row (excluding its own id) must not flag itself as a duplicate
    check_duplicate_kpi(db_session, performance.PerformanceID, kpi.KPIID, exclude_employee_kpi_id=row.EmployeeKPIID)


# ------------------------------------------------------------------- recompute_rollups

def test_recompute_rollups_sums_kpi_weightage_into_kpa_and_total(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi1 = _seed_kpa_kpi(db_session, "KPA-R1", "KPI-R1")
    _, kpi2 = _seed_kpa_kpi(db_session, "KPA-R1-dup", "KPI-R2")  # separate KPA for kpi2's own KPAID FK, unused here

    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    db_session.add_all([
        EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi1.KPIID, MeasurementType="PERCENTAGE", Weightage=30),
        EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi2.KPIID, MeasurementType="PERCENTAGE", Weightage=20),
    ])
    db_session.commit()

    updated = recompute_rollups(db_session, performance.PerformanceID)
    assert float(updated.kpas[0].Weightage) == 50.0
    assert float(updated.TotalWeightage) == 50.0


# --------------------------------------------------------------- validate_submission_ready

def test_submission_blocked_when_total_weightage_below_100(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi = _seed_kpa_kpi(db_session, "KPA-S1", "KPI-S1")
    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    db_session.add(EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=60))
    db_session.commit()
    recompute_rollups(db_session, performance.PerformanceID)
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance)
    assert exc_info.value.status_code == 400
    assert "less than 100" in exc_info.value.detail


def test_submission_blocked_when_total_weightage_exceeds_100(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi = _seed_kpa_kpi(db_session, "KPA-S2", "KPI-S2")
    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    db_session.add(EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=100))
    db_session.flush()
    db_session.add(EmployeeKPI(
        EmployeeKPAID=ek.EmployeeKPAID,
        KPIID=_seed_kpa_kpi(db_session, "KPA-S2b", "KPI-S2b")[1].KPIID,
        MeasurementType="PERCENTAGE", Weightage=10,
    ))
    db_session.commit()
    recompute_rollups(db_session, performance.PerformanceID)
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance)
    assert "exceeds 100" in exc_info.value.detail


def test_submission_blocked_when_a_kpa_has_no_kpi_attached(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi = _seed_kpa_kpi(db_session, "KPA-S3", "KPI-S3")
    ek_with_kpi = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    empty_kpa, _ = _seed_kpa_kpi(db_session, "KPA-S3-empty", "KPI-S3-empty")
    ek_empty = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=empty_kpa.KPAID, Weightage=0)
    db_session.add_all([ek_with_kpi, ek_empty])
    db_session.flush()
    db_session.add(EmployeeKPI(EmployeeKPAID=ek_with_kpi.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=100))
    db_session.commit()
    recompute_rollups(db_session, performance.PerformanceID)
    db_session.refresh(performance)

    with pytest.raises(HTTPException) as exc_info:
        validate_submission_ready(performance)
    assert "Missing mandatory KPI" in exc_info.value.detail
    assert empty_kpa.KPAName in exc_info.value.detail


def test_submission_succeeds_when_total_is_exactly_100_and_every_kpa_has_a_kpi(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi = _seed_kpa_kpi(db_session, "KPA-S4", "KPI-S4")
    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    db_session.add(EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="PERCENTAGE", Weightage=100))
    db_session.commit()
    recompute_rollups(db_session, performance.PerformanceID)
    db_session.refresh(performance)

    validate_submission_ready(performance)  # should not raise


def test_submission_tolerates_rounding_noise_near_100(db_session):
    performance = _seed_performance(db_session)
    kpa, kpi1 = _seed_kpa_kpi(db_session, "KPA-S5", "KPI-S5")
    _, kpi2 = _seed_kpa_kpi(db_session, "KPA-S5b", "KPI-S5b")
    _, kpi3 = _seed_kpa_kpi(db_session, "KPA-S5c", "KPI-S5c")
    ek = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=0)
    db_session.add(ek)
    db_session.flush()
    # 33.33 x 3 = 99.99, within the tolerance band
    db_session.add_all([
        EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi1.KPIID, MeasurementType="PERCENTAGE", Weightage=33.33),
        EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi2.KPIID, MeasurementType="PERCENTAGE", Weightage=33.33),
        EmployeeKPI(EmployeeKPAID=ek.EmployeeKPAID, KPIID=kpi3.KPIID, MeasurementType="PERCENTAGE", Weightage=33.33),
    ])
    db_session.commit()
    recompute_rollups(db_session, performance.PerformanceID)
    db_session.refresh(performance)

    validate_submission_ready(performance)  # should not raise despite 99.99 != 100.00 exactly

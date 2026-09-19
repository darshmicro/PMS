from dataclasses import dataclass

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import PerformanceCycle, RatingMaster
from app.services.dashboard_service import (
    SCOPE_DEPT,
    SCOPE_ORG,
    SCOPE_OWN,
    SCOPE_PLANT,
    SCOPE_TEAM,
    apply_dashboard_scope,
    summarize,
    system_health,
)


@dataclass
class _Ctx:
    employee_id: int | None
    role_codes: list[str]


def _seed_org(db_session):
    hod = Employee(EmployeeCode="D-HOD", ADUsername="COMPANY\\dhod", FullName="Dept Hod", PlantID=1)
    manager = Employee(EmployeeCode="D-MGR", ADUsername="COMPANY\\dmgr", FullName="Dept Manager", PlantID=1)
    plant_head = Employee(EmployeeCode="D-PH", ADUsername="COMPANY\\dph", FullName="Plant Head One", PlantID=1)
    other_plant_head = Employee(EmployeeCode="D-PH2", ADUsername="COMPANY\\dph2", FullName="Plant Head Two", PlantID=2)
    db_session.add_all([hod, manager, plant_head, other_plant_head])
    db_session.flush()

    reportee = Employee(
        EmployeeCode="D-EMP", ADUsername="COMPANY\\demp", FullName="Dept Employee",
        ManagerID=manager.EmployeeID, HODID=hod.EmployeeID, PlantID=1,
    )
    other_plant_employee = Employee(
        EmployeeCode="D-EMP2", ADUsername="COMPANY\\demp2", FullName="Other Plant Employee", PlantID=2,
    )
    db_session.add_all([reportee, other_plant_employee])
    db_session.flush()

    cycle = PerformanceCycle(CycleName="DASH-CYCLE")
    rating = RatingMaster(RatingLabel="Excellent", MinPercent=80, MaxPercent=100)
    db_session.add_all([cycle, rating])
    db_session.flush()

    performance = EmployeePerformance(
        EmployeeID=reportee.EmployeeID, CycleID=cycle.CycleID, Status="HOD_REVIEW",
    )
    other_performance = EmployeePerformance(
        EmployeeID=other_plant_employee.EmployeeID, CycleID=cycle.CycleID, Status="FINAL_APPROVED",
        FinalScorePct=90, FinalRatingID=rating.RatingID,
    )
    db_session.add_all([performance, other_performance])
    db_session.commit()

    return {
        "hod": hod, "manager": manager, "plant_head": plant_head, "other_plant_head": other_plant_head,
        "reportee": reportee, "other_plant_employee": other_plant_employee, "rating": rating,
    }


def test_apply_dashboard_scope_broad_roles_are_org_wide(db_session):
    _seed_org(db_session)
    query, scope = apply_dashboard_scope(db_session.query(EmployeePerformance), _Ctx(employee_id=999, role_codes=["HR"]))
    assert scope == SCOPE_ORG
    assert query.count() == 2


def test_apply_dashboard_scope_plant_head_is_plant_scoped(db_session):
    ids = _seed_org(db_session)
    query, scope = apply_dashboard_scope(
        db_session.query(EmployeePerformance), _Ctx(employee_id=ids["plant_head"].EmployeeID, role_codes=["PLANT_HEAD"]),
    )
    assert scope == SCOPE_PLANT
    records = query.all()
    assert len(records) == 1
    assert records[0].EmployeeID == ids["reportee"].EmployeeID


def test_apply_dashboard_scope_hod_is_dept_scoped(db_session):
    ids = _seed_org(db_session)
    query, scope = apply_dashboard_scope(
        db_session.query(EmployeePerformance), _Ctx(employee_id=ids["hod"].EmployeeID, role_codes=["HOD"]),
    )
    assert scope == SCOPE_DEPT
    assert query.count() == 1


def test_apply_dashboard_scope_manager_is_team_scoped(db_session):
    ids = _seed_org(db_session)
    query, scope = apply_dashboard_scope(
        db_session.query(EmployeePerformance), _Ctx(employee_id=ids["manager"].EmployeeID, role_codes=["MANAGER"]),
    )
    assert scope == SCOPE_TEAM
    assert query.count() == 1


def test_apply_dashboard_scope_employee_is_own_only(db_session):
    ids = _seed_org(db_session)
    query, scope = apply_dashboard_scope(
        db_session.query(EmployeePerformance), _Ctx(employee_id=ids["reportee"].EmployeeID, role_codes=["EMPLOYEE"]),
    )
    assert scope == SCOPE_OWN
    assert query.count() == 1


def test_summarize_computes_status_rating_and_overdue(db_session):
    ids = _seed_org(db_session)
    records = db_session.query(EmployeePerformance).all()
    data = summarize(db_session, records, ["HR"])
    assert data["total_appraisals"] == 2
    assert data["status_breakdown"] == {"HOD_REVIEW": 1, "FINAL_APPROVED": 1}
    assert data["rating_distribution"] == {"Excellent": 1}
    assert data["average_final_score_pct"] == 90.0


def test_summarize_pending_my_action_count_for_hod(db_session):
    ids = _seed_org(db_session)
    records = db_session.query(EmployeePerformance).all()
    data = summarize(db_session, records, ["HOD"])
    assert data["pending_my_action_count"] == 1  # the one HOD_REVIEW record


def test_summarize_pending_my_action_count_zero_for_hr_admin(db_session):
    ids = _seed_org(db_session)
    records = db_session.query(EmployeePerformance).all()
    data = summarize(db_session, records, ["HR_ADMIN"])
    assert data["pending_my_action_count"] == 0


def test_summarize_empty_records_returns_zeros_and_none_average(db_session):
    data = summarize(db_session, [], ["MANAGER"])
    assert data["total_appraisals"] == 0
    assert data["average_final_score_pct"] is None
    assert data["status_breakdown"] == {}
    assert data["rating_distribution"] == {}


def test_system_health_counts_are_technical_only(db_session):
    _seed_org(db_session)
    data = system_health(db_session)
    assert data["active_employees"] >= 6
    assert "FINAL_APPROVED" in data["appraisals_by_status"]
    assert data["total_audit_log_entries"] == 0
    assert data["most_recent_audit_at"] is None
    assert data["total_notifications_sent"] == 0

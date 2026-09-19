from dataclasses import dataclass

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import PerformanceCycle, RatingMaster
from app.models.performance_score import PerformanceScore
from app.models.workflow_history import WorkflowHistory
from app.services.performance_history_service import build_history, can_view_employee_history


@dataclass
class _Ctx:
    employee_id: int | None
    role_codes: list[str]


def _seed_org(db_session):
    manager = Employee(EmployeeCode="PH-MGR", ADUsername="COMPANY\\phmgr", FullName="Manager")
    hod = Employee(EmployeeCode="PH-HOD", ADUsername="COMPANY\\phhod", FullName="HOD")
    plant_head = Employee(EmployeeCode="PH-PLH", ADUsername="COMPANY\\phplh", FullName="Plant Head", PlantID=1)
    hr = Employee(EmployeeCode="PH-HR", ADUsername="COMPANY\\phhr", FullName="HR")
    db_session.add_all([manager, hod, plant_head, hr])
    db_session.flush()

    target = Employee(
        EmployeeCode="PH-TGT", ADUsername="COMPANY\\phtgt", FullName="Target Employee",
        ManagerID=manager.EmployeeID, HODID=hod.EmployeeID, PlantID=1,
    )
    outsider = Employee(EmployeeCode="PH-OUT", ADUsername="COMPANY\\phout", FullName="Outsider")
    other_plant_head = Employee(EmployeeCode="PH-OPLH", ADUsername="COMPANY\\phoplh", FullName="Other Plant Head", PlantID=2)
    db_session.add_all([target, outsider, other_plant_head])
    db_session.flush()
    db_session.commit()

    return {
        "manager": manager, "hod": hod, "plant_head": plant_head, "hr": hr,
        "target": target, "outsider": outsider, "other_plant_head": other_plant_head,
    }


def test_sys_admin_is_denied_outright(db_session):
    ids = _seed_org(db_session)
    ctx = _Ctx(employee_id=None, role_codes=["SYS_ADMIN"])
    assert can_view_employee_history(db_session, ctx, ids["target"]) is False


def test_hr_md_hr_admin_can_view_anyone(db_session):
    ids = _seed_org(db_session)
    for role in ("HR", "MD", "HR_ADMIN"):
        ctx = _Ctx(employee_id=999, role_codes=[role])
        assert can_view_employee_history(db_session, ctx, ids["target"]) is True


def test_plant_head_scoped_to_same_plant(db_session):
    ids = _seed_org(db_session)
    ctx = _Ctx(employee_id=ids["plant_head"].EmployeeID, role_codes=["PLANT_HEAD"])
    assert can_view_employee_history(db_session, ctx, ids["target"]) is True

    ctx_other = _Ctx(employee_id=ids["other_plant_head"].EmployeeID, role_codes=["PLANT_HEAD"])
    assert can_view_employee_history(db_session, ctx_other, ids["target"]) is False


def test_hod_scoped_to_own_reports(db_session):
    ids = _seed_org(db_session)
    ctx = _Ctx(employee_id=ids["hod"].EmployeeID, role_codes=["HOD"])
    assert can_view_employee_history(db_session, ctx, ids["target"]) is True

    ctx_outsider = _Ctx(employee_id=ids["outsider"].EmployeeID, role_codes=["HOD"])
    assert can_view_employee_history(db_session, ctx_outsider, ids["target"]) is False


def test_manager_scoped_to_own_reports(db_session):
    ids = _seed_org(db_session)
    ctx = _Ctx(employee_id=ids["manager"].EmployeeID, role_codes=["MANAGER"])
    assert can_view_employee_history(db_session, ctx, ids["target"]) is True

    ctx_outsider = _Ctx(employee_id=ids["outsider"].EmployeeID, role_codes=["MANAGER"])
    assert can_view_employee_history(db_session, ctx_outsider, ids["target"]) is False


def test_employee_can_only_view_self(db_session):
    ids = _seed_org(db_session)
    ctx_self = _Ctx(employee_id=ids["target"].EmployeeID, role_codes=["EMPLOYEE"])
    assert can_view_employee_history(db_session, ctx_self, ids["target"]) is True

    ctx_other = _Ctx(employee_id=ids["outsider"].EmployeeID, role_codes=["EMPLOYEE"])
    assert can_view_employee_history(db_session, ctx_other, ids["target"]) is False


def test_build_history_shape_ordering_and_grouping(db_session):
    ids = _seed_org(db_session)
    cycle1 = PerformanceCycle(CycleName="2024-25")
    cycle2 = PerformanceCycle(CycleName="2025-26")
    rating = RatingMaster(RatingLabel="Exceeds Expectations", MinPercent=80, MaxPercent=100)
    db_session.add_all([cycle1, cycle2, rating])
    db_session.flush()

    older = EmployeePerformance(
        EmployeeID=ids["target"].EmployeeID, CycleID=cycle1.CycleID, Status="MD_APPROVED",
        FinalScorePct=88.5, FinalRatingID=rating.RatingID, IsLocked=True,
    )
    newer = EmployeePerformance(
        EmployeeID=ids["target"].EmployeeID, CycleID=cycle2.CycleID, Status="SELF_ASSESSMENT",
    )
    db_session.add_all([older, newer])
    db_session.flush()
    # Force a deterministic CreatedAt ordering regardless of insert speed.
    import datetime
    older.CreatedAt = datetime.datetime(2025, 1, 1)
    newer.CreatedAt = datetime.datetime(2026, 1, 1)
    db_session.flush()

    db_session.add_all([
        PerformanceScore(PerformanceID=older.PerformanceID, ScoreType="KPI_WEIGHTED", ScoreValue=90.0),
        PerformanceScore(PerformanceID=older.PerformanceID, ScoreType="FINAL", ScoreValue=88.5),
    ])
    db_session.add(
        WorkflowHistory(
            PerformanceID=older.PerformanceID, FromStatus="DRAFT", ToStatus="SELF_ASSESSMENT", Comments="Started",
        )
    )
    db_session.commit()

    history = build_history(db_session, ids["target"].EmployeeID)
    assert len(history) == 2
    assert history[0]["performance_id"] == older.PerformanceID
    assert history[1]["performance_id"] == newer.PerformanceID

    first = history[0]
    assert first["cycle_name"] == "2024-25"
    assert first["status"] == "MD_APPROVED"
    assert first["final_score_pct"] == 88.5
    assert first["final_rating_label"] == "Exceeds Expectations"
    assert first["is_locked"] is True
    assert {s["score_type"] for s in first["score_breakdown"]} == {"KPI_WEIGHTED", "FINAL"}
    assert len(first["transitions"]) == 1
    assert first["transitions"][0]["to_status"] == "SELF_ASSESSMENT"

    second = history[1]
    assert second["final_score_pct"] is None
    assert second["final_rating_label"] is None
    assert second["score_breakdown"] == []
    assert second["transitions"] == []


def test_build_history_empty_for_employee_with_no_records(db_session):
    ids = _seed_org(db_session)
    assert build_history(db_session, ids["outsider"].EmployeeID) == []

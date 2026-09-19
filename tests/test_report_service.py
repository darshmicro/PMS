from dataclasses import dataclass

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import PerformanceCycle, RatingMaster
from app.services.report_service import (
    REPORT_CATALOG,
    build_appraisal_status_rows,
    list_available_reports,
    render_csv,
    render_pdf,
)


@dataclass
class _Ctx:
    employee_id: int | None
    role_codes: list[str]


def test_list_available_reports_filters_by_held_permissions():
    available = list_available_reports({"EMPLOYEE_MASTER.VIEW", "SELF_ASSESSMENT.VIEW"})
    keys = {entry["key"] for entry in available}
    assert "employee_master" in keys
    assert "self_assessment" in keys
    assert "pip" not in keys  # PIP.VIEW not held


def test_list_available_reports_empty_permissions_returns_nothing():
    assert list_available_reports(set()) == []


def test_report_catalog_entries_have_unique_keys():
    keys = [entry["key"] for entry in REPORT_CATALOG]
    assert len(keys) == len(set(keys))


def test_build_appraisal_status_rows_shapes_and_scopes(db_session):
    manager = Employee(EmployeeCode="RPT-MGR", ADUsername="COMPANY\\rptmgr", FullName="Report Manager")
    db_session.add(manager)
    db_session.flush()
    employee = Employee(
        EmployeeCode="RPT-EMP", ADUsername="COMPANY\\rptemp", FullName="Report Employee",
        ManagerID=manager.EmployeeID,
    )
    db_session.add(employee)
    db_session.flush()

    cycle = PerformanceCycle(CycleName="RPT-CYCLE")
    rating = RatingMaster(RatingLabel="Good", MinPercent=60, MaxPercent=79.99)
    db_session.add_all([cycle, rating])
    db_session.flush()

    performance = EmployeePerformance(
        EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="FINAL_APPROVED",
        FinalScorePct=70, FinalRatingID=rating.RatingID, IsLocked=True,
    )
    db_session.add(performance)
    db_session.commit()

    rows, scope = build_appraisal_status_rows(db_session, _Ctx(employee_id=manager.EmployeeID, role_codes=["MANAGER"]))
    assert scope == "TEAM"
    assert len(rows) == 1
    row = rows[0]
    assert row["employee_code"] == "RPT-EMP"
    assert row["final_rating_label"] == "Good"
    assert row["is_locked"] is True


def test_render_csv_produces_header_and_rows():
    content = render_csv(["A", "B"], [[1, "x"], [2, "y"]])
    text = content.decode("utf-8")
    assert "A,B" in text
    assert "1,x" in text
    assert "2,y" in text


def test_render_pdf_produces_nonempty_pdf_bytes():
    content = render_pdf(
        title="Test Report", headers=["A", "B"], rows=[[1, "x"]], generated_by="tester", context_label="unit test",
    )
    assert content.startswith(b"%PDF")
    assert len(content) > 100

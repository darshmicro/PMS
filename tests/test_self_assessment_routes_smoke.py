"""
End-to-end smoke tests for the M12 Self-Assessment routes, driven over
ASGI the same way as tests/test_routes_smoke.py and
tests/test_assignment_routes_smoke.py.
"""
import asyncio
import json as jsonlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers every model on Base.metadata
from app.core.dependencies import CurrentContext, get_current_context
from app.db.base import Base, get_db
from app.main import app as fastapi_app
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import KPAMaster, KPIMaster, KPIScoringRule, PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(EmployeeCode="EMP-SA-SMOKE", ADUsername="COMPANY\\sasmoke", FullName="SA Smoke Employee")
    other_employee = Employee(EmployeeCode="EMP-SA-OTHER", ADUsername="COMPANY\\saother", FullName="SA Other Employee")
    seed.add_all([employee, other_employee])
    seed.flush()

    cycle = PerformanceCycle(CycleName="SA-SMOKE-CYCLE")
    kpa = KPAMaster(KPACode="KPA-SA-SMOKE", KPAName="SA Smoke KPA", IsActive=True)
    seed.add_all([cycle, kpa])
    seed.flush()
    kpi_numeric = KPIMaster(KPICode="KPI-SA-NUM", KPIName="Numeric KPI", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    kpi_qual = KPIMaster(KPICode="KPI-SA-QUAL", KPIName="Qualitative KPI", KPAID=kpa.KPAID, MeasurementType="QUALITATIVE", IsActive=True)
    seed.add_all([kpi_numeric, kpi_qual])
    seed.flush()

    # Global default scoring bands covering the whole 0-100% range in two bands
    seed.add_all([
        KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=79.99, Score=3, IsActive=True),
        KPIScoringRule(KPIID=None, MinAchievement=80, MaxAchievement=200, Score=5, IsActive=True),
    ])

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="KPI_ASSIGNED")
    seed.add(performance)
    seed.flush()
    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    ek_numeric = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_numeric.KPIID, MeasurementType="PERCENTAGE",
        Weightage=60, Target=100.0,
    )
    ek_qual = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_qual.KPIID, MeasurementType="QUALITATIVE", Weightage=40,
    )
    seed.add_all([ek_numeric, ek_qual])
    seed.commit()

    ids = {
        "employee_id": employee.EmployeeID,
        "other_employee_id": other_employee.EmployeeID,
        "performance_id": performance.PerformanceID,
        "numeric_kpi_id": ek_numeric.EmployeeKPIID,
        "qual_kpi_id": ek_qual.EmployeeKPIID,
    }
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app, ids, SessionLocal
    fastapi_app.dependency_overrides.clear()


def _ctx_as(employee_id, role_codes=("EMPLOYEE",)):
    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\ctxuser", employee_id=employee_id,
            role_codes=list(role_codes), permission_codes={"SELF_ASSESSMENT.VIEW", "SELF_ASSESSMENT.EDIT"},
        )
    return override_ctx


async def _call(app, path, method="GET", json_body=None):
    status_code, headers_out, body = None, [], b""
    body_bytes = jsonlib.dumps(json_body).encode() if json_body is not None else b""

    async def receive():
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    async def send(message):
        nonlocal status_code, headers_out, body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            headers_out = message["headers"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")

    headers = [(b"client", b"testclient")]
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": headers, "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80), "scheme": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1",
    }
    await app(scope, receive, send)
    return status_code, dict(headers_out), body


def test_full_self_assessment_lifecycle(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    # A different employee cannot acknowledge someone else's assignment
    app.dependency_overrides[get_current_context] = _ctx_as(ids["other_employee_id"])
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))
    assert status == 404, body  # outside their view scope entirely (plain EMPLOYEE scope = self only)

    # The owning employee acknowledges
    app.dependency_overrides[get_current_context] = _ctx_as(ids["employee_id"])
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))
    assert status == 200, body
    assert jsonlib.loads(body)["status"] == "EMPLOYEE_ACKNOWLEDGED"

    # Acknowledging again is rejected (already past KPI_ASSIGNED)
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))
    assert status == 409, body

    # Update the numeric KPI's achievement - score is auto-derived (80% -> band gives Score=5)
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['numeric_kpi_id']}", "PUT",
        {"achievement": 80.0, "employee_comments": "Hit target"},
    ))
    assert status == 200, body
    updated = jsonlib.loads(body)
    assert updated["achievement_pct"] == 80.0
    assert updated["self_score"] == 5

    # Status auto-advanced from EMPLOYEE_ACKNOWLEDGED to SELF_ASSESSMENT after the first edit
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}", "GET"))
    assert jsonlib.loads(body)["status"] == "SELF_ASSESSMENT"

    # Submitting now fails - the qualitative KPI has no self score yet
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/submit", "POST"))
    assert status == 400, body
    assert "Qualitative KPI" in jsonlib.loads(body)["detail"]

    # Supply a direct self score for the qualitative KPI (no achievement % applies)
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['qual_kpi_id']}", "PUT",
        {"achievement": 1, "self_score": 4, "employee_comments": "Good collaboration"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["self_score"] == 4
    assert jsonlib.loads(body)["achievement_pct"] is None  # no target to divide against

    # An out-of-range self score is rejected
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['qual_kpi_id']}", "PUT", {"self_score": 9},
    ))
    assert status == 400, body

    # Submit now succeeds
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/submit", "POST"))
    assert status == 200, body
    submitted = jsonlib.loads(body)
    assert submitted["status"] == "MANAGER_REVIEW"
    assert all(k["status"] == "SUBMITTED" for k in submitted["kpis"])

    # Post-submission edits are blocked
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['numeric_kpi_id']}", "PUT", {"achievement": 50.0},
    ))
    assert status == 409, body

    # The stage-wise export route is reachable
    status, headers, body = asyncio.run(_call(app, f"/self-assessments/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_no_scoring_band_covers_achievement_is_rejected(client_env):
    app, ids, SessionLocal = client_env
    pid = ids["performance_id"]

    # Remove the seeded scoring rules so no band covers any achievement
    db = SessionLocal()
    db.query(KPIScoringRule).delete()
    db.commit()
    db.close()

    app.dependency_overrides[get_current_context] = _ctx_as(ids["employee_id"])
    asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))

    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['numeric_kpi_id']}", "PUT", {"achievement": 80.0},
    ))
    assert status == 400, body
    assert "No KPI Scoring Rule" in jsonlib.loads(body)["detail"]


def test_manager_can_view_but_not_edit_employees_self_assessment(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    # Set up: employee acknowledges first
    app.dependency_overrides[get_current_context] = _ctx_as(ids["employee_id"])
    asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))

    # A manager (broad enough to at least reach the record, simulate via HR role for scope) can view
    app.dependency_overrides[get_current_context] = _ctx_as(ids["other_employee_id"], role_codes=["HR"])
    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}", "GET"))
    assert status == 200, body

    # ...but cannot edit it, even though HR is within view-scope
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['numeric_kpi_id']}", "PUT", {"achievement": 80.0},
    ))
    assert status == 403, body

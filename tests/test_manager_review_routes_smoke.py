"""
End-to-end smoke tests for the M13 Manager Review routes, driven over
ASGI the same way as the prior modules' smoke tests.
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
from app.models.self_assessment import SelfAssessment


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    manager = Employee(EmployeeCode="EMP-MR-MGR", ADUsername="COMPANY\\mrmgr", FullName="MR Smoke Manager")
    other = Employee(EmployeeCode="EMP-MR-OTHER", ADUsername="COMPANY\\mrother", FullName="MR Other Manager")
    seed.add_all([manager, other])
    seed.flush()
    employee = Employee(
        EmployeeCode="EMP-MR-EMP", ADUsername="COMPANY\\mremp", FullName="MR Smoke Employee",
        ManagerID=manager.EmployeeID,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="MR-SMOKE-CYCLE")
    kpa = KPAMaster(KPACode="KPA-MR-SMOKE", KPAName="MR Smoke KPA", IsActive=True)
    seed.add_all([cycle, kpa])
    seed.flush()
    kpi1 = KPIMaster(KPICode="KPI-MR-1", KPIName="MR KPI One", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    kpi2 = KPIMaster(KPICode="KPI-MR-2", KPIName="MR KPI Two", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    seed.add_all([kpi1, kpi2])
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="MANAGER_REVIEW")
    seed.add(performance)
    seed.flush()
    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    ek1 = EmployeeKPI(EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi1.KPIID, MeasurementType="PERCENTAGE", Weightage=60, Target=100.0)
    ek2 = EmployeeKPI(EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi2.KPIID, MeasurementType="PERCENTAGE", Weightage=40, Target=100.0)
    seed.add_all([ek1, ek2])
    seed.flush()

    seed.add(KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=200, Score=4, IsActive=True))

    sa1 = SelfAssessment(EmployeeKPIID=ek1.EmployeeKPIID, Achievement=80, AchievementPct=80, SelfScore=3, Status="SUBMITTED")
    sa2 = SelfAssessment(EmployeeKPIID=ek2.EmployeeKPIID, Achievement=90, AchievementPct=90, SelfScore=4, Status="SUBMITTED")
    seed.add_all([sa1, sa2])
    seed.commit()

    ids = {
        "employee_id": employee.EmployeeID, "manager_id": manager.EmployeeID, "other_manager_id": other.EmployeeID,
        "performance_id": performance.PerformanceID, "kpi1_id": ek1.EmployeeKPIID, "kpi2_id": ek2.EmployeeKPIID,
    }
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    yield fastapi_app, ids
    fastapi_app.dependency_overrides.clear()


def _ctx_as(employee_id, role_codes=("MANAGER",)):
    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\ctxuser", employee_id=employee_id,
            role_codes=list(role_codes),
            permission_codes={
                "MANAGER_REVIEW.VIEW", "MANAGER_REVIEW.EDIT", "SELF_ASSESSMENT.VIEW", "SELF_ASSESSMENT.EDIT",
            },
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


def test_full_manager_review_lifecycle_submit(client_env):
    app, ids = client_env
    pid = ids["performance_id"]

    # A different manager cannot touch this employee's review at all
    app.dependency_overrides[get_current_context] = _ctx_as(ids["other_manager_id"])
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}", "GET"))
    assert status == 404, body  # outside their view scope (not their direct report)

    # The actual manager can view and edit
    app.dependency_overrides[get_current_context] = _ctx_as(ids["manager_id"])
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}", "GET"))
    assert status == 200, body

    # Matching the self score (3) requires no comments
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/kpis/{ids['kpi1_id']}", "PUT", {"manager_score": 3},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["manager_score"] == 3

    # Overriding KPI 2's score (self=4) without comments is rejected
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/kpis/{ids['kpi2_id']}", "PUT", {"manager_score": 2},
    ))
    assert status == 400, body

    # Submitting now fails - KPI 2 still has no manager score recorded
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}/submit", "POST"))
    assert status == 400, body

    # Overriding with comments succeeds
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/kpis/{ids['kpi2_id']}", "PUT",
        {"manager_score": 2, "manager_comments": "Missed a key deadline mid-cycle"},
    ))
    assert status == 200, body

    # Submit now succeeds -> HOD_REVIEW
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}/submit", "POST"))
    assert status == 200, body
    submitted = jsonlib.loads(body)
    assert submitted["status"] == "HOD_REVIEW"
    assert all(k["action"] == "SUBMIT" for k in submitted["kpis"])

    # Post-submission edits are blocked
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/kpis/{ids['kpi1_id']}", "PUT", {"manager_score": 4},
    ))
    assert status == 409, body

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/manager-reviews/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_return_to_employee_requires_reason_and_resets_stage(client_env):
    app, ids = client_env
    pid = ids["performance_id"]
    app.dependency_overrides[get_current_context] = _ctx_as(ids["manager_id"])

    # A manager can return early, having only partially reviewed - record a
    # score for one KPI (creating its Manager_Review row) and leave the
    # other completely untouched (no Manager_Review row exists for it yet).
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/kpis/{ids['kpi1_id']}", "PUT", {"manager_score": 3},
    ))
    assert status == 200, body

    # A reason is mandatory
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}/return", "POST", {"reason": "   "}))
    assert status == 400, body

    # With a reason, the record moves back to SELF_ASSESSMENT
    status, _, body = asyncio.run(_call(
        app, f"/manager-reviews/{pid}/return", "POST", {"reason": "Please add supporting evidence for KPI One"},
    ))
    assert status == 200, body
    returned = jsonlib.loads(body)
    assert returned["status"] == "SELF_ASSESSMENT"
    # Only the KPI that actually had a Manager_Review row gets stamped -
    # stamp_action only touches rows that exist, and the untouched KPI
    # (never PUT to) legitimately has none yet.
    kpi1_row = next(k for k in returned["kpis"] if k["employee_kpi_id"] == ids["kpi1_id"])
    kpi2_row = next(k for k in returned["kpis"] if k["employee_kpi_id"] == ids["kpi2_id"])
    assert kpi1_row["action"] == "RETURN"
    assert kpi2_row["action"] is None

    # The self-assessment side is now editable again by the employee (M12's
    # SELF_ASSESSMENT status was always in EDITABLE_STATUSES - confirms the
    # M12 forward note's resolution needed no code change there)
    app.dependency_overrides[get_current_context] = _ctx_as(ids["employee_id"], role_codes=("EMPLOYEE",))
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['kpi1_id']}", "PUT", {"achievement": 85.0},
    ))
    assert status == 200, body

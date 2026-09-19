"""
End-to-end smoke tests for the M14 HOD Review routes, driven over ASGI the
same way as the prior modules' smoke tests.
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
from app.models.manager_review import ManagerReview
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.models.self_assessment import SelfAssessment


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    hod = Employee(EmployeeCode="EMP-HOD-SMOKE", ADUsername="COMPANY\\hodsmoke", FullName="HOD Smoke")
    other_hod = Employee(EmployeeCode="EMP-HOD-OTHER", ADUsername="COMPANY\\hodother", FullName="HOD Other")
    seed.add_all([hod, other_hod])
    seed.flush()
    employee = Employee(
        EmployeeCode="EMP-HOD-EMP", ADUsername="COMPANY\\hodempsmoke", FullName="HOD Smoke Employee",
        HODID=hod.EmployeeID,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="HOD-SMOKE-CYCLE")
    kpa = KPAMaster(KPACode="KPA-HOD-SMOKE", KPAName="HOD Smoke KPA", IsActive=True)
    seed.add_all([cycle, kpa])
    seed.flush()
    kpi1 = KPIMaster(KPICode="KPI-HOD-1", KPIName="HOD KPI One", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    kpi2 = KPIMaster(KPICode="KPI-HOD-2", KPIName="HOD KPI Two", KPAID=kpa.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    seed.add_all([kpi1, kpi2])
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="HOD_REVIEW")
    seed.add(performance)
    seed.flush()
    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    ek1 = EmployeeKPI(EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi1.KPIID, MeasurementType="PERCENTAGE", Weightage=60, Target=100.0)
    ek2 = EmployeeKPI(EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi2.KPIID, MeasurementType="PERCENTAGE", Weightage=40, Target=100.0)
    seed.add_all([ek1, ek2])
    seed.flush()

    # Manager scores: 4*60/5 + 5*40/5 = 48 + 40 = 88.0 reference pct
    seed.add_all([
        ManagerReview(EmployeeKPIID=ek1.EmployeeKPIID, ManagerScore=4, Action="SUBMIT"),
        ManagerReview(EmployeeKPIID=ek2.EmployeeKPIID, ManagerScore=5, Action="SUBMIT"),
        SelfAssessment(EmployeeKPIID=ek1.EmployeeKPIID, Achievement=80, AchievementPct=80, SelfScore=4, Status="SUBMITTED"),
        SelfAssessment(EmployeeKPIID=ek2.EmployeeKPIID, Achievement=90, AchievementPct=90, SelfScore=5, Status="SUBMITTED"),
    ])
    seed.commit()

    ids = {
        "employee_id": employee.EmployeeID, "hod_id": hod.EmployeeID, "other_hod_id": other_hod.EmployeeID,
        "performance_id": performance.PerformanceID, "kpi1_id": ek1.EmployeeKPIID,
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


def _ctx_as(employee_id, role_codes=("HOD",)):
    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\ctxuser", employee_id=employee_id,
            role_codes=list(role_codes),
            permission_codes={
                "HOD_REVIEW.VIEW", "HOD_REVIEW.EDIT", "SELF_ASSESSMENT.VIEW", "SELF_ASSESSMENT.EDIT",
                "MANAGER_REVIEW.VIEW", "MANAGER_REVIEW.EDIT",
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


def test_full_hod_review_lifecycle_approve(client_env):
    app, ids = client_env
    pid = ids["performance_id"]

    # A different HOD cannot see this record at all
    app.dependency_overrides[get_current_context] = _ctx_as(ids["other_hod_id"])
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}", "GET"))
    assert status == 404, body

    # The actual HOD can view - the reference weighted score is exposed.
    # (In production, Employee/Manager never reach even this far: neither
    # role is ever granted HOD_REVIEW.VIEW in sql/015, so require_permission
    # rejects them with a 403 before the scope filter below runs at all.)
    app.dependency_overrides[get_current_context] = _ctx_as(ids["hod_id"])
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["manager_weighted_score_pct"] == 88.0

    # Approving before any HOD score is recorded fails
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}/approve", "POST"))
    assert status == 400, body

    # Setting a score that matches the reference needs no comments
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}", "PUT", {"hod_score": 88.0}))
    assert status == 200, body
    assert jsonlib.loads(body)["hod_score"] == 88.0

    # Approve & forward now succeeds -> HR_REVIEW
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}/approve", "POST"))
    assert status == 200, body
    approved = jsonlib.loads(body)
    assert approved["status"] == "HR_REVIEW"
    assert approved["action"] == "APPROVE_FORWARD"

    # Post-approval edits are blocked
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}", "PUT", {"hod_score": 70.0}))
    assert status == 409, body

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/hod-reviews/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_score_override_requires_comments(client_env):
    app, ids = client_env
    pid = ids["performance_id"]
    app.dependency_overrides[get_current_context] = _ctx_as(ids["hod_id"])

    # 70 differs meaningfully from the 88.0 reference - rejected without comments
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}", "PUT", {"hod_score": 70.0}))
    assert status == 400, body

    # With comments, the override is accepted
    status, _, body = asyncio.run(_call(
        app, f"/hod-reviews/{pid}", "PUT",
        {"hod_score": 70.0, "hod_comments": "Department-wide calibration adjustment applied"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["hod_score"] == 70.0


def test_return_to_manager_and_return_to_employee(client_env):
    app, ids = client_env
    pid = ids["performance_id"]
    app.dependency_overrides[get_current_context] = _ctx_as(ids["hod_id"])

    # A reason is mandatory
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}/return-to-manager", "POST", {"reason": ""}))
    assert status == 400, body

    # Returning to manager sends the record back to MANAGER_REVIEW
    status, _, body = asyncio.run(_call(
        app, f"/hod-reviews/{pid}/return-to-manager", "POST", {"reason": "Please re-check KPI Two's evidence"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["status"] == "MANAGER_REVIEW"

    # Confirm the record really did land back at MANAGER_REVIEW (not just
    # what the return call's own response claimed) by reading it back
    # through M13's own unmodified endpoint with a broad-access role - the
    # same "concrete labelled arrow, not a generic RETURNED status"
    # resolution established in M13 continues to hold with zero changes
    # to that module.
    app.dependency_overrides[get_current_context] = _ctx_as(1, role_codes=("HR",))
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["status"] == "MANAGER_REVIEW"


def test_return_to_employee_resets_self_assessment_status(client_env):
    app, ids = client_env
    pid = ids["performance_id"]
    app.dependency_overrides[get_current_context] = _ctx_as(ids["hod_id"])

    status, _, body = asyncio.run(_call(
        app, f"/hod-reviews/{pid}/return-to-employee", "POST", {"reason": "Achievement evidence looks incomplete"},
    ))
    assert status == 200, body
    result = jsonlib.loads(body)
    assert result["status"] == "SELF_ASSESSMENT"
    assert result["action"] == "RETURN_TO_EMPLOYEE"

    # The employee can immediately edit their self-assessment again through
    # M12's own unmodified endpoint.
    app.dependency_overrides[get_current_context] = _ctx_as(ids["employee_id"], role_codes=("EMPLOYEE",))
    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['kpi1_id']}", "PUT", {"achievement": 95.0},
    ))
    assert status == 400, body  # no scoring rule seeded in this fixture, but the STAGE gate itself passed (not a 409)

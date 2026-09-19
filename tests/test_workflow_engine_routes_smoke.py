"""
End-to-end smoke tests for M19: the stage-window gate actually blocking a
real transition endpoint when called before the cycle's configured
window opens, and the workflow status/history endpoint reflecting real
transitions recorded by other modules' own routers.
"""
import asyncio
import json as jsonlib
from datetime import date, timedelta

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
from app.models.hr_review import HRReview
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(
        EmployeeCode="EMP-WE-SMOKE", ADUsername="COMPANY\\wesmoke", FullName="Workflow Engine Smoke Employee",
        ManagerID=999,  # matches the acting Manager's employee_id in this fixture's default context
    )
    seed.add(employee)
    seed.flush()

    future_start = date.today() + timedelta(days=30)
    cycle = PerformanceCycle(
        CycleName="WE-SMOKE-CYCLE", ManagerReviewStart=future_start, ManagerReviewEnd=future_start + timedelta(days=30),
    )
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="MANAGER_REVIEW")
    seed.add(performance)
    seed.flush()

    kpa_master = KPAMaster(KPACode="KPA-WE-SMOKE", KPAName="Quality")
    seed.add(kpa_master)
    seed.flush()
    kpi_master = KPIMaster(KPICode="KPI-WE-SMOKE", KPIName="Defect Rate", KPAID=kpa_master.KPAID, MeasurementType="PERCENTAGE")
    seed.add(kpi_master)
    seed.flush()
    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa_master.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    seed.add(EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_master.KPIID, MeasurementType="PERCENTAGE", Weightage=100,
    ))
    seed.commit()

    ids = {"performance_id": performance.PerformanceID}
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(role_codes, permission_codes):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\weuser", employee_id=999, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["MANAGER"], {"MANAGER_REVIEW.VIEW", "MANAGER_REVIEW.EDIT", "WORKFLOW_ENGINE.VIEW"},
    )
    yield fastapi_app, ids, SessionLocal, _ctx_as
    fastapi_app.dependency_overrides.clear()


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


def test_stage_window_gate_blocks_action_before_cycle_opens(client_env):
    app, ids, _, _ = client_env
    pid = ids["performance_id"]

    # ManagerReviewStart is 30 days in the future - submit should be blocked
    status, _, body = asyncio.run(_call(app, f"/manager-reviews/{pid}/submit", "POST"))
    assert status == 409, body
    assert "does not open until" in jsonlib.loads(body)["detail"]


def test_workflow_status_endpoint_reflects_real_transition(client_env):
    app, ids, SessionLocal, ctx_as = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/workflow-engine/{pid}/status", "GET"))
    assert status == 200, body
    initial = jsonlib.loads(body)
    assert initial["current_status"] == "MANAGER_REVIEW"
    assert initial["next_forward_stages"] == ["HOD_REVIEW"]
    assert initial["next_return_stages"] == ["SELF_ASSESSMENT"]
    assert initial["window_start"] is not None
    assert initial["history"] == []

    # HOD Review has no configured window on this fixture's cycle, so its
    # own approve endpoint isn't blocked by the gate proven above - fast
    # forward the record there directly (bypassing the gated Manager
    # Review stage) and drive a real transition through it, to confirm
    # record_transition() wrote a row that shows up through this same
    # status endpoint.
    from app.models.hod_review import HODReview

    db = SessionLocal()
    performance = db.get(EmployeePerformance, pid)
    performance.Status = "HOD_REVIEW"
    employee = db.get(Employee, performance.EmployeeID)
    employee.HODID = 42  # matches the acting HOD's employee_id set below
    db.add(HODReview(PerformanceID=pid, HODScore=80.0))
    db.commit()
    db.close()

    def _hod_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\weuser", employee_id=42, role_codes=["HOD"],
            permission_codes={"HOD_REVIEW.VIEW", "HOD_REVIEW.EDIT", "WORKFLOW_ENGINE.VIEW"},
        )

    fastapi_app.dependency_overrides[get_current_context] = _hod_ctx
    status, _, body = asyncio.run(_call(app, f"/hod-reviews/{pid}/approve", "POST"))
    assert status == 200, body

    status, _, body = asyncio.run(_call(app, f"/workflow-engine/{pid}/status", "GET"))
    assert status == 200, body
    after = jsonlib.loads(body)
    assert after["current_status"] == "HR_REVIEW"
    assert len(after["history"]) == 1
    assert after["history"][0]["from_status"] == "HOD_REVIEW"
    assert after["history"][0]["to_status"] == "HR_REVIEW"

"""
End-to-end smoke tests for the M16 Plant Head Approval routes, driven over
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
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hr_review import HRReview
from app.models.performance_masters import PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    plant_head = Employee(
        EmployeeCode="EMP-PH-SMOKE", ADUsername="COMPANY\\phsmoke", FullName="Plant Head Smoke", PlantID=1,
    )
    seed.add(plant_head)
    seed.flush()

    employee = Employee(
        EmployeeCode="EMP-PHA-SMOKE", ADUsername="COMPANY\\phasmoke", FullName="Plant Head Approval Smoke Employee",
        PlantID=1,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="PHA-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(
        EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="PLANT_HEAD_APPROVAL",
    )
    seed.add(performance)
    seed.flush()
    seed.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=85.0))
    seed.commit()

    ids = {"performance_id": performance.PerformanceID, "plant_head_employee_id": plant_head.EmployeeID}
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(employee_id, role_codes):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\phuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes={"PLANT_HEAD_APPROVAL.VIEW", "PLANT_HEAD_APPROVAL.EDIT"},
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(ids["plant_head_employee_id"], ["PLANT_HEAD"])
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


def test_full_plant_head_approval_lifecycle(client_env):
    app, ids, _, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["hr_score"] == 85.0

    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/approve", "POST", {"comments": "Looks good"}))
    assert status == 200, body
    approved = jsonlib.loads(body)
    assert approved["status"] == "MD_APPROVAL"
    assert approved["decision"] == "APPROVE"

    # Post-approval actions are blocked (record has moved on)
    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/approve", "POST", {}))
    assert status == 409, body

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_return_requires_comments_and_sends_back_to_hr(client_env):
    app, ids, _, _ = client_env
    pid = ids["performance_id"]

    # No comments -> rejected
    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/return", "POST", {}))
    assert status == 400, body

    # With comments -> succeeds, back to HR_REVIEW
    status, _, body = asyncio.run(
        _call(app, f"/plant-head-approvals/{pid}/return", "POST", {"comments": "Recalibrate against peer group"})
    )
    assert status == 200, body
    returned = jsonlib.loads(body)
    assert returned["status"] == "HR_REVIEW"
    assert returned["decision"] == "RETURN"


def test_only_the_matching_plant_head_can_act(client_env):
    app, ids, _, ctx_as = client_env
    pid = ids["performance_id"]

    # A different plant head (no matching Employee row / different plant)
    # sees a 404 via _apply_scope before any ownership check even runs -
    # same pattern as M14's manager/HOD scoping tests.
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(999999, ["PLANT_HEAD"])
    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/approve", "POST", {}))
    assert status == 404, body


def test_approve_fails_without_a_completed_hr_review(client_env):
    app, ids, SessionLocal, _ = client_env
    pid = ids["performance_id"]

    db = SessionLocal()
    db.query(HRReview).filter(HRReview.PerformanceID == pid).delete()
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(app, f"/plant-head-approvals/{pid}/approve", "POST", {}))
    assert status == 409, body
    assert "HR Review" in jsonlib.loads(body)["detail"]

    # A nonexistent performance record is a plain 404
    status, _, body = asyncio.run(_call(app, "/plant-head-approvals/999999", "GET"))
    assert status == 404, body

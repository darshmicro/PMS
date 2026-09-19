"""
End-to-end smoke tests for the M17 MD Approval routes, driven over ASGI
the same way as the prior modules' smoke tests.
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
from app.models.performance_masters import PerformanceCycle, RatingMaster


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(EmployeeCode="EMP-MDA-SMOKE", ADUsername="COMPANY\\mdasmoke", FullName="MD Approval Smoke Employee")
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="MDA-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="MD_APPROVAL")
    seed.add(performance)
    seed.flush()
    seed.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=90.0))
    # M18's Scoring Engine now runs inside /approve, so a Rating Master
    # band covering the HR score must exist for approval to succeed.
    seed.add(RatingMaster(RatingLabel="Excellent", MinPercent=80, MaxPercent=100))
    seed.commit()

    ids = {"performance_id": performance.PerformanceID}
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\mduser", employee_id=999, role_codes=["MD"],
            permission_codes={"MD_APPROVAL.VIEW", "MD_APPROVAL.EDIT"},
        )

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = override_ctx
    yield fastapi_app, ids, SessionLocal
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


def test_full_md_approval_lifecycle_locks_the_record(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}", "GET"))
    assert status == 200, body
    got = jsonlib.loads(body)
    assert got["hr_score"] == 90.0
    assert got["is_locked"] is False

    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/approve", "POST", {"comments": "Approved"}))
    assert status == 200, body
    approved = jsonlib.loads(body)
    assert approved["status"] == "FINAL_APPROVED"
    assert approved["is_locked"] is True
    assert approved["decision"] == "APPROVE"

    # Post-approval actions are blocked - the record is locked now
    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/approve", "POST", {}))
    assert status == 409, body
    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/return", "POST", {"comments": "too late"}))
    assert status == 409, body

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/md-approvals/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_return_requires_comments_and_sends_back_to_plant_head(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    # No comments -> rejected
    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/return", "POST", {}))
    assert status == 400, body

    # With comments -> succeeds, back to PLANT_HEAD_APPROVAL, not locked
    status, _, body = asyncio.run(
        _call(app, f"/md-approvals/{pid}/return", "POST", {"comments": "Please double-check the calibration note"})
    )
    assert status == 200, body
    returned = jsonlib.loads(body)
    assert returned["status"] == "PLANT_HEAD_APPROVAL"
    assert returned["decision"] == "RETURN"
    assert returned["is_locked"] is False


def test_approve_fails_without_a_completed_hr_review(client_env):
    app, ids, SessionLocal = client_env
    pid = ids["performance_id"]

    db = SessionLocal()
    db.query(HRReview).filter(HRReview.PerformanceID == pid).delete()
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/approve", "POST", {}))
    assert status == 409, body
    assert "HR Review" in jsonlib.loads(body)["detail"]

    # A nonexistent performance record is a plain 404
    status, _, body = asyncio.run(_call(app, "/md-approvals/999999", "GET"))
    assert status == 404, body

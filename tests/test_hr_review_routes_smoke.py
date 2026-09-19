"""
End-to-end smoke tests for the M15 HR Review routes, driven over ASGI the
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
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hod_review import HODReview
from app.models.performance_masters import PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(EmployeeCode="EMP-HRR-SMOKE", ADUsername="COMPANY\\hrrsmoke", FullName="HR Review Smoke Employee")
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="HRR-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="HR_REVIEW")
    seed.add(performance)
    seed.flush()
    seed.add(HODReview(PerformanceID=performance.PerformanceID, HODScore=80.0, Action="APPROVE_FORWARD"))
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
            user_id=1, ad_username="COMPANY\\hruser", employee_id=999, role_codes=["HR"],
            permission_codes={"HR_REVIEW.VIEW", "HR_REVIEW.EDIT"},
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


def test_full_hr_review_lifecycle_with_no_adjustment(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["hod_score"] == 80.0

    # Completing before touching the record at all fails - no HRScore yet
    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}/complete", "POST"))
    assert status == 400, body

    # A PUT with only comments (no adjustment) auto-derives HRScore = HODScore + 0
    status, _, body = asyncio.run(_call(
        app, f"/hr-reviews/{pid}", "PUT", {"hr_comments": "Consistent with department norms"},
    ))
    assert status == 200, body
    updated = jsonlib.loads(body)
    assert updated["calibration_adjustment"] == 0
    assert updated["hr_score"] == 80.0

    # Complete now succeeds -> PLANT_HEAD_APPROVAL
    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}/complete", "POST"))
    assert status == 200, body
    completed = jsonlib.loads(body)
    assert completed["status"] == "PLANT_HEAD_APPROVAL"

    # Post-completion edits are blocked
    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}", "PUT", {"hr_comments": "too late"}))
    assert status == 409, body

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/hr-reviews/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_nonzero_adjustment_requires_reason_and_recomputes_score(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    # A nonzero adjustment without a reason is rejected
    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}", "PUT", {"calibration_adjustment": 5.0}))
    assert status == 400, body

    # With a reason, it succeeds and HRScore reflects HODScore + adjustment
    status, _, body = asyncio.run(_call(
        app, f"/hr-reviews/{pid}", "PUT",
        {"calibration_adjustment": 5.0, "adjustment_reason": "Cross-department calibration - dept scored high overall"},
    ))
    assert status == 200, body
    updated = jsonlib.loads(body)
    assert updated["calibration_adjustment"] == 5.0
    assert updated["hr_score"] == 85.0

    status, _, body = asyncio.run(_call(app, f"/hr-reviews/{pid}/complete", "POST"))
    assert status == 200, body
    assert jsonlib.loads(body)["status"] == "PLANT_HEAD_APPROVAL"


def test_adjustment_pushing_score_out_of_bounds_is_rejected(client_env):
    app, ids, _ = client_env
    pid = ids["performance_id"]

    # HOD score is 80.0; an adjustment of +30 would push HRScore to 110, over 100
    status, _, body = asyncio.run(_call(
        app, f"/hr-reviews/{pid}", "PUT",
        {"calibration_adjustment": 30.0, "adjustment_reason": "Too generous an adjustment"},
    ))
    assert status == 400, body
    assert "0-100" in jsonlib.loads(body)["detail"]


def test_complete_fails_without_a_completed_hod_review(client_env):
    app, ids, SessionLocal = client_env
    pid = ids["performance_id"]

    # Remove the HOD score prerequisite entirely to simulate a data-integrity
    # gap (a record should never legitimately reach HR_REVIEW without one).
    db = SessionLocal()
    db.query(HODReview).filter(HODReview.PerformanceID == pid).delete()
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(
        app, f"/hr-reviews/{pid}", "PUT", {"hr_comments": "shouldn't get this far"},
    ))
    assert status == 409, body
    assert "HOD Review" in jsonlib.loads(body)["detail"]

    # A nonexistent performance record is a plain 404
    status, _, body = asyncio.run(_call(app, "/hr-reviews/999999", "GET"))
    assert status == 404, body

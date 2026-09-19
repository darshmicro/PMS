"""
End-to-end smoke tests for the M20 Development Plan routes, driven over
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
from app.models.performance_masters import PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(
        EmployeeCode="EMP-DP-SMOKE", ADUsername="COMPANY\\dpsmoke", FullName="Development Plan Smoke Employee",
        ManagerID=999,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="DP-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="HOD_REVIEW")
    seed.add(performance)
    seed.commit()

    ids = {"performance_id": performance.PerformanceID, "employee_id": employee.EmployeeID}
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(role_codes, permission_codes, employee_id=999):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\dpuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["MANAGER"], {"DEVELOPMENT_PLAN.VIEW", "DEVELOPMENT_PLAN.EDIT"},
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


def test_full_development_plan_lifecycle(client_env):
    app, ids, _, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(
        app, "/development-plans", "POST",
        {"performance_id": pid, "development_area": "Communication", "skill_gap": "Public speaking",
         "training_required": "Toastmasters course", "target_date": "2026-12-31"},
    ))
    assert status == 201, body
    created = jsonlib.loads(body)
    assert created["completion_status"] == "PENDING"
    dev_plan_id = created["dev_plan_id"]

    status, _, body = asyncio.run(_call(app, f"/development-plans/{dev_plan_id}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["skill_gap"] == "Public speaking"

    status, _, body = asyncio.run(_call(
        app, f"/development-plans/{dev_plan_id}", "PUT", {"completion_status": "IN_PROGRESS"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["completion_status"] == "IN_PROGRESS"

    # Invalid completion status is rejected
    status, _, body = asyncio.run(_call(
        app, f"/development-plans/{dev_plan_id}", "PUT", {"completion_status": "DONE"},
    ))
    assert status == 400, body

    status, _, body = asyncio.run(_call(app, "/development-plans", "GET", None))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 1

    status, headers, body = asyncio.run(_call(app, f"/development-plans/performance/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_editing_survives_appraisal_lock(client_env):
    """A development plan's tracked lifetime outlives the appraisal - see
    the model's own docstring. Locking Employee_Performance must not
    block updates here, unlike every review/approval stage's own gate."""
    app, ids, SessionLocal, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(
        app, "/development-plans", "POST", {"performance_id": pid, "skill_gap": "Leadership"},
    ))
    assert status == 201, body
    dev_plan_id = jsonlib.loads(body)["dev_plan_id"]

    db = SessionLocal()
    performance = db.get(EmployeePerformance, pid)
    performance.Status = "FINAL_APPROVED"
    performance.IsLocked = True
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(
        app, f"/development-plans/{dev_plan_id}", "PUT", {"completion_status": "COMPLETED"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["completion_status"] == "COMPLETED"


def test_employee_can_view_but_not_edit_own_plan(client_env):
    app, ids, _, ctx_as = client_env
    pid = ids["performance_id"]
    employee_id = ids["employee_id"]

    status, _, body = asyncio.run(_call(
        app, "/development-plans", "POST", {"performance_id": pid, "skill_gap": "Time management"},
    ))
    assert status == 201, body

    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["EMPLOYEE"], {"DEVELOPMENT_PLAN.VIEW"}, employee_id=employee_id,
    )
    status, _, body = asyncio.run(_call(app, "/development-plans", "GET"))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 1

    # No DEVELOPMENT_PLAN.EDIT permission -> 403
    status, _, body = asyncio.run(_call(
        app, "/development-plans", "POST", {"performance_id": pid, "skill_gap": "Should be blocked"},
    ))
    assert status == 403, body

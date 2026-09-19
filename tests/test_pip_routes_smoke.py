"""
End-to-end smoke tests for the M21 PIP routes, driven over ASGI the same
way as every prior module's smoke tests.
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
from app.models.employee import Employee


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    subject = Employee(EmployeeCode="EMP-PIP-SUBJECT", ADUsername="COMPANY\\pipsubject", FullName="PIP Subject Employee")
    seed.add(subject)
    seed.flush()

    manager = Employee(
        EmployeeCode="EMP-PIP-MGR", ADUsername="COMPANY\\pipmgr", FullName="PIP Assigned Manager", ManagerID=None,
    )
    seed.add(manager)
    seed.commit()

    ids = {"employee_id": subject.EmployeeID, "manager_id": manager.EmployeeID}
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
                user_id=1, ad_username="COMPANY\\pipuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["HR"], {"PIP.VIEW", "PIP.EDIT"},
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


def test_full_pip_lifecycle_create_edit_close(client_env):
    app, ids, _, _ = client_env
    employee_id = ids["employee_id"]
    manager_id = ids["manager_id"]

    status, _, body = asyncio.run(_call(
        app, "/pip", "POST",
        {"employee_id": employee_id, "performance_gap": "Missed deadlines", "manager_id": manager_id,
         "pip_start_date": "2026-01-01", "pip_end_date": "2026-03-31"},
    ))
    assert status == 201, body
    created = jsonlib.loads(body)
    assert created["outcome"] is None
    pip_id = created["pip_id"]

    status, _, body = asyncio.run(_call(app, f"/pip/{pip_id}", "GET"))
    assert status == 200, body
    assert jsonlib.loads(body)["performance_gap"] == "Missed deadlines"

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}", "PUT", {"action_plan": "Weekly 1:1s with manager"},
    ))
    assert status == 200, body
    assert jsonlib.loads(body)["action_plan"] == "Weekly 1:1s with manager"

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}/close", "POST", {"outcome": "SUCCESSFUL", "comments": "Targets met"},
    ))
    assert status == 200, body
    closed = jsonlib.loads(body)
    assert closed["outcome"] == "SUCCESSFUL"
    assert closed["comments"] == "Targets met"

    # Closed PIP rejects further edits and a second close with 409
    status, _, body = asyncio.run(_call(app, f"/pip/{pip_id}", "PUT", {"action_plan": "Should be blocked"}))
    assert status == 409, body

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}/close", "POST", {"outcome": "UNSUCCESSFUL"},
    ))
    assert status == 409, body

    status, headers, body = asyncio.run(_call(app, f"/pip/{pip_id}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_only_broad_access_roles_may_create_a_pip(client_env):
    app, ids, _, ctx_as = client_env
    employee_id = ids["employee_id"]
    manager_id = ids["manager_id"]

    # A Manager holds PIP.EDIT (to work assigned PIPs) but may not open a new one.
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["MANAGER"], {"PIP.VIEW", "PIP.EDIT"}, employee_id=manager_id,
    )
    status, _, body = asyncio.run(_call(
        app, "/pip", "POST", {"employee_id": employee_id, "manager_id": manager_id},
    ))
    assert status == 403, body


def test_assigned_manager_can_edit_and_close_own_pip_but_not_others(client_env):
    app, ids, _, ctx_as = client_env
    employee_id = ids["employee_id"]
    manager_id = ids["manager_id"]

    status, _, body = asyncio.run(_call(
        app, "/pip", "POST", {"employee_id": employee_id, "manager_id": manager_id},
    ))
    assert status == 201, body
    pip_id = jsonlib.loads(body)["pip_id"]

    # A second PIP assigned to a *different* manager (nobody, here - unassigned)
    status, _, body = asyncio.run(_call(app, "/pip", "POST", {"employee_id": employee_id}))
    assert status == 201, body
    other_pip_id = jsonlib.loads(body)["pip_id"]

    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["MANAGER"], {"PIP.VIEW", "PIP.EDIT"}, employee_id=manager_id,
    )

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}", "PUT", {"training": "Coaching sessions"},
    ))
    assert status == 200, body

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}/close", "POST", {"outcome": "EXTENDED"},
    ))
    assert status == 200, body

    # Not assigned to this manager -> 403 (scoped list means 404 on lookup, or 403 on ownership)
    status, _, body = asyncio.run(_call(
        app, f"/pip/{other_pip_id}", "PUT", {"training": "Should be blocked"},
    ))
    assert status in (403, 404), body


def test_employee_can_view_own_pip_but_not_edit(client_env):
    app, ids, _, ctx_as = client_env
    employee_id = ids["employee_id"]

    status, _, body = asyncio.run(_call(app, "/pip", "POST", {"employee_id": employee_id}))
    assert status == 201, body
    pip_id = jsonlib.loads(body)["pip_id"]

    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["EMPLOYEE"], {"PIP.VIEW"}, employee_id=employee_id,
    )

    status, _, body = asyncio.run(_call(app, f"/pip/{pip_id}", "GET"))
    assert status == 200, body

    status, _, body = asyncio.run(_call(app, "/pip", "GET"))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 1

    # No PIP.EDIT permission -> 403
    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}", "PUT", {"training": "Should be blocked"},
    ))
    assert status == 403, body


def test_invalid_outcome_on_close_is_rejected(client_env):
    app, ids, _, _ = client_env
    employee_id = ids["employee_id"]

    status, _, body = asyncio.run(_call(app, "/pip", "POST", {"employee_id": employee_id}))
    assert status == 201, body
    pip_id = jsonlib.loads(body)["pip_id"]

    status, _, body = asyncio.run(_call(
        app, f"/pip/{pip_id}/close", "POST", {"outcome": "STILL_TRYING"},
    ))
    assert status == 400, body

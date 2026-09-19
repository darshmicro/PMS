"""
End-to-end smoke tests for the M26 Audit Log routes, driven over ASGI the
same way as every prior module's smoke tests.
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
from app.models.audit import AuditLog
from app.models.employee import Employee


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    hr = Employee(EmployeeCode="EMP-AUD-HR", ADUsername="COMPANY\\audhr", FullName="Audit HR", DepartmentID=1)
    same_dept = Employee(EmployeeCode="EMP-AUD-SD", ADUsername="COMPANY\\audsd", FullName="Same Dept Employee", DepartmentID=1)
    other_dept = Employee(EmployeeCode="EMP-AUD-OD", ADUsername="COMPANY\\audod", FullName="Other Dept Employee", DepartmentID=2)
    seed.add_all([hr, same_dept, other_dept])
    seed.flush()

    seed.add_all([
        AuditLog(Action="EDIT", Module="EMPLOYEE", EmployeeID=same_dept.EmployeeID, ADUsername="COMPANY\\audsd"),
        AuditLog(Action="EDIT", Module="EMPLOYEE", EmployeeID=other_dept.EmployeeID, ADUsername="COMPANY\\audod"),
    ])
    seed.commit()

    ids = {"hr_id": hr.EmployeeID, "same_dept_id": same_dept.EmployeeID, "other_dept_id": other_dept.EmployeeID}
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
                user_id=1, ad_username="COMPANY\\audituser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["HR"], {"AUDIT_LOG.VIEW"}, employee_id=ids["hr_id"],
    )
    yield fastapi_app, ids, SessionLocal, _ctx_as
    fastapi_app.dependency_overrides.clear()


async def _call(app, path, method="GET"):
    status_code, headers_out, body = None, [], b""

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal status_code, headers_out, body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            headers_out = message["headers"]
        elif message["type"] == "http.response.body":
            body += message.get("body", b"")

    path_only, _, query_string = path.partition("?")
    scope = {
        "type": "http", "method": method, "path": path_only, "raw_path": path_only.encode(),
        "query_string": query_string.encode(), "headers": [(b"client", b"testclient")], "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80), "scheme": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1",
    }
    await app(scope, receive, send)
    return status_code, dict(headers_out), body


def test_hr_sees_only_own_department(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, "/audit-log"))
    assert status == 200, body
    rows = jsonlib.loads(body)
    assert len(rows) == 1
    assert rows[0]["employee_id"] == ids["same_dept_id"]


def test_md_sees_everything(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["MD"], {"AUDIT_LOG.VIEW"})
    status, _, body = asyncio.run(_call(app, "/audit-log"))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 2


def test_employee_manager_hod_are_forbidden(client_env):
    app, ids, _, ctx_as = client_env
    for role in ("EMPLOYEE", "MANAGER", "HOD"):
        fastapi_app.dependency_overrides[get_current_context] = ctx_as([role], set())
        status, _, body = asyncio.run(_call(app, "/audit-log"))
        assert status == 403, (role, body)


def test_get_single_entry_respects_scope(client_env):
    app, ids, SessionLocal, _ = client_env
    db = SessionLocal()
    other_entry = db.query(AuditLog).filter(AuditLog.EmployeeID == ids["other_dept_id"]).one()
    other_entry_id = other_entry.AuditID
    same_entry = db.query(AuditLog).filter(AuditLog.EmployeeID == ids["same_dept_id"]).one()
    same_entry_id = same_entry.AuditID
    db.close()

    status, _, body = asyncio.run(_call(app, f"/audit-log/{same_entry_id}"))
    assert status == 200, body

    status, _, body = asyncio.run(_call(app, f"/audit-log/{other_entry_id}"))
    assert status == 404, body


def test_filter_by_module_and_employee(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, f"/audit-log?employee_id={ids['same_dept_id']}"))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 1

    status, _, body = asyncio.run(_call(app, "/audit-log?module=NONEXISTENT"))
    assert status == 200, body
    assert jsonlib.loads(body) == []


def test_export_is_reachable(client_env):
    app, ids, _, _ = client_env
    status, headers, body = asyncio.run(_call(app, "/audit-log/export/list"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

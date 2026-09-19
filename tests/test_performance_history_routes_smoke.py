"""
End-to-end smoke tests for the M27 Performance History routes, driven
over ASGI the same way as every prior module's smoke tests. Uses the
query-string-splitting _call() harness from the start (see M22/M25's
history of this same bug for why).
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
from app.models.performance_masters import PerformanceCycle, RatingMaster


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    manager = Employee(EmployeeCode="PHR-MGR", ADUsername="COMPANY\\phrmgr", FullName="Manager")
    target = Employee(EmployeeCode="PHR-TGT", ADUsername="COMPANY\\phrtgt", FullName="Target")
    outsider = Employee(EmployeeCode="PHR-OUT", ADUsername="COMPANY\\phrout", FullName="Outsider")
    seed.add_all([manager, target, outsider])
    seed.flush()
    target.ManagerID = manager.EmployeeID
    seed.flush()

    cycle = PerformanceCycle(CycleName="2026-27")
    rating = RatingMaster(RatingLabel="Meets Expectations", MinPercent=60, MaxPercent=79.99)
    seed.add_all([cycle, rating])
    seed.flush()

    record = EmployeePerformance(
        EmployeeID=target.EmployeeID, CycleID=cycle.CycleID, Status="MD_APPROVED",
        FinalScorePct=70.0, FinalRatingID=rating.RatingID, IsLocked=True,
    )
    seed.add(record)
    seed.commit()

    ids = {
        "manager_id": manager.EmployeeID, "target_id": target.EmployeeID, "outsider_id": outsider.EmployeeID,
    }
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(role_codes, employee_id):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\phruser", employee_id=employee_id, role_codes=role_codes,
                permission_codes={"PERFORMANCE_HISTORY.VIEW"},
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(["EMPLOYEE"], ids["target_id"])
    yield fastapi_app, ids, _ctx_as
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


def test_me_returns_own_history(client_env):
    app, ids, _ = client_env
    status, _, body = asyncio.run(_call(app, "/performance-history/me"))
    assert status == 200, body
    payload = jsonlib.loads(body)
    assert payload["employee_id"] == ids["target_id"]
    assert len(payload["records"]) == 1
    assert payload["records"][0]["final_rating_label"] == "Meets Expectations"


def test_manager_can_view_own_report(client_env):
    app, ids, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["MANAGER"], ids["manager_id"])
    status, _, body = asyncio.run(_call(app, f"/performance-history/{ids['target_id']}"))
    assert status == 200, body
    assert len(jsonlib.loads(body)["records"]) == 1


def test_outsider_is_forbidden(client_env):
    app, ids, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["EMPLOYEE"], ids["outsider_id"])
    status, _, body = asyncio.run(_call(app, f"/performance-history/{ids['target_id']}"))
    assert status == 403, body


def test_unknown_employee_is_not_found(client_env):
    app, ids, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["MD"], 999)
    status, _, body = asyncio.run(_call(app, "/performance-history/999999"))
    assert status == 404, body


def test_hr_md_can_view_anyone(client_env):
    app, ids, ctx_as = client_env
    for role in ("HR", "MD", "HR_ADMIN"):
        fastapi_app.dependency_overrides[get_current_context] = ctx_as([role], 999)
        status, _, body = asyncio.run(_call(app, f"/performance-history/{ids['target_id']}"))
        assert status == 200, (role, body)


def test_sys_admin_is_forbidden(client_env):
    app, ids, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["SYS_ADMIN"], None)
    status, _, body = asyncio.run(_call(app, f"/performance-history/{ids['target_id']}"))
    assert status == 403, body

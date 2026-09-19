"""
End-to-end smoke tests for the M25 Reports & Export Center routes, driven
over ASGI the same way as every prior module's smoke tests.
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
    manager = Employee(EmployeeCode="EMP-RPT-MGR", ADUsername="COMPANY\\rptmgr", FullName="Report Manager")
    seed.add(manager)
    seed.flush()

    employee = Employee(
        EmployeeCode="EMP-RPT-EMP", ADUsername="COMPANY\\rptemp", FullName="Report Employee",
        ManagerID=manager.EmployeeID,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="RPT-SMOKE-CYCLE")
    rating = RatingMaster(RatingLabel="Excellent", MinPercent=80, MaxPercent=100)
    seed.add_all([cycle, rating])
    seed.flush()

    seed.add(EmployeePerformance(
        EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="FINAL_APPROVED",
        FinalScorePct=85, FinalRatingID=rating.RatingID,
    ))
    seed.commit()

    ids = {"manager_id": manager.EmployeeID, "employee_id": employee.EmployeeID}
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
                user_id=1, ad_username="COMPANY\\rptuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["MANAGER"], {"REPORT.VIEW", "EMPLOYEE_MASTER.VIEW", "SELF_ASSESSMENT.VIEW"}, employee_id=ids["manager_id"],
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


def test_catalog_is_filtered_to_held_permissions(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, "/reports/catalog"))
    assert status == 200, body
    entries = jsonlib.loads(body)
    keys = {e["key"] for e in entries}
    assert "employee_master" in keys
    assert "self_assessment" in keys
    assert "pip" not in keys  # caller has no PIP.VIEW


def test_appraisal_status_report_json_is_team_scoped(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, "/reports/appraisal-status"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "TEAM"
    assert len(data["rows"]) == 1
    assert data["rows"][0]["employee_code"] == "EMP-RPT-EMP"
    assert data["rows"][0]["final_rating_label"] == "Excellent"


def test_appraisal_status_report_xlsx(client_env):
    app, ids, _, _ = client_env
    status, headers, body = asyncio.run(_call(app, "/reports/appraisal-status?format=xlsx"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_appraisal_status_report_csv(client_env):
    app, ids, _, _ = client_env
    status, headers, body = asyncio.run(_call(app, "/reports/appraisal-status?format=csv"))
    assert status == 200, body
    assert headers.get(b"content-type", b"").startswith(b"text/csv")
    assert b"EMP-RPT-EMP" in body


def test_appraisal_status_report_pdf(client_env):
    app, ids, _, _ = client_env
    status, headers, body = asyncio.run(_call(app, "/reports/appraisal-status?format=pdf"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/pdf"
    assert body.startswith(b"%PDF")


def test_invalid_format_is_rejected(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, "/reports/appraisal-status?format=word"))
    assert status == 422, body


def test_sys_admin_has_no_access_to_reports(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["SYS_ADMIN"], {"REPORT.VIEW"})
    status, _, body = asyncio.run(_call(app, "/reports/appraisal-status"))
    assert status == 403, body


def test_org_wide_scope_for_hr(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["HR"], {"REPORT.VIEW"})
    status, _, body = asyncio.run(_call(app, "/reports/appraisal-status"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "ORG"
    assert len(data["rows"]) == 1

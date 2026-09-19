"""
End-to-end smoke tests for the M24 Dashboard routes, driven over ASGI the
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
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import PerformanceCycle, RatingMaster
from app.models.rbac import User


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    seed.add(User(UserID=1, ADUsername="COMPANY\\dashuser", IsActive=True))

    plant_head = Employee(EmployeeCode="EMP-DASH-PH", ADUsername="COMPANY\\dashph", FullName="Plant Head", PlantID=1)
    manager = Employee(EmployeeCode="EMP-DASH-MGR", ADUsername="COMPANY\\dashmgr", FullName="Dash Manager", PlantID=1)
    seed.add_all([plant_head, manager])
    seed.flush()

    reportee = Employee(
        EmployeeCode="EMP-DASH-REP", ADUsername="COMPANY\\dashrep", FullName="Dash Reportee",
        ManagerID=manager.EmployeeID, PlantID=1,
    )
    other_plant_employee = Employee(
        EmployeeCode="EMP-DASH-OTHER", ADUsername="COMPANY\\dashother", FullName="Other Plant Employee", PlantID=2,
    )
    seed.add_all([reportee, other_plant_employee])
    seed.flush()

    cycle = PerformanceCycle(CycleName="DASH-SMOKE-CYCLE")
    rating = RatingMaster(RatingLabel="Good", MinPercent=60, MaxPercent=79.99)
    seed.add_all([cycle, rating])
    seed.flush()

    seed.add(EmployeePerformance(EmployeeID=reportee.EmployeeID, CycleID=cycle.CycleID, Status="MANAGER_REVIEW"))
    seed.add(EmployeePerformance(
        EmployeeID=other_plant_employee.EmployeeID, CycleID=cycle.CycleID, Status="FINAL_APPROVED",
        FinalScorePct=70, FinalRatingID=rating.RatingID,
    ))
    seed.commit()

    ids = {
        "plant_head_id": plant_head.EmployeeID, "manager_id": manager.EmployeeID, "reportee_id": reportee.EmployeeID,
    }
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(role_codes, employee_id=999):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\dashuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes={"DASHBOARD.VIEW"},
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(["HR"])
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

    headers = [(b"client", b"testclient")]
    scope = {
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": headers, "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80), "scheme": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1",
    }
    await app(scope, receive, send)
    return status_code, dict(headers_out), body


def test_hr_dashboard_is_org_wide(client_env):
    app, ids, _, _ = client_env
    status, _, body = asyncio.run(_call(app, "/dashboard/summary"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "ORG"
    assert data["total_appraisals"] == 2
    assert data["average_final_score_pct"] == 70.0
    assert data["rating_distribution"] == {"Good": 1}


def test_plant_head_dashboard_is_plant_scoped(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["PLANT_HEAD"], employee_id=ids["plant_head_id"])
    status, _, body = asyncio.run(_call(app, "/dashboard/summary"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "PLANT"
    assert data["total_appraisals"] == 1  # only the same-plant record


def test_manager_dashboard_shows_pending_action_count(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["MANAGER"], employee_id=ids["manager_id"])
    status, _, body = asyncio.run(_call(app, "/dashboard/summary"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "TEAM"
    assert data["total_appraisals"] == 1
    assert data["pending_my_action_count"] == 1  # the reportee's record is at MANAGER_REVIEW


def test_employee_dashboard_is_own_only(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["EMPLOYEE"], employee_id=ids["reportee_id"])
    status, _, body = asyncio.run(_call(app, "/dashboard/summary"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["scope"] == "OWN"
    assert data["total_appraisals"] == 1


def test_sys_admin_cannot_use_the_business_summary_endpoint(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["SYS_ADMIN"])
    status, _, body = asyncio.run(_call(app, "/dashboard/summary"))
    assert status == 403, body


def test_sys_admin_system_health_endpoint(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["SYS_ADMIN"])
    status, _, body = asyncio.run(_call(app, "/dashboard/system-health"))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["active_employees"] >= 4
    assert "FINAL_APPROVED" in data["appraisals_by_status"]


def test_business_role_cannot_use_the_system_health_endpoint(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(["HR"])
    status, _, body = asyncio.run(_call(app, "/dashboard/system-health"))
    assert status == 403, body

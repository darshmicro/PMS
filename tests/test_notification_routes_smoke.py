"""
End-to-end smoke tests for the M23 Notification routes, driven over ASGI
the same way as every prior module's smoke tests. Also exercises the
stage-based trigger retrofit into Self-Assessment's acknowledge/submit
endpoints (M12), confirming notify_stage_transition() actually fires at
those two of the eleven retrofitted call sites without needing to stand
up the entire six-stage workflow chain.
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
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.performance_masters import KPAMaster, KPIMaster, KPIScoringRule, PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    manager = Employee(EmployeeCode="EMP-NOTIF-MGR", ADUsername="COMPANY\\notifmgr", FullName="Notification Manager")
    seed.add(manager)
    seed.flush()

    employee = Employee(
        EmployeeCode="EMP-NOTIF-SMOKE", ADUsername="COMPANY\\notifsmoke", FullName="Notification Smoke Employee",
        ManagerID=manager.EmployeeID,
    )
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="NOTIF-SMOKE-CYCLE")
    kpa = KPAMaster(KPACode="KPA-NOTIF", KPAName="Notif KPA", IsActive=True)
    seed.add_all([cycle, kpa])
    seed.flush()
    kpi = KPIMaster(KPICode="KPI-NOTIF", KPIName="Notif KPI", KPAID=kpa.KPAID, MeasurementType="QUALITATIVE", IsActive=True)
    seed.add(kpi)
    seed.flush()
    seed.add(KPIScoringRule(KPIID=None, MinAchievement=0, MaxAchievement=200, Score=5, IsActive=True))

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="KPI_ASSIGNED")
    seed.add(performance)
    seed.flush()
    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    employee_kpi = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi.KPIID, MeasurementType="QUALITATIVE", Weightage=100,
    )
    seed.add(employee_kpi)
    seed.commit()

    ids = {
        "employee_id": employee.EmployeeID, "manager_id": manager.EmployeeID,
        "performance_id": performance.PerformanceID, "employee_kpi_id": employee_kpi.EmployeeKPIID,
    }
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
                user_id=1, ad_username="COMPANY\\notifuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["EMPLOYEE"], {"SELF_ASSESSMENT.VIEW", "SELF_ASSESSMENT.EDIT", "NOTIFICATION.VIEW"},
        employee_id=ids["employee_id"],
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


def test_acknowledge_notifies_self_and_submit_notifies_manager(client_env):
    app, ids, _, ctx_as = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/acknowledge", "POST"))
    assert status == 200, body

    status, _, body = asyncio.run(_call(
        app, f"/self-assessments/{pid}/kpis/{ids['employee_kpi_id']}", "PUT",
        {"achievement": 1, "self_score": 5, "employee_comments": "Done"},
    ))
    assert status == 200, body

    status, _, body = asyncio.run(_call(app, f"/self-assessments/{pid}/submit", "POST"))
    assert status == 200, body

    # The employee received a notification when their appraisal was acknowledged.
    status, _, body = asyncio.run(_call(app, "/notifications"))
    assert status == 200, body
    own_notifications = jsonlib.loads(body)
    assert len(own_notifications) == 1
    assert "acknowledge" in own_notifications[0]["message"].lower()

    # The manager received a notification when the self-assessment was submitted to them.
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["MANAGER"], {"NOTIFICATION.VIEW"}, employee_id=ids["manager_id"],
    )
    status, _, body = asyncio.run(_call(app, "/notifications"))
    assert status == 200, body
    manager_notifications = jsonlib.loads(body)
    assert len(manager_notifications) == 1
    assert "manager review" in manager_notifications[0]["message"].lower()


def test_notifications_are_scoped_to_the_caller_only(client_env):
    app, ids, SessionLocal, ctx_as = client_env

    db = SessionLocal()
    db.add(Notification(EmployeeID=ids["employee_id"], Message="For the employee"))
    db.add(Notification(EmployeeID=ids["manager_id"], Message="For the manager"))
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(app, "/notifications"))
    assert status == 200, body
    rows = jsonlib.loads(body)
    assert len(rows) == 1
    assert rows[0]["message"] == "For the employee"


def test_mark_read_and_unread_count(client_env):
    app, ids, SessionLocal, _ = client_env

    db = SessionLocal()
    db.add(Notification(EmployeeID=ids["employee_id"], Message="First"))
    db.add(Notification(EmployeeID=ids["employee_id"], Message="Second"))
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(app, "/notifications/unread-count"))
    assert status == 200, body
    assert jsonlib.loads(body)["unread_count"] == 2

    status, _, body = asyncio.run(_call(app, "/notifications"))
    notification_id = jsonlib.loads(body)[0]["notification_id"]

    status, _, body = asyncio.run(_call(app, f"/notifications/{notification_id}/read", "POST"))
    assert status == 200, body
    assert jsonlib.loads(body)["is_read"] is True

    status, _, body = asyncio.run(_call(app, "/notifications/unread-count"))
    assert jsonlib.loads(body)["unread_count"] == 1

    status, _, body = asyncio.run(_call(app, "/notifications/read-all", "POST"))
    assert status == 200, body

    status, _, body = asyncio.run(_call(app, "/notifications/unread-count"))
    assert jsonlib.loads(body)["unread_count"] == 0


def test_marking_someone_elses_notification_read_is_not_found(client_env):
    app, ids, SessionLocal, _ = client_env

    db = SessionLocal()
    other = Notification(EmployeeID=ids["manager_id"], Message="Not yours")
    db.add(other)
    db.commit()
    other_id = other.NotificationID
    db.close()

    status, _, body = asyncio.run(_call(app, f"/notifications/{other_id}/read", "POST"))
    assert status == 404, body


def test_export_is_reachable(client_env):
    app, ids, SessionLocal, _ = client_env

    db = SessionLocal()
    db.add(Notification(EmployeeID=ids["employee_id"], Message="Exportable"))
    db.commit()
    db.close()

    status, headers, body = asyncio.run(_call(app, "/notifications/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_caller_with_no_employee_identity_sees_an_empty_inbox(client_env):
    app, ids, _, ctx_as = client_env
    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["SYS_ADMIN"], {"NOTIFICATION.VIEW"}, employee_id=None,
    )
    status, _, body = asyncio.run(_call(app, "/notifications"))
    assert status == 200, body
    assert jsonlib.loads(body) == []

    status, _, body = asyncio.run(_call(app, "/notifications/unread-count"))
    assert status == 200, body
    assert jsonlib.loads(body)["unread_count"] == 0

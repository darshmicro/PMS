"""
End-to-end smoke tests for the M11 KPA/KPI Assignment routes, driven over
ASGI the same way as tests/test_routes_smoke.py (M5-M10) - this is what
would have caught the M3/M4 route-ordering bug, so every module gets this
same style of coverage in addition to its pure validator unit tests.
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
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    # Seed one employee, one cycle, and two KPAs (each with one KPI) that
    # the tests below assign to that employee.
    seed = SessionLocal()
    employee = Employee(EmployeeCode="EMP-SMOKE-1", ADUsername="COMPANY\\smoke1", FullName="Smoke Test Employee")
    manager = Employee(EmployeeCode="EMP-SMOKE-MGR", ADUsername="COMPANY\\smokemgr", FullName="Smoke Test Manager")
    seed.add_all([employee, manager])
    seed.flush()
    employee.ManagerID = manager.EmployeeID

    cycle = PerformanceCycle(CycleName="SMOKE-CYCLE")
    kpa1 = KPAMaster(KPACode="KPA-SMOKE-1", KPAName="Smoke KPA 1", IsActive=True)
    kpa2 = KPAMaster(KPACode="KPA-SMOKE-2", KPAName="Smoke KPA 2", IsActive=True)
    seed.add_all([cycle, kpa1, kpa2])
    seed.flush()
    kpi1 = KPIMaster(KPICode="KPI-SMOKE-1", KPIName="Smoke KPI 1", KPAID=kpa1.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    kpi2 = KPIMaster(KPICode="KPI-SMOKE-2", KPIName="Smoke KPI 2", KPAID=kpa2.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    kpi_wrong_kpa = KPIMaster(KPICode="KPI-SMOKE-3", KPIName="Smoke KPI 3", KPAID=kpa2.KPAID, MeasurementType="PERCENTAGE", IsActive=True)
    seed.add_all([kpi1, kpi2, kpi_wrong_kpa])
    seed.commit()

    ids = {
        "employee_id": employee.EmployeeID,
        "cycle_id": cycle.CycleID,
        "kpa1_id": kpa1.KPAID,
        "kpa2_id": kpa2.KPAID,
        "kpi1_id": kpi1.KPIID,
        "kpi2_id": kpi2.KPIID,
        "kpi_wrong_kpa_id": kpi_wrong_kpa.KPIID,
    }
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\hr_admin", employee_id=999,
            role_codes=["HR_ADMIN"],
            permission_codes={"ASSIGNMENT.VIEW", "ASSIGNMENT.EDIT"},
        )

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = override_ctx
    yield fastapi_app, ids
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


def test_full_assignment_lifecycle_create_to_submit(client_env):
    app, ids = client_env

    # 1. Create the assignment envelope
    status, _, body = asyncio.run(_call(
        app, "/assignments", "POST", {"employee_id": ids["employee_id"], "cycle_id": ids["cycle_id"]},
    ))
    assert status == 201, body
    performance_id = jsonlib.loads(body)["performance_id"]

    # 2. Creating a second assignment for the same employee+cycle is rejected
    status, _, body = asyncio.run(_call(
        app, "/assignments", "POST", {"employee_id": ids["employee_id"], "cycle_id": ids["cycle_id"]},
    ))
    assert status == 409, body

    # 3. Add first KPA
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas", "POST", {"kpa_id": ids["kpa1_id"]},
    ))
    assert status == 201, body
    ek1_id = jsonlib.loads(body)["employee_kpa_id"]

    # 4. Add second KPA
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas", "POST", {"kpa_id": ids["kpa2_id"]},
    ))
    assert status == 201, body
    ek2_id = jsonlib.loads(body)["employee_kpa_id"]

    # 5. Add a KPI under the wrong KPA - rejected (kpi_wrong_kpa belongs to kpa2, not kpa1)
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek1_id}/kpis", "POST",
        {"kpi_id": ids["kpi_wrong_kpa_id"], "weightage": 50, "target": 100},
    ))
    assert status == 400, body

    # 6. Add the correct KPI under kpa1 (weightage 60)
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek1_id}/kpis", "POST",
        {"kpi_id": ids["kpi1_id"], "weightage": 60, "target": 100},
    ))
    assert status == 201, body

    # 7. Duplicate KPI (same KPI again, under its own correct KPA) - rejected.
    # (Note: attempting this under ek2/kpa2 instead would trip the KPA-mismatch
    # check first, since kpi1 belongs to kpa1 - that's a different, also-valid
    # 400 rejection tested separately in step 5, so duplicate detection is
    # isolated here by re-adding kpi1 under its own KPA, ek1.)
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek1_id}/kpis", "POST",
        {"kpi_id": ids["kpi1_id"], "weightage": 10, "target": 100},
    ))
    assert status == 409, body

    # 8. Out-of-bounds weightage - rejected
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek2_id}/kpis", "POST",
        {"kpi_id": ids["kpi2_id"], "weightage": 150, "target": 100},
    ))
    assert status == 400, body

    # 9. Missing target for a numeric measurement type - rejected
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek2_id}/kpis", "POST",
        {"kpi_id": ids["kpi2_id"], "weightage": 30},
    ))
    assert status == 400, body

    # 10. Submit while kpa2 still has no KPI attached - rejected (this fires
    # before the weightage-total check, since an empty KPA is checked first)
    status, _, body = asyncio.run(_call(app, f"/assignments/{performance_id}/submit", "POST"))
    assert status == 400, body
    assert "Missing mandatory KPI" in jsonlib.loads(body)["detail"]

    # 11. Add the correct KPI under kpa2, but with weightage 30 -> total 90%
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas/{ek2_id}/kpis", "POST",
        {"kpi_id": ids["kpi2_id"], "weightage": 30, "target": 100},
    ))
    assert status == 201, body
    kpi2_row_id = jsonlib.loads(body)["employee_kpi_id"]

    # 11a. Submit while total (90%) != 100% - rejected on the weightage rule
    status, _, body = asyncio.run(_call(app, f"/assignments/{performance_id}/submit", "POST"))
    assert status == 400, body
    assert "100%" in jsonlib.loads(body)["detail"]

    # 11b. Edit that KPI's weightage up to 40 -> total now 100%
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpis/{kpi2_row_id}", "PUT", {"weightage": 40},
    ))
    assert status == 200, body

    # 12. Submit now succeeds
    status, _, body = asyncio.run(_call(app, f"/assignments/{performance_id}/submit", "POST"))
    assert status == 200, body
    submitted = jsonlib.loads(body)
    assert submitted["status"] == "KPI_ASSIGNED"
    assert float(submitted["total_weightage"]) == 100.0

    # 13. Post-submission mutation is blocked (assignment is no longer DRAFT)
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas", "POST", {"kpa_id": ids["kpa1_id"]},
    ))
    assert status == 409, body

    # 14. The stage-wise export route (nested one level deeper than /{id},
    # so it carries none of the M3/M4 shadowing risk) is reachable
    status, headers, body = asyncio.run(_call(app, f"/assignments/{performance_id}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_submit_with_empty_kpa_is_rejected(client_env):
    app, ids = client_env

    status, _, body = asyncio.run(_call(
        app, "/assignments", "POST", {"employee_id": ids["employee_id"], "cycle_id": ids["cycle_id"]},
    ))
    performance_id = jsonlib.loads(body)["performance_id"]

    # Add a KPA but never attach a KPI to it
    status, _, body = asyncio.run(_call(
        app, f"/assignments/{performance_id}/kpas", "POST", {"kpa_id": ids["kpa1_id"]},
    ))
    assert status == 201, body

    status, _, body = asyncio.run(_call(app, f"/assignments/{performance_id}/submit", "POST"))
    assert status == 400, body
    assert "Missing mandatory KPI" in jsonlib.loads(body)["detail"]


def test_assignment_list_and_get_routes(client_env):
    app, ids = client_env

    status, _, body = asyncio.run(_call(
        app, "/assignments", "POST", {"employee_id": ids["employee_id"], "cycle_id": ids["cycle_id"]},
    ))
    performance_id = jsonlib.loads(body)["performance_id"]

    status, _, body = asyncio.run(_call(app, "/assignments"))
    assert status == 200, body
    assert len(jsonlib.loads(body)) == 1

    status, _, body = asyncio.run(_call(app, f"/assignments/{performance_id}"))
    assert status == 200, body
    assert jsonlib.loads(body)["performance_id"] == performance_id

    # A non-existent assignment id is a 404, not a 500/422 - also confirms
    # "/assignments/{performance_id}" isn't shadowed by anything registered
    # after it (no literal-path route exists at this same depth in this router).
    status, _, body = asyncio.run(_call(app, "/assignments/999999"))
    assert status == 404, body

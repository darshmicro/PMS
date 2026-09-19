"""
End-to-end smoke test for M18's real integration point: approving a
record at MD Approval (M17) should trigger the Scoring Engine
automatically, and the result should then be visible via
GET /scoring-engine/{performance_id}.
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
from app.models.hr_review import HRReview
from app.models.manager_review import ManagerReview
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle, RatingMaster


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    employee = Employee(EmployeeCode="EMP-SE-SMOKE", ADUsername="COMPANY\\sesmoke", FullName="Scoring Engine Smoke Employee")
    seed.add(employee)
    seed.flush()

    cycle = PerformanceCycle(CycleName="SE-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=employee.EmployeeID, CycleID=cycle.CycleID, Status="MD_APPROVAL")
    seed.add(performance)
    seed.flush()

    kpa_master = KPAMaster(KPACode="KPA-SE-SMOKE", KPAName="Quality")
    seed.add(kpa_master)
    seed.flush()
    kpi_master = KPIMaster(KPICode="KPI-SE-SMOKE", KPIName="Defect Rate", KPAID=kpa_master.KPAID, MeasurementType="PERCENTAGE")
    seed.add(kpi_master)
    seed.flush()

    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa_master.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()
    employee_kpi = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_master.KPIID, MeasurementType="PERCENTAGE", Weightage=100,
    )
    seed.add(employee_kpi)
    seed.flush()
    seed.add(ManagerReview(EmployeeKPIID=employee_kpi.EmployeeKPIID, ManagerScore=5))

    seed.add(HRReview(PerformanceID=performance.PerformanceID, HRScore=95.0))
    seed.add(RatingMaster(RatingLabel="Outstanding", MinPercent=90, MaxPercent=100))
    seed.add(RatingMaster(RatingLabel="Good", MinPercent=60, MaxPercent=89.99))
    seed.commit()

    ids = {"performance_id": performance.PerformanceID}
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _ctx_as(role_codes, permission_codes):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\seuser", employee_id=999, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["MD"], {"MD_APPROVAL.VIEW", "MD_APPROVAL.EDIT", "SCORING_ENGINE.VIEW"},
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


def test_md_approval_triggers_scoring_engine_and_result_is_viewable(client_env):
    app, ids, _, _ = client_env
    pid = ids["performance_id"]

    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/approve", "POST", {"comments": "Approved"}))
    assert status == 200, body
    assert jsonlib.loads(body)["status"] == "FINAL_APPROVED"

    status, _, body = asyncio.run(_call(app, f"/scoring-engine/{pid}", "GET"))
    assert status == 200, body
    result = jsonlib.loads(body)
    assert result["final_score_pct"] == 95.0
    assert result["rating_label"] == "Outstanding"
    score_types = {s["score_type"] for s in result["scores"]}
    assert score_types == {"KPI_WEIGHTED", "COMPETENCY_WEIGHTED", "FINAL"}

    # Stage-wise export is reachable
    status, headers, body = asyncio.run(_call(app, f"/scoring-engine/{pid}/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_approve_fails_and_rolls_back_when_no_rating_band_covers_the_score(client_env):
    app, ids, SessionLocal, _ = client_env
    pid = ids["performance_id"]

    db = SessionLocal()
    db.query(RatingMaster).delete()
    db.commit()
    db.close()

    status, _, body = asyncio.run(_call(app, f"/md-approvals/{pid}/approve", "POST", {}))
    assert status == 409, body
    assert "Rating" in jsonlib.loads(body)["detail"] or "rating" in jsonlib.loads(body)["detail"]

    # The record must NOT have been locked/finalized by the failed attempt
    db = SessionLocal()
    performance = db.get(EmployeePerformance, pid)
    assert performance.Status == "MD_APPROVAL"
    assert performance.IsLocked is False
    db.close()

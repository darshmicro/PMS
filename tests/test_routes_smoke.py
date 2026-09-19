"""
End-to-end smoke tests that drive the actual FastAPI routes over ASGI
(not just the pure validator functions), the same way the M3/M4 route-
ordering bug was originally caught. Uses an in-memory SQLite DB shared
across the whole app via StaticPool, with auth/db dependencies overridden.
"""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - registers every model on Base.metadata
from app.core.dependencies import CurrentContext, get_current_context
from app.db.base import Base, get_db
from app.main import app as fastapi_app


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_ctx():
        return CurrentContext(
            user_id=1, ad_username="COMPANY\\hr_admin", employee_id=1,
            role_codes=["HR_ADMIN"],
            permission_codes={"MASTERS.VIEW", "MASTERS.EDIT", "MASTERS.DEACTIVATE"},
        )

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = override_ctx
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


async def _call(app, path, method="GET", json_body=None):
    import json as jsonlib

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


def test_performance_cycle_valid_dates_creates_successfully(client_env):
    status, _, body = asyncio.run(_call(
        client_env, "/masters/performance-cycles", "POST",
        {
            "cycle_name": "2026-27",
            "kpi_setting_start": "2026-04-01", "kpi_setting_end": "2026-04-30",
            "self_assessment_start": "2027-04-01", "self_assessment_end": "2027-04-10",
        },
    ))
    assert status == 201, body


def test_performance_cycle_bad_sequence_is_rejected_by_the_route(client_env):
    status, _, body = asyncio.run(_call(
        client_env, "/masters/performance-cycles", "POST",
        {
            "cycle_name": "BAD-2026",
            "kpi_setting_start": "2026-04-30", "kpi_setting_end": "2026-04-01",  # inverted
        },
    ))
    assert status == 400, body


def test_kpa_then_kpi_creation_and_scoring_rule_overlap_end_to_end(client_env):
    status, _, body = asyncio.run(_call(
        client_env, "/masters/kpa", "POST",
        {"kpa_code": "KPA-E2E-1", "kpa_name": "E2E KPA", "default_weightage": 20.0},
    ))
    assert status == 201, body
    import json
    kpa_id = json.loads(body)["kpa_id"]

    status, _, body = asyncio.run(_call(
        client_env, "/masters/kpi", "POST",
        {
            "kpi_code": "KPI-E2E-1", "kpi_name": "E2E KPI", "kpa_id": kpa_id,
            "measurement_type": "PERCENTAGE", "weightage": 100.0,
        },
    ))
    assert status == 201, body
    kpi_id = json.loads(body)["kpi_id"]

    # First scoring rule for this KPI - should succeed
    status, _, body = asyncio.run(_call(
        client_env, "/masters/scoring-rules", "POST",
        {"kpi_id": kpi_id, "min_achievement": 100.0, "max_achievement": 104.99, "score": 3},
    ))
    assert status == 201, body

    # Second, overlapping rule for the SAME KPI - should be rejected
    status, _, body = asyncio.run(_call(
        client_env, "/masters/scoring-rules", "POST",
        {"kpi_id": kpi_id, "min_achievement": 102.0, "max_achievement": 110.0, "score": 4},
    ))
    assert status == 409, body


def test_kpi_export_route_is_reachable_and_not_shadowed(client_env):
    status, headers, body = asyncio.run(_call(client_env, "/masters/kpi/export"))
    assert status == 200, body
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_invalid_measurement_type_is_rejected_by_the_route(client_env):
    status, _, body = asyncio.run(_call(
        client_env, "/masters/kpa", "POST", {"kpa_code": "KPA-E2E-2", "kpa_name": "Another KPA"},
    ))
    import json
    kpa_id = json.loads(body)["kpa_id"]

    status, _, body = asyncio.run(_call(
        client_env, "/masters/kpi", "POST",
        {
            "kpi_code": "KPI-BAD-TYPE", "kpi_name": "Bad Type KPI", "kpa_id": kpa_id,
            "measurement_type": "NOT_REAL",
        },
    ))
    assert status == 400, body

"""
End-to-end smoke tests for the M28 System Configuration routes, driven
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

    def _ctx_as(role_codes):
        def _override():
            return CurrentContext(
                user_id=1, ad_username="COMPANY\\sysconfigadmin", employee_id=None, role_codes=role_codes,
                permission_codes=set(),
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(["SYS_ADMIN"])
    yield fastapi_app, _ctx_as
    fastapi_app.dependency_overrides.clear()


async def _call(app, path, method="GET", body: bytes = b""):
    status_code, headers_out, resp_body = None, [], b""

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        nonlocal status_code, headers_out, resp_body
        if message["type"] == "http.response.start":
            status_code = message["status"]
            headers_out = message["headers"]
        elif message["type"] == "http.response.body":
            resp_body += message.get("body", b"")

    path_only, _, query_string = path.partition("?")
    headers = [(b"client", b"testclient")]
    if body:
        headers.append((b"content-type", b"application/json"))
    scope = {
        "type": "http", "method": method, "path": path_only, "raw_path": path_only.encode(),
        "query_string": query_string.encode(), "headers": headers, "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80), "scheme": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1",
    }
    await app(scope, receive, send)
    return status_code, dict(headers_out), resp_body


def test_create_then_list_then_get(client_env):
    app, _ = client_env
    payload = jsonlib.dumps({"config_value": "smtp.company.local", "description": "Outbound relay"}).encode()
    status, _, body = asyncio.run(_call(app, "/system-config/SMTP_SERVER", method="POST", body=payload))
    assert status == 201, body

    status, _, body = asyncio.run(_call(app, "/system-config"))
    assert status == 200, body
    rows = jsonlib.loads(body)
    assert len(rows) == 1
    assert rows[0]["config_key"] == "SMTP_SERVER"

    status, _, body = asyncio.run(_call(app, "/system-config/SMTP_SERVER"))
    assert status == 200, body
    assert jsonlib.loads(body)["config_value"] == "smtp.company.local"


def test_create_duplicate_is_conflict(client_env):
    app, _ = client_env
    payload = jsonlib.dumps({"config_value": "1"}).encode()
    asyncio.run(_call(app, "/system-config/MAX_UPLOAD_SIZE_MB", method="POST", body=payload))
    status, _, body = asyncio.run(_call(app, "/system-config/MAX_UPLOAD_SIZE_MB", method="POST", body=payload))
    assert status == 409, body


def test_update_missing_key_is_not_found(client_env):
    app, _ = client_env
    payload = jsonlib.dumps({"config_value": "x"}).encode()
    status, _, body = asyncio.run(_call(app, "/system-config/AD_SERVER", method="PUT", body=payload))
    assert status == 404, body


def test_update_existing_key(client_env):
    app, _ = client_env
    payload = jsonlib.dumps({"config_value": "dc1.company.local"}).encode()
    asyncio.run(_call(app, "/system-config/AD_SERVER", method="POST", body=payload))

    payload2 = jsonlib.dumps({"config_value": "dc2.company.local"}).encode()
    status, _, body = asyncio.run(_call(app, "/system-config/AD_SERVER", method="PUT", body=payload2))
    assert status == 200, body
    assert jsonlib.loads(body)["config_value"] == "dc2.company.local"


def test_secret_like_key_is_rejected(client_env):
    app, _ = client_env
    payload = jsonlib.dumps({"config_value": "hunter2"}).encode()
    status, _, body = asyncio.run(_call(app, "/system-config/AD_BIND_PASSWORD", method="POST", body=payload))
    assert status == 400, body


def test_non_sys_admin_roles_are_forbidden(client_env):
    app, ctx_as = client_env
    for role in ("EMPLOYEE", "HR", "MD", "HR_ADMIN", "PLANT_HEAD"):
        fastapi_app.dependency_overrides[get_current_context] = ctx_as([role])
        status, _, body = asyncio.run(_call(app, "/system-config"))
        assert status == 403, (role, body)


def test_get_missing_key_is_not_found(client_env):
    app, _ = client_env
    status, _, body = asyncio.run(_call(app, "/system-config/SMTP_FROM"))
    assert status == 404, body

"""
End-to-end smoke tests for AUTH_MODE=demo_local (the Windows 11 Home /
no-AD local demo path). Settings are read once at process start in this
codebase (get_settings() is lru_cache'd, and app/api/routes/auth.py
captures `settings` at module import time) - so rather than fighting that
via env-var reloading, these tests monkeypatch the `settings` objects the
auth and demo_auth route modules actually hold, the same way a real
deployment would have AUTH_MODE fixed for its whole process lifetime.
"""
import asyncio
import json as jsonlib
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes.auth as auth_module
import app.api.routes.demo_auth as demo_auth_module
import app.models  # noqa: F401 - registers every model on Base.metadata
from app.core.dependencies import CurrentContext, get_current_context
from app.db.base import Base, get_db
from app.main import app as fastapi_app
from app.models.rbac import Role, User, UserRole
from app.services.demo_auth_service import set_password


@dataclass
class _FakeSettings:
    AUTH_MODE: str = "demo_local"
    ENVIRONMENT: str = "development"
    IIS_FORWARDED_USER_HEADER: str = "X-Remote-User"


@pytest.fixture()
def client_env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    role = Role(RoleCode="SYS_ADMIN", RoleName="System Administrator", IsBusinessRole=False, IsActive=True)
    seed.add(role)
    seed.flush()
    user = User(ADUsername="demoadmin", IsActive=True)
    seed.add(user)
    seed.flush()
    seed.add(UserRole(UserID=user.UserID, RoleID=role.RoleID))
    seed.commit()
    set_password(seed, user.UserID, "first-password")
    user_id = user.UserID
    seed.close()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fake_settings = _FakeSettings()
    monkeypatch.setattr(auth_module, "settings", fake_settings)
    monkeypatch.setattr(demo_auth_module, "get_settings", lambda: fake_settings)

    yield fastapi_app, user_id, fake_settings, SessionLocal
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


def test_login_succeeds_with_correct_demo_credentials(client_env):
    app, user_id, _settings, _ = client_env
    payload = jsonlib.dumps({"username": "demoadmin", "password": "first-password"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/login", method="POST", body=payload))
    assert status == 200, body
    data = jsonlib.loads(body)
    assert data["ad_username"] == "demoadmin"
    assert "SYS_ADMIN" in data["role_codes"]


def test_login_fails_with_wrong_password(client_env):
    app, _, _settings, _ = client_env
    payload = jsonlib.dumps({"username": "demoadmin", "password": "wrong"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/login", method="POST", body=payload))
    assert status == 401, body


def test_demo_local_refused_when_environment_is_production(client_env):
    app, _, settings, _ = client_env
    settings.ENVIRONMENT = "production"
    payload = jsonlib.dumps({"username": "demoadmin", "password": "first-password"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/login", method="POST", body=payload))
    assert status == 500, body


def test_self_service_change_password(client_env):
    app, user_id, _settings, _ = client_env
    fastapi_app.dependency_overrides[get_current_context] = lambda: CurrentContext(
        user_id=user_id, ad_username="demoadmin", employee_id=None, role_codes=["SYS_ADMIN"], permission_codes=set(),
    )
    payload = jsonlib.dumps({"current_password": "first-password", "new_password": "second-password"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/demo/change-password", method="PUT", body=payload))
    assert status == 204, body

    login_payload = jsonlib.dumps({"username": "demoadmin", "password": "second-password"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/login", method="POST", body=login_payload))
    assert status == 200, body


def test_admin_set_password_requires_hr_admin_or_sys_admin_role(client_env):
    app, user_id, _settings, _ = client_env
    fastapi_app.dependency_overrides[get_current_context] = lambda: CurrentContext(
        user_id=999, ad_username="regularemployee", employee_id=None, role_codes=["EMPLOYEE"], permission_codes=set(),
    )
    payload = jsonlib.dumps({"new_password": "reset-password-1"}).encode()
    status, _, body = asyncio.run(_call(app, f"/auth/demo/set-password/{user_id}", method="POST", body=payload))
    assert status == 403, body


def test_admin_set_password_succeeds_for_sys_admin(client_env):
    app, user_id, _settings, _ = client_env
    fastapi_app.dependency_overrides[get_current_context] = lambda: CurrentContext(
        user_id=1, ad_username="anotheradmin", employee_id=None, role_codes=["SYS_ADMIN"], permission_codes=set(),
    )
    payload = jsonlib.dumps({"new_password": "reset-password-1"}).encode()
    status, _, body = asyncio.run(_call(app, f"/auth/demo/set-password/{user_id}", method="POST", body=payload))
    assert status == 204, body

    login_payload = jsonlib.dumps({"username": "demoadmin", "password": "reset-password-1"}).encode()
    status, _, body = asyncio.run(_call(app, "/auth/login", method="POST", body=login_payload))
    assert status == 200, body

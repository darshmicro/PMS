"""
End-to-end smoke tests for the M22 Attachment routes, driven over ASGI the
same way as every prior module's smoke tests. Upload is multipart/form-data
(not JSON), so this file builds the multipart body by hand rather than
reusing the plain-JSON `_call()` helper other smoke tests use.
"""
import asyncio
import json as jsonlib
import uuid

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
from app.models.performance_masters import KPAMaster, KPIMaster, PerformanceCycle
from app.models.rbac import User


@pytest.fixture()
def client_env():
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)

    seed = SessionLocal()
    user = User(UserID=1, ADUsername="COMPANY\\attachuser", IsActive=True)
    seed.add(user)

    subject = Employee(EmployeeCode="EMP-ATT-SUBJECT", ADUsername="COMPANY\\attsubject", FullName="Attachment Subject Employee")
    seed.add(subject)
    seed.flush()

    manager = Employee(EmployeeCode="EMP-ATT-MGR", ADUsername="COMPANY\\attmgr", FullName="Attachment Manager")
    seed.add(manager)
    seed.flush()

    subject.ManagerID = manager.EmployeeID
    seed.flush()

    outsider = Employee(EmployeeCode="EMP-ATT-OUTSIDER", ADUsername="COMPANY\\attoutsider", FullName="Unrelated Employee")
    seed.add(outsider)
    seed.flush()

    cycle = PerformanceCycle(CycleName="ATT-SMOKE-CYCLE")
    seed.add(cycle)
    seed.flush()

    performance = EmployeePerformance(EmployeeID=subject.EmployeeID, CycleID=cycle.CycleID, Status="SELF_ASSESSMENT")
    seed.add(performance)
    seed.flush()

    kpa_master = KPAMaster(KPACode="KPA-ATT", KPAName="Quality")
    seed.add(kpa_master)
    seed.flush()

    kpi_master = KPIMaster(KPICode="KPI-ATT", KPIName="Defect Rate", KPAID=kpa_master.KPAID, MeasurementType="PERCENTAGE")
    seed.add(kpi_master)
    seed.flush()

    employee_kpa = EmployeeKPA(PerformanceID=performance.PerformanceID, KPAID=kpa_master.KPAID, Weightage=100)
    seed.add(employee_kpa)
    seed.flush()

    employee_kpi = EmployeeKPI(
        EmployeeKPAID=employee_kpa.EmployeeKPAID, KPIID=kpi_master.KPIID, MeasurementType="PERCENTAGE",
        Weightage=100, EvidenceRequired=True,
    )
    seed.add(employee_kpi)
    seed.commit()

    ids = {
        "employee_id": subject.EmployeeID, "manager_id": manager.EmployeeID,
        "outsider_id": outsider.EmployeeID, "employee_kpi_id": employee_kpi.EmployeeKPIID,
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
                user_id=1, ad_username="COMPANY\\attachuser", employee_id=employee_id, role_codes=role_codes,
                permission_codes=permission_codes,
            )
        return _override

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_context] = _ctx_as(
        ["HR"], {"ATTACHMENT.VIEW", "ATTACHMENT.EDIT"},
    )
    yield fastapi_app, ids, SessionLocal, _ctx_as
    fastapi_app.dependency_overrides.clear()


def _multipart_body(fields: dict, filename: str, file_content: bytes, content_type: str = "application/pdf"):
    boundary = f"----pms-test-{uuid.uuid4().hex}"
    lines = []
    for name, value in fields.items():
        if value is None:
            continue
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(f"{value}\r\n".encode())
    lines.append(f"--{boundary}\r\n".encode())
    lines.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    lines.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    lines.append(file_content)
    lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    body = b"".join(lines)
    return f"multipart/form-data; boundary={boundary}", body


async def _call(app, path, method="GET", json_body=None, raw_body=None, content_type=None):
    status_code, headers_out, body = None, [], b""
    if raw_body is not None:
        body_bytes = raw_body
    elif json_body is not None:
        body_bytes = jsonlib.dumps(json_body).encode()
    else:
        body_bytes = b""

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
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    elif json_body is not None:
        headers.append((b"content-type", b"application/json"))

    # This harness's path may carry a "?query=string" suffix (unlike every
    # prior smoke test's harness, none of which ever exercised a query
    # param) - ASGI routes on scope["path"] alone and expects the query
    # separately in scope["query_string"], so split it here.
    path_only, _, query_string = path.partition("?")
    scope = {
        "type": "http", "method": method, "path": path_only, "raw_path": path_only.encode(),
        "query_string": query_string.encode(), "headers": headers, "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80), "scheme": "http", "asgi": {"version": "3.0"},
        "http_version": "1.1",
    }
    await app(scope, receive, send)
    return status_code, dict(headers_out), body


def test_full_attachment_lifecycle_upload_download_and_versioning(client_env):
    app, ids, _, _ = client_env
    employee_kpi_id = ids["employee_kpi_id"]

    content_type, body = _multipart_body(
        {"employee_kpi_id": employee_kpi_id}, "evidence.pdf", b"%PDF-1.4 fake evidence bytes",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 201, body_out
    created = jsonlib.loads(body_out)
    assert created["file_version"] == 1
    assert created["file_name"] == "evidence.pdf"
    attachment_id = created["attachment_id"]

    status, headers, body_out = asyncio.run(_call(app, f"/attachments/{attachment_id}/download"))
    assert status == 200, body_out
    assert body_out == b"%PDF-1.4 fake evidence bytes"
    assert b'filename="evidence.pdf"' in headers.get(b"content-disposition", b"")

    # Re-uploading the same original filename against the same KPI creates version 2.
    content_type, body = _multipart_body(
        {"employee_kpi_id": employee_kpi_id}, "evidence.pdf", b"%PDF-1.4 revised evidence bytes",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 201, body_out
    assert jsonlib.loads(body_out)["file_version"] == 2

    status, _, body_out = asyncio.run(_call(app, f"/attachments?employee_kpi_id={employee_kpi_id}"))
    assert status == 200, body_out
    assert len(jsonlib.loads(body_out)) == 2

    status, _, body_out = asyncio.run(
        _call(app, f"/attachments?employee_kpi_id={employee_kpi_id}&latest_only=true")
    )
    assert status == 200, body_out
    latest = jsonlib.loads(body_out)
    assert len(latest) == 1
    assert latest[0]["file_version"] == 2

    status, headers, body_out = asyncio.run(
        _call(app, f"/attachments/export/list?employee_kpi_id={employee_kpi_id}")
    )
    assert status == 200, body_out
    assert headers.get(b"content-type") == b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_disallowed_extension_is_rejected(client_env):
    app, ids, _, _ = client_env
    content_type, body = _multipart_body(
        {"employee_kpi_id": ids["employee_kpi_id"]}, "malware.exe", b"not really an exe", content_type="application/octet-stream",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 400, body_out


def test_both_targets_at_once_is_rejected(client_env):
    app, ids, _, _ = client_env
    content_type, body = _multipart_body(
        {"employee_kpi_id": ids["employee_kpi_id"], "related_employee_id": ids["employee_id"]},
        "evidence.pdf", b"bytes",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 400, body_out


def test_general_employee_scoped_attachment_via_related_employee_id(client_env):
    app, ids, _, _ = client_env
    content_type, body = _multipart_body(
        {"related_employee_id": ids["employee_id"]}, "pip_plan.docx", b"pip document bytes",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 201, body_out
    created = jsonlib.loads(body_out)
    assert created["employee_kpi_id"] is None
    assert created["related_employee_id"] == ids["employee_id"]


def test_manager_can_upload_and_view_within_scope_but_not_for_others(client_env):
    app, ids, _, ctx_as = client_env
    manager_id = ids["manager_id"]
    employee_kpi_id = ids["employee_kpi_id"]

    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["MANAGER"], {"ATTACHMENT.VIEW", "ATTACHMENT.EDIT"}, employee_id=manager_id,
    )

    content_type, body = _multipart_body(
        {"employee_kpi_id": employee_kpi_id}, "manager_note.pdf", b"manager uploaded evidence",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 201, body_out

    status, _, body_out = asyncio.run(_call(app, f"/attachments?employee_kpi_id={employee_kpi_id}"))
    assert status == 200, body_out
    assert len(jsonlib.loads(body_out)) == 1

    # An unrelated employee (not this manager's report, not the manager themself) is out of scope.
    outsider_content_type, outsider_body = _multipart_body(
        {"related_employee_id": ids["outsider_id"]}, "self_note.pdf", b"note about someone else entirely",
    )
    status, _, body_out = asyncio.run(
        _call(app, "/attachments", "POST", raw_body=outsider_body, content_type=outsider_content_type)
    )
    assert status == 403, body_out


def test_employee_can_view_own_evidence_but_not_upload(client_env):
    app, ids, _, ctx_as = client_env
    employee_id = ids["employee_id"]
    employee_kpi_id = ids["employee_kpi_id"]

    content_type, body = _multipart_body(
        {"employee_kpi_id": employee_kpi_id}, "evidence.pdf", b"evidence bytes",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 201, body_out

    fastapi_app.dependency_overrides[get_current_context] = ctx_as(
        ["EMPLOYEE"], {"ATTACHMENT.VIEW"}, employee_id=employee_id,
    )
    status, _, body_out = asyncio.run(_call(app, f"/attachments?employee_kpi_id={employee_kpi_id}"))
    assert status == 200, body_out
    assert len(jsonlib.loads(body_out)) == 1

    # No ATTACHMENT.EDIT permission -> 403
    content_type, body = _multipart_body(
        {"employee_kpi_id": employee_kpi_id}, "should_be_blocked.pdf", b"bytes",
    )
    status, _, body_out = asyncio.run(_call(app, "/attachments", "POST", raw_body=body, content_type=content_type))
    assert status == 403, body_out

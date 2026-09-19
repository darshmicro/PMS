"""
Attachment endpoints (spec Section 4.5/9 / M22). No RBAC matrix row exists
for this module either (Section 5's matrix stops at Audit Log - the same
gap M18/M20/M21 already hit). Section 7 gives one concrete anchor -
"Self-Assessment form (per KPI, with evidence upload)" - which is an
Employee-uploads-own-evidence flow, but the DDL's RelatedEmployeeID
column (see model docstring) also has to serve general employee-scoped
attachments such as PIP supporting documents, which Section 7 places
under HR. Reading those together: ATTACHMENT.VIEW reuses the same broad
visibility scope as every review-chain module (self/reports/department/
broad-access); ATTACHMENT.EDIT (upload only - there is no destructive
update, see below) is granted to the same set, with an in-app ownership
check (_apply_scope, single-record form) rather than a narrower
permission, since the caller only knows which KPI/employee they're
attaching evidence to at request time, not at permission-grant time.

There is no DELETE or in-place update endpoint. A superseding upload is
just a new row with FileVersion+1 (see model docstring) - matching this
codebase's broader insert-only-history convention (Audit_Log,
Workflow_History, and now Attachments) rather than mutating or removing
evidence that may already be referenced by an approved appraisal record.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.attachment import Attachment
from app.models.employee import Employee
from app.schemas.attachment import AttachmentOut
from app.services.attachment_service import (
    ensure_exactly_one_target,
    generate_stored_filename,
    next_file_version,
    read_file,
    sanitize_filename,
    save_file,
    validate_extension,
    validate_size,
    virus_scan_hook,
)
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/attachments", tags=["attachments"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}

_EmployeeViaKPI = aliased(Employee)
_EmployeeViaRelated = aliased(Employee)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _is_broad_access(ctx: CurrentContext) -> bool:
    return bool(BROAD_ACCESS_ROLES & set(ctx.role_codes))


def _join_owning_employee(query):
    """Attachments are scoped to an owning employee via one of two
    nullable paths (see model docstring) - joined here with aliased
    Employee tables and coalesced so a single filter covers both."""
    return (
        query.outerjoin(EmployeeKPI, Attachment.EmployeeKPIID == EmployeeKPI.EmployeeKPIID)
        .outerjoin(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .outerjoin(EmployeePerformance, EmployeeKPA.PerformanceID == EmployeePerformance.PerformanceID)
        .outerjoin(_EmployeeViaKPI, EmployeePerformance.EmployeeID == _EmployeeViaKPI.EmployeeID)
        .outerjoin(_EmployeeViaRelated, Attachment.RelatedEmployeeID == _EmployeeViaRelated.EmployeeID)
    )


def _apply_scope(query, ctx: CurrentContext):
    if _is_broad_access(ctx):
        return query
    query = _join_owning_employee(query)
    owner_id = func.coalesce(_EmployeeViaKPI.EmployeeID, _EmployeeViaRelated.EmployeeID)
    hod_id = func.coalesce(_EmployeeViaKPI.HODID, _EmployeeViaRelated.HODID)
    manager_id = func.coalesce(_EmployeeViaKPI.ManagerID, _EmployeeViaRelated.ManagerID)
    if "HOD" in ctx.role_codes:
        return query.filter(hod_id == ctx.employee_id)
    if "MANAGER" in ctx.role_codes:
        return query.filter(manager_id == ctx.employee_id)
    return query.filter(owner_id == ctx.employee_id)


def _resolve_owning_employee(db: Session, employee_kpi_id: int | None, related_employee_id: int | None) -> Employee:
    if employee_kpi_id is not None:
        kpi = db.get(EmployeeKPI, employee_kpi_id)
        if kpi is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="EmployeeKPI not found")
        employee = kpi.employee_kpa.performance.employee
    else:
        employee = db.get(Employee, related_employee_id)
        if employee is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee


def _ensure_can_upload_for(ctx: CurrentContext, employee: Employee) -> None:
    if _is_broad_access(ctx):
        return
    if "HOD" in ctx.role_codes and employee.HODID == ctx.employee_id:
        return
    if "MANAGER" in ctx.role_codes and employee.ManagerID == ctx.employee_id:
        return
    if employee.EmployeeID == ctx.employee_id:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Outside your access scope")


def _get_scoped_attachment(db: Session, attachment_id: int, ctx: CurrentContext) -> Attachment:
    query = _apply_scope(db.query(Attachment).filter(Attachment.AttachmentID == attachment_id), ctx)
    attachment = query.one_or_none()
    if attachment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found or outside your access scope")
    return attachment


def _to_out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        attachment_id=attachment.AttachmentID, employee_kpi_id=attachment.EmployeeKPIID,
        related_employee_id=attachment.RelatedEmployeeID, file_name=attachment.FileName,
        file_version=attachment.FileVersion, uploaded_by=attachment.uploaded_by_user.ADUsername,
        uploaded_at=attachment.UploadedAt,
    )


@router.get("", response_model=list[AttachmentOut])
def list_attachments(
    employee_kpi_id: int | None = None, related_employee_id: int | None = None, latest_only: bool = False,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("ATTACHMENT.VIEW")),
):
    query = _apply_scope(db.query(Attachment), ctx)
    if employee_kpi_id is not None:
        query = query.filter(Attachment.EmployeeKPIID == employee_kpi_id)
    if related_employee_id is not None:
        query = query.filter(Attachment.RelatedEmployeeID == related_employee_id)
    rows = query.order_by(Attachment.AttachmentID).all()
    if latest_only:
        latest_by_slot: dict[tuple, Attachment] = {}
        for row in rows:
            key = (row.EmployeeKPIID, row.RelatedEmployeeID, row.FileName)
            current = latest_by_slot.get(key)
            if current is None or row.FileVersion > current.FileVersion:
                latest_by_slot[key] = row
        rows = list(latest_by_slot.values())
    return [_to_out(a) for a in rows]


@router.get("/{attachment_id}", response_model=AttachmentOut)
def get_attachment(
    attachment_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("ATTACHMENT.VIEW")),
):
    return _to_out(_get_scoped_attachment(db, attachment_id, ctx))


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("ATTACHMENT.VIEW")),
):
    attachment = _get_scoped_attachment(db, attachment_id, ctx)
    content = read_file(attachment.StoredPath)
    return Response(
        content=content, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{attachment.FileName}"'},
    )


@router.post("", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED)
def upload_attachment(
    request: Request, file: UploadFile = File(...), employee_kpi_id: int | None = Form(None),
    related_employee_id: int | None = Form(None), db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("ATTACHMENT.EDIT")),
):
    ensure_exactly_one_target(employee_kpi_id, related_employee_id)
    owning_employee = _resolve_owning_employee(db, employee_kpi_id, related_employee_id)
    _ensure_can_upload_for(ctx, owning_employee)

    safe_name = sanitize_filename(file.filename or "")
    validate_extension(safe_name)

    content = file.file.read()
    validate_size(len(content), get_settings().MAX_UPLOAD_SIZE_MB)
    virus_scan_hook(content)

    stored_filename = generate_stored_filename(safe_name)
    stored_path = save_file(stored_filename, content)
    version = next_file_version(db, employee_kpi_id, related_employee_id, safe_name)

    attachment = Attachment(
        EmployeeKPIID=employee_kpi_id, RelatedEmployeeID=related_employee_id, FileName=safe_name,
        StoredPath=stored_path, UploadedBy=ctx.user_id, FileVersion=version,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="ATTACHMENT", record_id=str(attachment.AttachmentID),
        new_value=f"FileName={safe_name}, FileVersion={version}", ip_address=_client_ip(request),
    )
    return _to_out(attachment)


@router.get("/export/list")
def export_attachments(
    employee_kpi_id: int | None = None, related_employee_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("ATTACHMENT.VIEW")),
):
    """Metadata export (spec Section 36A) - the file bytes themselves are
    never embedded in the workbook, only a manifest of what was uploaded."""
    query = _apply_scope(db.query(Attachment), ctx)
    if employee_kpi_id is not None:
        query = query.filter(Attachment.EmployeeKPIID == employee_kpi_id)
    if related_employee_id is not None:
        query = query.filter(Attachment.RelatedEmployeeID == related_employee_id)
    attachments = query.order_by(Attachment.AttachmentID).all()

    rows = [[
        a.AttachmentID, a.EmployeeKPIID or "", a.RelatedEmployeeID or "", a.FileName, a.FileVersion,
        a.uploaded_by_user.ADUsername, a.UploadedAt.isoformat(),
    ] for a in attachments]

    content = build_export_workbook(
        sheet_title="Attachments",
        headers=["AttachmentID", "EmployeeKPIID", "RelatedEmployeeID", "FileName", "FileVersion", "UploadedBy", "UploadedAt"],
        rows=rows, generated_by=ctx.ad_username, context_label="Attachments",
        filter_criteria=f"EmployeeKPIID={employee_kpi_id}, RelatedEmployeeID={related_employee_id}",
    )
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Attachments_Export.xlsx"},
    )

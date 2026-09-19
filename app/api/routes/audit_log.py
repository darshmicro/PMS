"""
Audit Log endpoints (spec Section 5/7/32 / M26). Read-only - see
audit_log_service.py's docstring for why there is no edit endpoint at
all, and for the RBAC matrix row this module implements directly
(X | X | X | V(dept) | V(plant) | V(all) | V(all) | V(all, no edit)).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.audit import AuditLog
from app.schemas.audit_log import AuditLogEntryOut
from app.services.audit_log_service import apply_audit_scope
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


def _to_out(entry: AuditLog) -> AuditLogEntryOut:
    return AuditLogEntryOut(
        audit_id=entry.AuditID, user_id=entry.UserID, ad_username=entry.ADUsername, employee_id=entry.EmployeeID,
        action=entry.Action, module=entry.Module, record_id=entry.RecordID, old_value=entry.OldValue,
        new_value=entry.NewValue, reason=entry.Reason, actioned_at=entry.ActionedAt, ip_address=entry.IPAddress,
    )


def _filtered_query(
    db: Session, ctx: CurrentContext, module: str | None, action: str | None, employee_id: int | None,
    record_id: str | None, from_date: datetime | None, to_date: datetime | None,
):
    query, scope = apply_audit_scope(db.query(AuditLog), db, ctx)
    if module is not None:
        query = query.filter(AuditLog.Module == module)
    if action is not None:
        query = query.filter(AuditLog.Action == action)
    if employee_id is not None:
        query = query.filter(AuditLog.EmployeeID == employee_id)
    if record_id is not None:
        query = query.filter(AuditLog.RecordID == record_id)
    if from_date is not None:
        query = query.filter(AuditLog.ActionedAt >= from_date)
    if to_date is not None:
        query = query.filter(AuditLog.ActionedAt <= to_date)
    return query, scope


@router.get("", response_model=list[AuditLogEntryOut])
def list_audit_log(
    module: str | None = None, action: str | None = None, employee_id: int | None = None,
    record_id: str | None = None, from_date: datetime | None = None, to_date: datetime | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("AUDIT_LOG.VIEW")),
):
    query, _scope = _filtered_query(db, ctx, module, action, employee_id, record_id, from_date, to_date)
    rows = query.order_by(AuditLog.ActionedAt.desc()).all()
    return [_to_out(e) for e in rows]


@router.get("/{audit_id}", response_model=AuditLogEntryOut)
def get_audit_log_entry(
    audit_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("AUDIT_LOG.VIEW")),
):
    query, _scope = apply_audit_scope(db.query(AuditLog).filter(AuditLog.AuditID == audit_id), db, ctx)
    entry = query.one_or_none()
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Audit log entry not found or outside your access scope")
    return _to_out(entry)


@router.get("/export/list")
def export_audit_log(
    module: str | None = None, action: str | None = None, employee_id: int | None = None,
    record_id: str | None = None, from_date: datetime | None = None, to_date: datetime | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("AUDIT_LOG.VIEW")),
):
    query, scope = _filtered_query(db, ctx, module, action, employee_id, record_id, from_date, to_date)
    rows = query.order_by(AuditLog.ActionedAt.desc()).all()

    export_rows = [
        [
            e.AuditID, e.ADUsername or "", e.EmployeeID or "", e.Action, e.Module, e.RecordID or "",
            e.Reason or "", e.ActionedAt.isoformat(), e.IPAddress or "",
        ]
        for e in rows
    ]
    content = build_export_workbook(
        sheet_title="Audit Log",
        headers=["AuditID", "ADUsername", "EmployeeID", "Action", "Module", "RecordID", "Reason", "ActionedAt", "IPAddress"],
        rows=export_rows, generated_by=ctx.ad_username, context_label=f"Audit Log - {scope} scope",
        filter_criteria=f"Module={module}, Action={action}, EmployeeID={employee_id}",
    )
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Audit_Log_Export.xlsx"},
    )

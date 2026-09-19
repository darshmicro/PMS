"""
Notification endpoints (spec Section 4.5/7 / M23). Unlike every other
module's list/get, there is no _apply_scope role-tiering here at all -
see notification_service.py's docstring: "Notifications panel" is a
Common screen for every role, and it is always self-scoped, never
broadened for Manager/HOD/HR/Plant Head/MD/HR Administrator the way
every other visibility rule in this codebase is. Marking a notification
read is treated as part of using your own inbox, not a separate grantable
capability, so it only requires the same NOTIFICATION.VIEW permission
every other endpoint here does - there is no NOTIFICATION.EDIT.

Notifications are never created directly through this API - they are
exclusively a byproduct of notify_stage_transition() firing at an
existing workflow transition (see service docstring). There is
deliberately no POST /notifications endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services.export_service import build_export_workbook
from app.services.notification_service import mark_read

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _own_query(db: Session, ctx: CurrentContext):
    """No employee identity (e.g. a technical System Administrator account
    with no linked Employee row, per M4) means no possible notifications -
    an empty, always-false filter rather than a 500 or a scope error."""
    query = db.query(Notification)
    if ctx.employee_id is None:
        return query.filter(Notification.NotificationID.is_(None))
    return query.filter(Notification.EmployeeID == ctx.employee_id)


def _get_own_notification(db: Session, notification_id: int, ctx: CurrentContext) -> Notification:
    notification = _own_query(db, ctx).filter(Notification.NotificationID == notification_id).one_or_none()
    if notification is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Notification not found or not yours")
    return notification


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        notification_id=n.NotificationID, message=n.Message, module=n.Module, is_read=n.IsRead,
        created_at=n.CreatedAt,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("NOTIFICATION.VIEW")),
):
    query = _own_query(db, ctx)
    if unread_only:
        query = query.filter(Notification.IsRead == False)  # noqa: E712
    rows = query.order_by(Notification.CreatedAt.desc()).all()
    return [_to_out(n) for n in rows]


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("NOTIFICATION.VIEW")),
):
    count = _own_query(db, ctx).filter(Notification.IsRead == False).count()  # noqa: E712
    return UnreadCountOut(unread_count=count)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("NOTIFICATION.VIEW")),
):
    notification = _get_own_notification(db, notification_id, ctx)
    mark_read(notification)
    db.commit()
    db.refresh(notification)
    return _to_out(notification)


@router.post("/read-all", response_model=list[NotificationOut])
def mark_all_notifications_read(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("NOTIFICATION.VIEW")),
):
    rows = _own_query(db, ctx).filter(Notification.IsRead == False).all()  # noqa: E712
    for notification in rows:
        mark_read(notification)
    db.commit()
    return [_to_out(n) for n in rows]


@router.get("/export")
def export_notifications(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("NOTIFICATION.VIEW")),
):
    rows = _own_query(db, ctx).order_by(Notification.CreatedAt.desc()).all()
    export_rows = [[n.NotificationID, n.Message, n.Module or "", "Yes" if n.IsRead else "No", n.CreatedAt.isoformat()] for n in rows]

    content = build_export_workbook(
        sheet_title="Notifications",
        headers=["NotificationID", "Message", "Module", "IsRead", "CreatedAt"],
        rows=export_rows, generated_by=ctx.ad_username, context_label="My Notifications",
    )
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=My_Notifications.xlsx"},
    )

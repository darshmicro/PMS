"""
Plant Head Approval endpoints (spec Section 11 / M16). RBAC matrix:
Create/View/Approve/Return for Plant Head only - no Edit column at all,
because there is nothing to edit (see model module docstring: this table
carries no score). MD and HR Administrator get View only; Employee,
Manager, HOD and HR get no access at all to this stage. Two exits, both
labelled arrows on the design doc's workflow diagram:

    PLANT_HEAD_APPROVAL --[approve]--> MD_APPROVAL
    PLANT_HEAD_APPROVAL --[return]--> HR_REVIEW
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.plant_head_approval import APPROVE, RETURN, PlantHeadApproval
from app.schemas.plant_head_approval import PlantHeadApprovalActionRequest, PlantHeadApprovalOut
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition
from app.services.rating_breakdown_service import build_rating_breakdown
from app.services.profile_service import employee_photo_url
from app.services.plant_head_approval_service import (
    HR_REVIEW_STAGE,
    MD_APPROVAL_STAGE,
    ensure_is_reviewing_plant_head,
    ensure_stage_editable,
    get_hr_score,
    stamp_decision,
    validate_return_has_comments,
)

router = APIRouter(prefix="/plant-head-approvals", tags=["plant-head-approvals"])

# Matching HOD Review/HR Review's pattern: this stage's own RBAC row gives
# no access at all to Employee/Manager/HOD/HR, so only Plant Head
# (plant-scoped) and the broader business-admin roles this row actually
# grants VIEW to (MD, HR Administrator) ever hold PLANT_HEAD_APPROVAL.VIEW
# in the first place (enforced by which roles sql/019 actually grants the
# permission to).
BROAD_ACCESS_ROLES = {"MD", "HR_ADMIN", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _apply_scope(query, ctx: CurrentContext):
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return query
    query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
    return query.filter(
        Employee.PlantID.isnot(None),
        Employee.PlantID.in_(
            query.session.query(Employee.PlantID).filter(Employee.EmployeeID == ctx.employee_id)
        ),
    )


def _get_scoped_performance(db: Session, performance_id: int, ctx: CurrentContext) -> EmployeePerformance:
    query = _apply_scope(db.query(EmployeePerformance).filter(EmployeePerformance.PerformanceID == performance_id), ctx)
    performance = query.one_or_none()
    if performance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found or outside your access scope")
    return performance


def _get_or_create_approval(db: Session, performance_id: int) -> PlantHeadApproval:
    approval = db.query(PlantHeadApproval).filter(PlantHeadApproval.PerformanceID == performance_id).one_or_none()
    if approval is None:
        approval = PlantHeadApproval(PerformanceID=performance_id)
        db.add(approval)
        db.flush()
    return approval


def _safe_hr_score(db: Session, performance_id: int) -> float | None:
    try:
        return get_hr_score(db, performance_id)
    except HTTPException:
        return None


def _to_out(
    db: Session, performance: EmployeePerformance, approval: PlantHeadApproval | None, hr_score: float | None
) -> PlantHeadApprovalOut:
    return PlantHeadApprovalOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        employee_photo_url=employee_photo_url(performance.employee),
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, status=performance.Status,
        hr_score=hr_score,
        decision=approval.Decision if approval else None,
        comments=approval.Comments if approval else None,
        actioned_at=approval.ActionedAt if approval else None,
        rating_breakdown=build_rating_breakdown(db, performance.PerformanceID),
    )


@router.get("", response_model=list[PlantHeadApprovalOut])
def list_plant_head_approvals(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("PLANT_HEAD_APPROVAL.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        approval = db.query(PlantHeadApproval).filter(PlantHeadApproval.PerformanceID == performance.PerformanceID).one_or_none()
        results.append(_to_out(db, performance, approval, _safe_hr_score(db, performance.PerformanceID)))
    return results


@router.get("/{performance_id}", response_model=PlantHeadApprovalOut)
def get_plant_head_approval(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PLANT_HEAD_APPROVAL.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    approval = db.query(PlantHeadApproval).filter(PlantHeadApproval.PerformanceID == performance_id).one_or_none()
    return _to_out(db, performance, approval, _safe_hr_score(db, performance_id))


@router.post("/{performance_id}/approve", response_model=PlantHeadApprovalOut)
def approve_and_forward(
    performance_id: int, payload: PlantHeadApprovalActionRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PLANT_HEAD_APPROVAL.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_plant_head(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    hr_score = get_hr_score(db, performance_id)
    approval = _get_or_create_approval(db, performance_id)

    old_status = performance.Status
    performance.Status = MD_APPROVAL_STAGE
    stamp_decision(approval, APPROVE, payload.comments, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="PLANT_HEAD_APPROVAL", record_id=str(performance_id),
        old_value=old_status, new_value=MD_APPROVAL_STAGE, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=MD_APPROVAL_STAGE,
        actioned_by_user_id=ctx.user_id, comments=payload.comments,
    )
    notify_stage_transition(db, performance)
    return _to_out(db, performance, approval, hr_score)


@router.post("/{performance_id}/return", response_model=PlantHeadApprovalOut)
def return_to_hr(
    performance_id: int, payload: PlantHeadApprovalActionRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PLANT_HEAD_APPROVAL.EDIT")),
):
    validate_return_has_comments(payload.comments)

    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_plant_head(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    hr_score = _safe_hr_score(db, performance_id)
    approval = _get_or_create_approval(db, performance_id)

    old_status = performance.Status
    performance.Status = HR_REVIEW_STAGE
    stamp_decision(approval, RETURN, payload.comments, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="PLANT_HEAD_APPROVAL", record_id=str(performance_id),
        old_value=old_status, new_value=HR_REVIEW_STAGE, reason=payload.comments, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=HR_REVIEW_STAGE,
        actioned_by_user_id=ctx.user_id, comments=payload.comments,
    )
    notify_stage_transition(db, performance)
    return _to_out(db, performance, approval, hr_score)


@router.get("/{performance_id}/export")
def export_plant_head_approval(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PLANT_HEAD_APPROVAL.VIEW")),
):
    """Stage-wise export for the Plant Head Approval stage (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    approval = db.query(PlantHeadApproval).filter(PlantHeadApproval.PerformanceID == performance_id).one_or_none()
    hr_score = _safe_hr_score(db, performance_id)

    rows = [[
        performance.employee.FullName, performance.cycle.CycleName,
        hr_score if hr_score is not None else "",
        approval.Decision or "" if approval else "",
        approval.Comments or "" if approval else "",
    ]]

    content = build_export_workbook(
        sheet_title="Plant Head Approval",
        headers=["Employee", "Cycle", "HR Score", "Decision", "Comments"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"Plant Head Approval - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=PLANT_HEAD_APPROVAL, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=Plant_Head_Approval_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

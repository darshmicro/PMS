"""
MD Final Approval endpoints (spec Section 11 / M17). RBAC matrix row is
the narrowest yet: "MD Approval: C,V,A,R" for MD alone, View only for HR
Administrator - not even Plant Head (the immediately preceding stage)
keeps any access here. Employee, Manager, HOD and HR get no access at
all, same as they've had none since HOD Review or HR Review respectively.
Two exits, both labelled arrows on the design doc's workflow diagram:

    MD_APPROVAL --[approve]--> FINAL_APPROVED (record locked in the same step)
    MD_APPROVAL --[return for clarification]--> PLANT_HEAD_APPROVAL
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.md_approval import APPROVE, RETURN, MDApproval
from app.models.plant_head_approval import PlantHeadApproval
from app.schemas.md_approval import MDApprovalActionRequest, MDApprovalOut
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.rating_breakdown_service import build_rating_breakdown
from app.services.profile_service import employee_photo_url
from app.services.md_approval_service import (
    PLANT_HEAD_APPROVAL_STAGE,
    ensure_stage_editable,
    finalize_and_lock,
    get_hr_score,
    stamp_decision,
    validate_return_has_comments,
)
from app.services.scoring_engine_service import run_scoring_engine
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition

router = APIRouter(prefix="/md-approvals", tags=["md-approvals"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_performance(db: Session, performance_id: int) -> EmployeePerformance:
    """No _apply_scope needed here (mirroring HR Review/M15's reasoning):
    MD Approval is a single, org-wide top-level sign-off, not scoped to
    any department/plant/reporting line - the permission grant itself
    (MD_APPROVAL.VIEW/.EDIT) is the only access control."""
    performance = db.get(EmployeePerformance, performance_id)
    if performance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return performance


def _get_or_create_approval(db: Session, performance_id: int) -> MDApproval:
    approval = db.query(MDApproval).filter(MDApproval.PerformanceID == performance_id).one_or_none()
    if approval is None:
        approval = MDApproval(PerformanceID=performance_id)
        db.add(approval)
        db.flush()
    return approval


def _safe_hr_score(db: Session, performance_id: int) -> float | None:
    try:
        return get_hr_score(db, performance_id)
    except HTTPException:
        return None


def _to_out(db: Session, performance: EmployeePerformance, approval: MDApproval | None, hr_score: float | None) -> MDApprovalOut:
    breakdown = build_rating_breakdown(db, performance.PerformanceID)
    plant_head = (
        db.query(PlantHeadApproval).filter(PlantHeadApproval.PerformanceID == performance.PerformanceID).one_or_none()
    )
    if plant_head is not None:
        breakdown = breakdown.model_copy(update={
            "plant_head_decision": plant_head.Decision,
            "plant_head_comments": plant_head.Comments,
        })
    return MDApprovalOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        employee_photo_url=employee_photo_url(performance.employee),
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, status=performance.Status, is_locked=performance.IsLocked,
        hr_score=hr_score,
        decision=approval.Decision if approval else None,
        comments=approval.Comments if approval else None,
        actioned_at=approval.ActionedAt if approval else None,
        rating_breakdown=breakdown,
    )


@router.get("", response_model=list[MDApprovalOut])
def list_md_approvals(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MD_APPROVAL.VIEW")),
):
    query = db.query(EmployeePerformance)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        approval = db.query(MDApproval).filter(MDApproval.PerformanceID == performance.PerformanceID).one_or_none()
        results.append(_to_out(db, performance, approval, _safe_hr_score(db, performance.PerformanceID)))
    return results


@router.get("/{performance_id}", response_model=MDApprovalOut)
def get_md_approval(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MD_APPROVAL.VIEW")),
):
    performance = _get_performance(db, performance_id)
    approval = db.query(MDApproval).filter(MDApproval.PerformanceID == performance_id).one_or_none()
    return _to_out(db, performance, approval, _safe_hr_score(db, performance_id))


@router.post("/{performance_id}/approve", response_model=MDApprovalOut)
def approve_and_finalize(
    performance_id: int, payload: MDApprovalActionRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MD_APPROVAL.EDIT")),
):
    performance = _get_performance(db, performance_id)
    ensure_stage_editable(performance)

    hr_score = get_hr_score(db, performance_id)
    approval = _get_or_create_approval(db, performance_id)

    old_status = performance.Status
    stamp_decision(approval, APPROVE, payload.comments, ctx.user_id)
    finalize_and_lock(performance)
    # M18 hook point (see md_approval_service.finalize_and_lock's own
    # docstring, and scoring_engine_service's module docstring): the
    # Scoring Engine runs exactly here, in the same transaction, so an
    # incomplete-data failure (e.g. an assigned-but-unscored competency)
    # rolls the whole approval back rather than leaving a locked record
    # with no Final Score/Rating.
    run_scoring_engine(db, performance, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="MD_APPROVAL", record_id=str(performance_id),
        old_value=old_status, new_value=f"{performance.Status} (locked)", ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=performance.Status,
        actioned_by_user_id=ctx.user_id, comments=payload.comments,
    )
    notify_stage_transition(db, performance)
    return _to_out(db, performance, approval, hr_score)


@router.post("/{performance_id}/return", response_model=MDApprovalOut)
def return_to_plant_head(
    performance_id: int, payload: MDApprovalActionRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MD_APPROVAL.EDIT")),
):
    validate_return_has_comments(payload.comments)

    performance = _get_performance(db, performance_id)
    ensure_stage_editable(performance)

    hr_score = _safe_hr_score(db, performance_id)
    approval = _get_or_create_approval(db, performance_id)

    old_status = performance.Status
    performance.Status = PLANT_HEAD_APPROVAL_STAGE
    stamp_decision(approval, RETURN, payload.comments, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="MD_APPROVAL", record_id=str(performance_id),
        old_value=old_status, new_value=PLANT_HEAD_APPROVAL_STAGE, reason=payload.comments, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=PLANT_HEAD_APPROVAL_STAGE,
        actioned_by_user_id=ctx.user_id, comments=payload.comments,
    )
    notify_stage_transition(db, performance)
    return _to_out(db, performance, approval, hr_score)


@router.get("/{performance_id}/export")
def export_md_approval(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MD_APPROVAL.VIEW")),
):
    """Stage-wise export for the MD Approval stage (spec Section 36A)."""
    performance = _get_performance(db, performance_id)
    approval = db.query(MDApproval).filter(MDApproval.PerformanceID == performance_id).one_or_none()
    hr_score = _safe_hr_score(db, performance_id)

    rows = [[
        performance.employee.FullName, performance.cycle.CycleName,
        hr_score if hr_score is not None else "",
        approval.Decision or "" if approval else "",
        approval.Comments or "" if approval else "",
        "Yes" if performance.IsLocked else "No",
    ]]

    content = build_export_workbook(
        sheet_title="MD Approval",
        headers=["Employee", "Cycle", "HR Score", "Decision", "Comments", "Locked"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"MD Approval - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=MD_APPROVAL, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=MD_Approval_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

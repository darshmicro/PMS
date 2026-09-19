"""
HR Review & Calibration endpoints (spec Section 11 / M15). RBAC matrix:
Create/View/Edit for HR alone (unlike every stage since M13, no other role
- not even HR Administrator, Plant Head or MD, who get View only here -
holds Edit). Employee, Manager and HOD get no access at all, matching
HOD Review's pattern from M14. HR reviews org-wide, not scoped to any
department or reporting line, so unlike every prior module there is no
per-record ownership check beyond the permission grant itself.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.hr_review import HRReview
from app.schemas.hr_review import HRReviewOut, HRReviewUpdate
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition
from app.services.rating_breakdown_service import build_rating_breakdown
from app.services.profile_service import employee_photo_url
from app.services.hr_review_service import (
    PLANT_HEAD_APPROVAL_STAGE,
    compute_hr_score,
    ensure_complete_ready,
    ensure_stage_editable,
    get_hod_score,
    stamp_completed,
    validate_calibration_adjustment_reason,
    validate_hr_score_bounds,
)

router = APIRouter(prefix="/hr-reviews", tags=["hr-reviews"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _get_performance(db: Session, performance_id: int) -> EmployeePerformance:
    """No _apply_scope needed here (see module docstring) - HR Review
    visibility is org-wide for anyone holding HR_REVIEW.VIEW at all."""
    performance = db.get(EmployeePerformance, performance_id)
    if performance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return performance


def _get_or_create_review(db: Session, performance_id: int) -> HRReview:
    review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    if review is None:
        review = HRReview(PerformanceID=performance_id, CalibrationAdjustment=0)
        db.add(review)
        db.flush()
    return review


def _to_out(
    db: Session, performance: EmployeePerformance, review: HRReview | None, hod_score: float | None
) -> HRReviewOut:
    return HRReviewOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        employee_photo_url=employee_photo_url(performance.employee),
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, status=performance.Status,
        hod_score=hod_score,
        calibration_adjustment=float(review.CalibrationAdjustment) if review else 0.0,
        hr_score=review.HRScore if review else None,
        adjustment_reason=review.AdjustmentReason if review else None,
        hr_comments=review.HRComments if review else None,
        training_recommendation=review.TrainingRecommendation if review else None,
        career_development_recommendation=review.CareerDevelopmentRecommendation if review else None,
        actioned_at=review.ActionedAt if review else None,
        rating_breakdown=build_rating_breakdown(db, performance.PerformanceID),
    )


def _safe_hod_score(db: Session, performance_id: int) -> float | None:
    try:
        return get_hod_score(db, performance_id)
    except HTTPException:
        return None


@router.get("", response_model=list[HRReviewOut])
def list_hr_reviews(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("HR_REVIEW.VIEW")),
):
    query = db.query(EmployeePerformance)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        review = db.query(HRReview).filter(HRReview.PerformanceID == performance.PerformanceID).one_or_none()
        results.append(_to_out(db, performance, review, _safe_hod_score(db, performance.PerformanceID)))
    return results


@router.get("/{performance_id}", response_model=HRReviewOut)
def get_hr_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HR_REVIEW.VIEW")),
):
    performance = _get_performance(db, performance_id)
    review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    return _to_out(db, performance, review, _safe_hod_score(db, performance_id))


@router.put("/{performance_id}", response_model=HRReviewOut)
def update_hr_review(
    performance_id: int, payload: HRReviewUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HR_REVIEW.EDIT")),
):
    performance = _get_performance(db, performance_id)
    ensure_stage_editable(performance)

    hod_score = get_hod_score(db, performance_id)
    review = _get_or_create_review(db, performance_id)

    old_value = f"CalibrationAdjustment={review.CalibrationAdjustment}, HRScore={review.HRScore}"

    if payload.hr_comments is not None:
        review.HRComments = payload.hr_comments
    if payload.training_recommendation is not None:
        review.TrainingRecommendation = payload.training_recommendation
    if payload.career_development_recommendation is not None:
        review.CareerDevelopmentRecommendation = payload.career_development_recommendation
    if payload.adjustment_reason is not None:
        review.AdjustmentReason = payload.adjustment_reason

    # HRScore is always fully recomputed from the current adjustment (new
    # if supplied this call, otherwise whatever was already stored) so it
    # can never drift out of sync with CalibrationAdjustment, and the
    # mandatory-reason rule is re-checked against that same up-to-date pair
    # every time - even a PUT that only touches comments still re-validates.
    new_adjustment = (
        payload.calibration_adjustment if payload.calibration_adjustment is not None
        else float(review.CalibrationAdjustment)
    )
    validate_calibration_adjustment_reason(new_adjustment, review.AdjustmentReason)
    new_score = compute_hr_score(hod_score, new_adjustment)
    validate_hr_score_bounds(new_score)
    review.CalibrationAdjustment = new_adjustment
    review.HRScore = new_score

    review.UpdatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="HR_REVIEW", record_id=str(review.HRReviewID),
        old_value=old_value,
        new_value=f"CalibrationAdjustment={review.CalibrationAdjustment}, HRScore={review.HRScore}",
        ip_address=_client_ip(request),
    )
    return _to_out(db, performance, review, hod_score)


@router.post("/{performance_id}/complete", response_model=HRReviewOut)
def complete_calibration(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HR_REVIEW.EDIT")),
):
    performance = _get_performance(db, performance_id)
    ensure_stage_editable(performance)

    hod_score = get_hod_score(db, performance_id)
    review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    ensure_complete_ready(review)
    validate_calibration_adjustment_reason(float(review.CalibrationAdjustment), review.AdjustmentReason)

    old_status = performance.Status
    performance.Status = PLANT_HEAD_APPROVAL_STAGE
    stamp_completed(review, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="HR_REVIEW", record_id=str(performance_id),
        old_value=old_status, new_value=PLANT_HEAD_APPROVAL_STAGE, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=PLANT_HEAD_APPROVAL_STAGE,
        actioned_by_user_id=ctx.user_id,
    )
    notify_stage_transition(db, performance)
    return _to_out(db, performance, review, hod_score)


@router.get("/{performance_id}/export")
def export_hr_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HR_REVIEW.VIEW")),
):
    """Stage-wise export for the HR Review stage (spec Section 36A)."""
    performance = _get_performance(db, performance_id)
    review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    hod_score = _safe_hod_score(db, performance_id)

    rows = [[
        performance.employee.FullName, performance.cycle.CycleName,
        hod_score if hod_score is not None else "",
        float(review.CalibrationAdjustment) if review else 0.0,
        review.HRScore if review and review.HRScore is not None else "",
        review.AdjustmentReason or "" if review else "",
        review.HRComments or "" if review else "",
        review.TrainingRecommendation or "" if review else "",
        review.CareerDevelopmentRecommendation or "" if review else "",
    ]]

    content = build_export_workbook(
        sheet_title="HR Review",
        headers=[
            "Employee", "Cycle", "HOD Score", "Calibration Adjustment", "HR Score", "Adjustment Reason",
            "HR Comments", "Training Recommendation", "Career Development Recommendation",
        ],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"HR Review - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=HR_REVIEW, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=HR_Review_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

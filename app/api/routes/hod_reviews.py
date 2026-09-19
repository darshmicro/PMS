"""
HOD Review endpoints (spec Section 11 / M14). RBAC matrix: HOD Review is
Create/View/Edit/Approve/Return for HOD only - Employee and Manager get no
access at all here (not even View), and HR/Plant Head/MD/HR Administrator
get View only. Three possible exits, each a distinct labelled arrow on the
design doc's workflow diagram:

    HOD_REVIEW --[approve & forward]--> HR_REVIEW
    HOD_REVIEW --[return to manager]--> MANAGER_REVIEW
    HOD_REVIEW --[return to employee]--> SELF_ASSESSMENT
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.hod_review import APPROVE_FORWARD, RETURN_TO_EMPLOYEE, RETURN_TO_MANAGER, HODReview
from app.models.manager_review import ManagerReview
from app.models.self_assessment import RETURNED as SA_RETURNED
from app.models.self_assessment import SelfAssessment
from app.schemas.hod_review import HODReviewOut, HODReviewReturnRequest, HODReviewUpdate
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition
from app.services.rating_breakdown_service import build_rating_breakdown
from app.services.profile_service import employee_photo_url
from app.services.hod_review_service import (
    HR_REVIEW_STAGE,
    MANAGER_REVIEW_STAGE,
    SELF_ASSESSMENT_STAGE,
    compute_manager_weighted_score_pct,
    ensure_approve_ready,
    ensure_is_reviewing_hod,
    ensure_stage_editable,
    stamp_action,
    validate_hod_score,
    validate_override_has_comments,
)

router = APIRouter(prefix="/hod-reviews", tags=["hod-reviews"])

# Unlike assignments.py/self_assessments.py/manager_reviews.py, this
# module's own RBAC row grants no access at all to Employee or Manager, so
# there is no self/reports branch here - only HOD (dept-scoped) and the
# broad business-admin roles ever hold HOD_REVIEW.VIEW/EDIT in the first
# place (enforced by which roles sql/015 actually grants the permission to).
BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _apply_scope(query, ctx: CurrentContext):
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return query
    query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
    return query.filter(Employee.HODID == ctx.employee_id)


def _get_scoped_performance(db: Session, performance_id: int, ctx: CurrentContext) -> EmployeePerformance:
    query = _apply_scope(db.query(EmployeePerformance).filter(EmployeePerformance.PerformanceID == performance_id), ctx)
    performance = query.one_or_none()
    if performance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found or outside your access scope")
    return performance


def _manager_reviews_for(db: Session, performance_id: int) -> list[ManagerReview]:
    return (
        db.query(ManagerReview)
        .join(EmployeeKPI, ManagerReview.EmployeeKPIID == EmployeeKPI.EmployeeKPIID)
        .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .filter(EmployeeKPA.PerformanceID == performance_id)
        .all()
    )


def _self_assessments_for(db: Session, performance_id: int) -> list[SelfAssessment]:
    return (
        db.query(SelfAssessment)
        .join(EmployeeKPI, SelfAssessment.EmployeeKPIID == EmployeeKPI.EmployeeKPIID)
        .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .filter(EmployeeKPA.PerformanceID == performance_id)
        .all()
    )


def _get_or_create_review(db: Session, performance_id: int) -> HODReview:
    review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    if review is None:
        review = HODReview(PerformanceID=performance_id)
        db.add(review)
        db.flush()
    return review


def _to_out(
    db: Session, performance: EmployeePerformance, review: HODReview | None, reference_pct: float | None
) -> HODReviewOut:
    return HODReviewOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        employee_photo_url=employee_photo_url(performance.employee),
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, status=performance.Status,
        manager_weighted_score_pct=reference_pct,
        hod_score=review.HODScore if review else None,
        hod_comments=review.HODComments if review else None,
        development_recommendation=review.DevelopmentRecommendation if review else None,
        training_requirement=review.TrainingRequirement if review else None,
        action=review.Action if review else None,
        actioned_at=review.ActionedAt if review else None,
        rating_breakdown=build_rating_breakdown(db, performance.PerformanceID),
    )


@router.get("", response_model=list[HODReviewOut])
def list_hod_reviews(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        review = db.query(HODReview).filter(HODReview.PerformanceID == performance.PerformanceID).one_or_none()
        reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance.PerformanceID))
        results.append(_to_out(db, performance, review, reference_pct))
    return results


@router.get("/{performance_id}", response_model=HODReviewOut)
def get_hod_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance_id))
    return _to_out(db, performance, review, reference_pct)


@router.put("/{performance_id}", response_model=HODReviewOut)
def update_hod_review(
    performance_id: int, payload: HODReviewUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_hod(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    review = _get_or_create_review(db, performance_id)
    reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance_id))

    old_value = f"HODScore={review.HODScore}"

    if payload.hod_comments is not None:
        review.HODComments = payload.hod_comments
    if payload.development_recommendation is not None:
        review.DevelopmentRecommendation = payload.development_recommendation
    if payload.training_requirement is not None:
        review.TrainingRequirement = payload.training_requirement
    if payload.hod_score is not None:
        validate_hod_score(payload.hod_score)
        validate_override_has_comments(payload.hod_score, reference_pct, payload.hod_comments or review.HODComments)
        review.HODScore = payload.hod_score

    review.UpdatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="HOD_REVIEW", record_id=str(review.HODReviewID),
        old_value=old_value, new_value=f"HODScore={review.HODScore}", ip_address=_client_ip(request),
    )
    return _to_out(db, performance, review, reference_pct)


@router.post("/{performance_id}/approve", response_model=HODReviewOut)
def approve_and_forward(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_hod(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    ensure_approve_ready(review)

    old_status = performance.Status
    performance.Status = HR_REVIEW_STAGE
    stamp_action(review, APPROVE_FORWARD, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="HOD_REVIEW", record_id=str(performance_id),
        old_value=old_status, new_value=HR_REVIEW_STAGE, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=HR_REVIEW_STAGE,
        actioned_by_user_id=ctx.user_id,
    )
    notify_stage_transition(db, performance)
    reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance_id))
    return _to_out(db, performance, review, reference_pct)


def _do_return(
    performance_id: int, payload: HODReviewReturnRequest, request: Request, db: Session, ctx: CurrentContext,
    target_status: str, action: str, reset_self_assessments: bool,
) -> HODReviewOut:
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A reason is required to return this record")

    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_hod(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    review = _get_or_create_review(db, performance_id)

    old_status = performance.Status
    performance.Status = target_status
    stamp_action(review, action, ctx.user_id)

    if reset_self_assessments:
        for sa in _self_assessments_for(db, performance_id):
            sa.Status = SA_RETURNED
            sa.UpdatedAt = datetime.now(timezone.utc)

    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="HOD_REVIEW", record_id=str(performance_id),
        old_value=old_status, new_value=target_status, reason=payload.reason, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=target_status,
        actioned_by_user_id=ctx.user_id, comments=payload.reason,
    )
    notify_stage_transition(db, performance)
    reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance_id))
    return _to_out(db, performance, review, reference_pct)


@router.post("/{performance_id}/return-to-manager", response_model=HODReviewOut)
def return_to_manager(
    performance_id: int, payload: HODReviewReturnRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.EDIT")),
):
    return _do_return(
        performance_id, payload, request, db, ctx,
        target_status=MANAGER_REVIEW_STAGE, action=RETURN_TO_MANAGER, reset_self_assessments=False,
    )


@router.post("/{performance_id}/return-to-employee", response_model=HODReviewOut)
def return_to_employee(
    performance_id: int, payload: HODReviewReturnRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.EDIT")),
):
    return _do_return(
        performance_id, payload, request, db, ctx,
        target_status=SELF_ASSESSMENT_STAGE, action=RETURN_TO_EMPLOYEE, reset_self_assessments=True,
    )


@router.get("/{performance_id}/export")
def export_hod_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("HOD_REVIEW.VIEW")),
):
    """Stage-wise export for the HOD Review stage (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    reference_pct = compute_manager_weighted_score_pct(performance, _manager_reviews_for(db, performance_id))

    rows = [[
        performance.employee.FullName, performance.cycle.CycleName,
        reference_pct if reference_pct is not None else "",
        review.HODScore if review and review.HODScore is not None else "",
        review.HODComments or "" if review else "",
        review.DevelopmentRecommendation or "" if review else "",
        review.TrainingRequirement or "" if review else "",
        review.Action or "" if review else "",
    ]]

    content = build_export_workbook(
        sheet_title="HOD Review",
        headers=[
            "Employee", "Cycle", "Manager Weighted Score %", "HOD Score", "HOD Comments",
            "Development Recommendation", "Training Requirement", "Action",
        ],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"HOD Review - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=HOD_REVIEW, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=HOD_Review_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

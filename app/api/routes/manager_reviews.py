"""
Manager Review endpoints (spec Section 11 / M13). RBAC matrix: Manager
Review is Create/View/Edit/Return for the employee's own direct Manager
only - HOD/HR/Plant Head/MD/HR Administrator get View only here despite
their broader business-admin rights elsewhere (their own edit rights start
at HOD Review, M14, onward).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.manager_review import RETURN, SUBMIT, ManagerReview
from app.models.self_assessment import RETURNED as SA_RETURNED
from app.models.self_assessment import SelfAssessment
from app.schemas.manager_review import (
    ManagerReviewKPIOut,
    ManagerReviewKPIUpdate,
    ManagerReviewOut,
    ManagerReviewReturnRequest,
)
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.profile_service import employee_photo_url
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition
from app.services.manager_review_service import (
    HOD_REVIEW_STAGE,
    SELF_ASSESSMENT_STAGE,
    ensure_is_reviewing_manager,
    ensure_stage_editable,
    stamp_action,
    validate_manager_score,
    validate_override_has_comments,
    validate_submission_ready,
)

router = APIRouter(prefix="/manager-reviews", tags=["manager-reviews"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _apply_scope(query, ctx: CurrentContext):
    """Same visibility rule as assignments.py/self_assessments.py - kept as
    a local copy per this codebase's established convention of each router
    scoping its own queries independently."""
    if BROAD_ACCESS_ROLES & set(ctx.role_codes):
        return query
    query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
    if "HOD" in ctx.role_codes:
        return query.filter(Employee.HODID == ctx.employee_id)
    if "MANAGER" in ctx.role_codes:
        return query.filter(Employee.ManagerID == ctx.employee_id)
    return query.filter(Employee.EmployeeID == ctx.employee_id)


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


def _to_out(performance: EmployeePerformance, reviews: list[ManagerReview], self_assessments: list[SelfAssessment]) -> ManagerReviewOut:
    reviews_by_kpi = {r.EmployeeKPIID: r for r in reviews}
    self_by_kpi = {s.EmployeeKPIID: s for s in self_assessments}
    kpi_rows: list[ManagerReviewKPIOut] = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            review = reviews_by_kpi.get(kpi.EmployeeKPIID)
            self_assessment = self_by_kpi.get(kpi.EmployeeKPIID)
            kpi_rows.append(
                ManagerReviewKPIOut(
                    employee_kpi_id=kpi.EmployeeKPIID, kpi_id=kpi.KPIID, kpi_name=kpi.kpi.KPIName,
                    weightage=kpi.Weightage,
                    self_achievement=self_assessment.Achievement if self_assessment else None,
                    self_achievement_pct=self_assessment.AchievementPct if self_assessment else None,
                    self_score=self_assessment.SelfScore if self_assessment else None,
                    manager_score=review.ManagerScore if review else None,
                    manager_comments=review.ManagerComments if review else None,
                    development_requirement=review.DevelopmentRequirement if review else None,
                    action=review.Action if review else None,
                    actioned_at=review.ActionedAt if review else None,
                )
            )
    return ManagerReviewOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        employee_photo_url=employee_photo_url(performance.employee),
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, status=performance.Status, kpis=kpi_rows,
    )


@router.get("", response_model=list[ManagerReviewOut])
def list_manager_reviews(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    return [
        _to_out(p, _manager_reviews_for(db, p.PerformanceID), _self_assessments_for(db, p.PerformanceID))
        for p in query.all()
    ]


@router.get("/{performance_id}", response_model=ManagerReviewOut)
def get_manager_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    return _to_out(performance, _manager_reviews_for(db, performance_id), _self_assessments_for(db, performance_id))


@router.put("/{performance_id}/kpis/{employee_kpi_id}", response_model=ManagerReviewKPIOut)
def update_manager_review_kpi(
    performance_id: int, employee_kpi_id: int, payload: ManagerReviewKPIUpdate, request: Request,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_manager(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    employee_kpi = db.get(EmployeeKPI, employee_kpi_id)
    if employee_kpi is None or employee_kpi.employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPI not found on this assignment")

    self_assessment = db.query(SelfAssessment).filter(SelfAssessment.EmployeeKPIID == employee_kpi_id).one_or_none()
    self_score = self_assessment.SelfScore if self_assessment else None

    review = db.query(ManagerReview).filter(ManagerReview.EmployeeKPIID == employee_kpi_id).one_or_none()
    if review is None:
        review = ManagerReview(EmployeeKPIID=employee_kpi_id)
        db.add(review)

    old_value = f"ManagerScore={review.ManagerScore}"

    if payload.manager_comments is not None:
        review.ManagerComments = payload.manager_comments
    if payload.development_requirement is not None:
        review.DevelopmentRequirement = payload.development_requirement
    if payload.manager_score is not None:
        validate_manager_score(payload.manager_score)
        validate_override_has_comments(
            payload.manager_score, self_score, payload.manager_comments or review.ManagerComments
        )
        review.ManagerScore = payload.manager_score

    review.UpdatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="MANAGER_REVIEW", record_id=str(review.ManagerReviewID),
        old_value=old_value, new_value=f"ManagerScore={review.ManagerScore}", ip_address=_client_ip(request),
    )

    return ManagerReviewKPIOut(
        employee_kpi_id=employee_kpi.EmployeeKPIID, kpi_id=employee_kpi.KPIID, kpi_name=employee_kpi.kpi.KPIName,
        weightage=employee_kpi.Weightage,
        self_achievement=self_assessment.Achievement if self_assessment else None,
        self_achievement_pct=self_assessment.AchievementPct if self_assessment else None,
        self_score=self_score, manager_score=review.ManagerScore, manager_comments=review.ManagerComments,
        development_requirement=review.DevelopmentRequirement, action=review.Action, actioned_at=review.ActionedAt,
    )


@router.post("/{performance_id}/submit", response_model=ManagerReviewOut)
def submit_manager_review(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_manager(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    reviews = _manager_reviews_for(db, performance_id)
    self_assessments = _self_assessments_for(db, performance_id)
    validate_submission_ready(performance, reviews, self_assessments)

    old_status = performance.Status
    performance.Status = HOD_REVIEW_STAGE
    stamp_action(reviews, SUBMIT, ctx.user_id)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="MANAGER_REVIEW", record_id=str(performance_id),
        old_value=old_status, new_value=HOD_REVIEW_STAGE, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=HOD_REVIEW_STAGE,
        actioned_by_user_id=ctx.user_id,
    )
    notify_stage_transition(db, performance)
    return _to_out(performance, reviews, self_assessments)


@router.post("/{performance_id}/return", response_model=ManagerReviewOut)
def return_manager_review(
    performance_id: int, payload: ManagerReviewReturnRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.EDIT")),
):
    """Sends the record back to the employee (spec diagram: MANAGER_REVIEW
    -> SELF_ASSESSMENT). Unlike submit(), this does not require every KPI
    to be scored - a manager can return early (e.g. missing evidence)
    without having finished reviewing. A reason is always mandatory,
    recorded on the audit trail rather than added as a new column, since
    Audit_Log already carries a Reason field for exactly this kind of
    "why was this record sent back" justification (established in M3/M4's
    deactivate-requires-reason pattern)."""
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A reason is required to return this record")

    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_is_reviewing_manager(performance, db, ctx.employee_id)
    ensure_stage_editable(performance)

    reviews = _manager_reviews_for(db, performance_id)
    self_assessments = _self_assessments_for(db, performance_id)

    old_status = performance.Status
    performance.Status = SELF_ASSESSMENT_STAGE
    stamp_action(reviews, RETURN, ctx.user_id)
    for sa in self_assessments:
        sa.Status = SA_RETURNED
        sa.UpdatedAt = datetime.now(timezone.utc)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="MANAGER_REVIEW", record_id=str(performance_id),
        old_value=old_status, new_value=SELF_ASSESSMENT_STAGE, reason=payload.reason, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=SELF_ASSESSMENT_STAGE,
        actioned_by_user_id=ctx.user_id, comments=payload.reason,
    )
    notify_stage_transition(db, performance)
    return _to_out(performance, reviews, self_assessments)


@router.get("/{performance_id}/export")
def export_manager_review(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("MANAGER_REVIEW.VIEW")),
):
    """Stage-wise export for the Manager Review stage (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    reviews = {r.EmployeeKPIID: r for r in _manager_reviews_for(db, performance_id)}
    self_assessments = {s.EmployeeKPIID: s for s in _self_assessments_for(db, performance_id)}

    rows = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            review = reviews.get(kpi.EmployeeKPIID)
            sa = self_assessments.get(kpi.EmployeeKPIID)
            rows.append([
                employee_kpa.kpa.KPAName, kpi.kpi.KPIName,
                sa.SelfScore if sa and sa.SelfScore is not None else "",
                review.ManagerScore if review and review.ManagerScore is not None else "",
                review.ManagerComments or "" if review else "",
                review.DevelopmentRequirement or "" if review else "",
                review.Action or "" if review else "",
            ])

    content = build_export_workbook(
        sheet_title="Manager Review",
        headers=["KPA", "KPI", "Self Score", "Manager Score", "Manager Comments", "Development Requirement", "Action"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"Manager Review - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=MANAGER_REVIEW, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=Manager_Review_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

"""
Employee Self-Assessment endpoints (spec Section 11 / M12). Unlike KPA/KPI
Assignment (M11), where a Manager/HR could act on an employee's behalf,
the RBAC matrix gives Create/Edit on "Own Self-Assessment" to the employee
alone - everyone else in the visibility scope (Manager/HOD/HR/Plant
Head/MD/HR Administrator) can only View. So every mutating endpoint here
calls self_assessment_service.ensure_own_record() in addition to the
usual permission check.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance
from app.models.employee import Employee
from app.models.self_assessment import DRAFT, SelfAssessment
from app.schemas.self_assessment import SelfAssessmentKPIOut, SelfAssessmentKPIUpdate, SelfAssessmentOut
from app.services.assignment_service import NUMERIC_TARGET_TYPES
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.workflow_engine_service import record_transition
from app.services.notification_service import notify_stage_transition
from app.services.self_assessment_service import (
    EMPLOYEE_ACKNOWLEDGED,
    KPI_ASSIGNED,
    MANAGER_REVIEW,
    SELF_ASSESSMENT_STAGE,
    compute_achievement_pct,
    ensure_own_record,
    ensure_stage_editable,
    lookup_self_score,
    mark_all_submitted,
    validate_self_score,
    validate_submission_ready,
)

router = APIRouter(prefix="/self-assessments", tags=["self-assessments"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _apply_scope(query, ctx: CurrentContext):
    """Same visibility rule as assignments.py::_apply_scope - kept as a
    local copy rather than a cross-module import, matching this codebase's
    existing convention (employees.py and assignments.py each keep their
    own copy too) of scoping each router's queries independently."""
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


def _self_assessments_for(db: Session, performance_id: int) -> list[SelfAssessment]:
    return (
        db.query(SelfAssessment)
        .join(EmployeeKPI, SelfAssessment.EmployeeKPIID == EmployeeKPI.EmployeeKPIID)
        .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .filter(EmployeeKPA.PerformanceID == performance_id)
        .all()
    )


def _to_out(performance: EmployeePerformance, self_assessments: list[SelfAssessment]) -> SelfAssessmentOut:
    by_kpi_id = {sa.EmployeeKPIID: sa for sa in self_assessments}
    kpi_rows: list[SelfAssessmentKPIOut] = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            sa = by_kpi_id.get(kpi.EmployeeKPIID)
            kpi_rows.append(
                SelfAssessmentKPIOut(
                    employee_kpi_id=kpi.EmployeeKPIID,
                    kpi_id=kpi.KPIID,
                    kpi_name=kpi.kpi.KPIName,
                    measurement_type=kpi.MeasurementType,
                    target=kpi.Target,
                    weightage=kpi.Weightage,
                    achievement=sa.Achievement if sa else None,
                    achievement_pct=sa.AchievementPct if sa else None,
                    self_score=sa.SelfScore if sa else None,
                    employee_comments=sa.EmployeeComments if sa else None,
                    development_need=sa.DevelopmentNeed if sa else None,
                    status=sa.Status if sa else DRAFT,
                    submitted_at=sa.SubmittedAt if sa else None,
                )
            )
    return SelfAssessmentOut(
        performance_id=performance.PerformanceID,
        employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName,
        cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName,
        status=performance.Status,
        kpis=kpi_rows,
    )


@router.get("", response_model=list[SelfAssessmentOut])
def list_self_assessments(
    employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        results.append(_to_out(performance, _self_assessments_for(db, performance.PerformanceID)))
    return results


@router.get("/{performance_id}", response_model=SelfAssessmentOut)
def get_self_assessment(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    return _to_out(performance, _self_assessments_for(db, performance_id))


@router.post("/{performance_id}/acknowledge", response_model=SelfAssessmentOut)
def acknowledge_assignment(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_own_record(performance, ctx.employee_id)

    if performance.Status != KPI_ASSIGNED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Only an assignment in status {KPI_ASSIGNED} can be acknowledged (current: {performance.Status})",
        )

    old_status = performance.Status
    performance.Status = EMPLOYEE_ACKNOWLEDGED

    # Seed one DRAFT Self_Assessment row per assigned KPI, so every KPI has
    # something to update in place afterward.
    existing_kpi_ids = {sa.EmployeeKPIID for sa in _self_assessments_for(db, performance_id)}
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            if kpi.EmployeeKPIID not in existing_kpi_ids:
                db.add(SelfAssessment(EmployeeKPIID=kpi.EmployeeKPIID, Status=DRAFT))

    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="SELF_ASSESSMENT", record_id=str(performance_id),
        old_value=old_status, new_value=EMPLOYEE_ACKNOWLEDGED, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=EMPLOYEE_ACKNOWLEDGED,
        actioned_by_user_id=ctx.user_id,
    )
    notify_stage_transition(db, performance)
    return _to_out(performance, _self_assessments_for(db, performance_id))


@router.put("/{performance_id}/kpis/{employee_kpi_id}", response_model=SelfAssessmentKPIOut)
def update_self_assessment_kpi(
    performance_id: int, employee_kpi_id: int, payload: SelfAssessmentKPIUpdate, request: Request,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_own_record(performance, ctx.employee_id)
    ensure_stage_editable(performance)

    employee_kpi = db.get(EmployeeKPI, employee_kpi_id)
    if employee_kpi is None or employee_kpi.employee_kpa.PerformanceID != performance_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="KPI not found on this assignment")

    self_assessment = (
        db.query(SelfAssessment).filter(SelfAssessment.EmployeeKPIID == employee_kpi_id).one_or_none()
    )
    if self_assessment is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This assignment has not been acknowledged yet - call the acknowledge endpoint first",
        )

    old_value = (
        f"Achievement={self_assessment.Achievement}, SelfScore={self_assessment.SelfScore}"
    )

    if payload.achievement is not None:
        self_assessment.Achievement = payload.achievement
    if payload.employee_comments is not None:
        self_assessment.EmployeeComments = payload.employee_comments
    if payload.development_need is not None:
        self_assessment.DevelopmentNeed = payload.development_need

    if employee_kpi.MeasurementType in NUMERIC_TARGET_TYPES:
        achievement_pct = compute_achievement_pct(employee_kpi.MeasurementType, self_assessment.Achievement, employee_kpi.Target)
        self_assessment.AchievementPct = achievement_pct
        if achievement_pct is not None:
            self_assessment.SelfScore = lookup_self_score(db, employee_kpi.KPIID, achievement_pct)
    else:
        # Non-numeric measurement types have no achievement percentage to
        # derive a score from - the employee supplies SelfScore directly.
        if payload.self_score is not None:
            validate_self_score(payload.self_score)
            self_assessment.SelfScore = payload.self_score

    self_assessment.UpdatedAt = datetime.now(timezone.utc)

    # First edit moves the record from "acknowledged" into "in progress".
    if performance.Status == EMPLOYEE_ACKNOWLEDGED:
        performance.Status = SELF_ASSESSMENT_STAGE

    db.commit()
    db.refresh(self_assessment)
    db.refresh(employee_kpi)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="SELF_ASSESSMENT", record_id=str(self_assessment.SelfAssessmentID),
        old_value=old_value,
        new_value=f"Achievement={self_assessment.Achievement}, SelfScore={self_assessment.SelfScore}",
        ip_address=_client_ip(request),
    )

    return SelfAssessmentKPIOut(
        employee_kpi_id=employee_kpi.EmployeeKPIID, kpi_id=employee_kpi.KPIID, kpi_name=employee_kpi.kpi.KPIName,
        measurement_type=employee_kpi.MeasurementType, target=employee_kpi.Target, weightage=employee_kpi.Weightage,
        achievement=self_assessment.Achievement, achievement_pct=self_assessment.AchievementPct,
        self_score=self_assessment.SelfScore, employee_comments=self_assessment.EmployeeComments,
        development_need=self_assessment.DevelopmentNeed, status=self_assessment.Status,
        submitted_at=self_assessment.SubmittedAt,
    )


@router.post("/{performance_id}/submit", response_model=SelfAssessmentOut)
def submit_self_assessment(
    performance_id: int, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.EDIT")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    ensure_own_record(performance, ctx.employee_id)
    ensure_stage_editable(performance)

    self_assessments = _self_assessments_for(db, performance_id)
    validate_submission_ready(performance, self_assessments)

    old_status = performance.Status
    performance.Status = MANAGER_REVIEW
    mark_all_submitted(db, self_assessments)
    db.commit()
    db.refresh(performance)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="SELF_ASSESSMENT", record_id=str(performance_id),
        old_value=old_status, new_value=MANAGER_REVIEW, ip_address=_client_ip(request),
    )
    record_transition(
        db, performance_id=performance_id, from_status=old_status, to_status=MANAGER_REVIEW,
        actioned_by_user_id=ctx.user_id,
    )
    notify_stage_transition(db, performance)
    return _to_out(performance, _self_assessments_for(db, performance_id))


@router.get("/{performance_id}/export")
def export_self_assessment(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SELF_ASSESSMENT.VIEW")),
):
    """Stage-wise export for the Self-Assessment stage (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    self_assessments = {sa.EmployeeKPIID: sa for sa in _self_assessments_for(db, performance_id)}

    rows = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            sa = self_assessments.get(kpi.EmployeeKPIID)
            rows.append([
                employee_kpa.kpa.KPAName, kpi.kpi.KPIName, kpi.Target if kpi.Target is not None else "",
                sa.Achievement if sa and sa.Achievement is not None else "",
                sa.AchievementPct if sa and sa.AchievementPct is not None else "",
                sa.SelfScore if sa and sa.SelfScore is not None else "",
                sa.EmployeeComments or "" if sa else "",
                sa.Status if sa else DRAFT,
            ])

    content = build_export_workbook(
        sheet_title="Self Assessment",
        headers=["KPA", "KPI", "Target", "Achievement", "Achievement %", "Self Score", "Employee Comments", "Status"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"Self Assessment - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Stage=SELF_ASSESSMENT, Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=Self_Assessment_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

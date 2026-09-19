"""
Development Plan endpoints (spec Section 4.5 / M20). No RBAC matrix row
exists for this module (see model docstring) - authorship reuses
ASSIGNMENT.EDIT/.VIEW's exact role split from M11 (Manager/HOD/HR/Plant
Head/MD/HR Administrator may create/edit; Employee gets View only, self
scope, matching Section 7's "My Development Plan" screen). Scoping
mirrors assignments.py/scoring_engine.py/workflow_engine.py's own
_apply_scope (self/reports/dept/broad-access).

No stage/lock gate on create or edit - see the model's own docstring for
why (a development plan's tracked lifetime routinely outlives the
appraisal cycle that created it).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.development_plan import PENDING, DevelopmentPlan
from app.models.employee import Employee
from app.schemas.development_plan import DevelopmentPlanCreate, DevelopmentPlanOut, DevelopmentPlanUpdate
from app.services.audit_service import write_audit
from app.services.development_plan_service import stamp_updated, validate_completion_status
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/development-plans", tags=["development-plans"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _apply_scope(query, ctx: CurrentContext):
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


def _get_scoped_plan(db: Session, dev_plan_id: int, ctx: CurrentContext) -> tuple[DevelopmentPlan, EmployeePerformance]:
    plan = db.get(DevelopmentPlan, dev_plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Development Plan not found")
    performance = _get_scoped_performance(db, plan.PerformanceID, ctx)
    return plan, performance


def _to_out(plan: DevelopmentPlan, performance: EmployeePerformance) -> DevelopmentPlanOut:
    return DevelopmentPlanOut(
        dev_plan_id=plan.DevPlanID, performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName, cycle_id=performance.CycleID, cycle_name=performance.cycle.CycleName,
        development_area=plan.DevelopmentArea, skill_gap=plan.SkillGap, training_required=plan.TrainingRequired,
        action_plan=plan.ActionPlan, responsible_person_id=plan.ResponsiblePersonID,
        responsible_person_name=plan.responsible_person.FullName if plan.responsible_person else None,
        target_date=plan.TargetDate, completion_status=plan.CompletionStatus, review_comments=plan.ReviewComments,
        created_at=plan.CreatedAt, updated_at=plan.UpdatedAt,
    )


@router.get("", response_model=list[DevelopmentPlanOut])
def list_development_plans(
    performance_id: int | None = None, employee_id: int | None = None, cycle_id: int | None = None,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("DEVELOPMENT_PLAN.VIEW")),
):
    query = _apply_scope(db.query(EmployeePerformance), ctx)
    if performance_id is not None:
        query = query.filter(EmployeePerformance.PerformanceID == performance_id)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    results = []
    for performance in query.all():
        for plan in db.query(DevelopmentPlan).filter(DevelopmentPlan.PerformanceID == performance.PerformanceID).all():
            results.append(_to_out(plan, performance))
    return results


@router.get("/{dev_plan_id}", response_model=DevelopmentPlanOut)
def get_development_plan(
    dev_plan_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("DEVELOPMENT_PLAN.VIEW")),
):
    plan, performance = _get_scoped_plan(db, dev_plan_id, ctx)
    return _to_out(plan, performance)


@router.post("", response_model=DevelopmentPlanOut, status_code=status.HTTP_201_CREATED)
def create_development_plan(
    payload: DevelopmentPlanCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("DEVELOPMENT_PLAN.EDIT")),
):
    performance = _get_scoped_performance(db, payload.performance_id, ctx)

    plan = DevelopmentPlan(
        PerformanceID=performance.PerformanceID, DevelopmentArea=payload.development_area,
        SkillGap=payload.skill_gap, TrainingRequired=payload.training_required, ActionPlan=payload.action_plan,
        ResponsiblePersonID=payload.responsible_person_id, TargetDate=payload.target_date,
        CompletionStatus=PENDING, ReviewComments=payload.review_comments,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="DEVELOPMENT_PLAN", record_id=str(plan.DevPlanID),
        new_value=f"SkillGap={plan.SkillGap}, TrainingRequired={plan.TrainingRequired}", ip_address=_client_ip(request),
    )
    return _to_out(plan, performance)


@router.put("/{dev_plan_id}", response_model=DevelopmentPlanOut)
def update_development_plan(
    dev_plan_id: int, payload: DevelopmentPlanUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("DEVELOPMENT_PLAN.EDIT")),
):
    plan, performance = _get_scoped_plan(db, dev_plan_id, ctx)
    old_value = f"CompletionStatus={plan.CompletionStatus}, TargetDate={plan.TargetDate}"

    if payload.development_area is not None:
        plan.DevelopmentArea = payload.development_area
    if payload.skill_gap is not None:
        plan.SkillGap = payload.skill_gap
    if payload.training_required is not None:
        plan.TrainingRequired = payload.training_required
    if payload.action_plan is not None:
        plan.ActionPlan = payload.action_plan
    if payload.responsible_person_id is not None:
        plan.ResponsiblePersonID = payload.responsible_person_id
    if payload.target_date is not None:
        plan.TargetDate = payload.target_date
    if payload.review_comments is not None:
        plan.ReviewComments = payload.review_comments
    if payload.completion_status is not None:
        validate_completion_status(payload.completion_status)
        plan.CompletionStatus = payload.completion_status

    stamp_updated(plan)
    db.commit()
    db.refresh(plan)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="DEVELOPMENT_PLAN", record_id=str(plan.DevPlanID),
        old_value=old_value, new_value=f"CompletionStatus={plan.CompletionStatus}, TargetDate={plan.TargetDate}",
        ip_address=_client_ip(request),
    )
    return _to_out(plan, performance)


@router.get("/performance/{performance_id}/export")
def export_development_plans(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("DEVELOPMENT_PLAN.VIEW")),
):
    """Stage-wise export for Development Plans (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    plans = db.query(DevelopmentPlan).filter(DevelopmentPlan.PerformanceID == performance_id).all()

    rows = [
        [
            performance.employee.FullName, performance.cycle.CycleName,
            p.DevelopmentArea or "", p.SkillGap or "", p.TrainingRequired or "", p.ActionPlan or "",
            p.responsible_person.FullName if p.responsible_person else "",
            p.TargetDate.isoformat() if p.TargetDate else "", p.CompletionStatus, p.ReviewComments or "",
        ]
        for p in plans
    ]

    content = build_export_workbook(
        sheet_title="Development Plans",
        headers=[
            "Employee", "Cycle", "Development Area", "Skill Gap", "Training Required", "Action Plan",
            "Responsible Person", "Target Date", "Completion Status", "Review Comments",
        ],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"Development Plans - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=Development_Plans_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

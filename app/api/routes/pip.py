"""
PIP endpoints (spec Section 4.5 / M21). No RBAC matrix row exists for
this module (see model docstring) - HR (plus Plant Head/MD/HR
Administrator) may create/edit/close any PIP; the assigned manager
(PIP.ManagerID) may edit/close only PIPs assigned to them; the PIP's
subject employee may view their own only. Unlike every other module's
_apply_scope (which joins through Employee_Performance), this one filters
PIP directly - there's no appraisal record in the picture at all.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.pip import PIP
from app.schemas.pip import PIPCloseRequest, PIPCreate, PIPOut, PIPUpdate
from app.services.audit_service import write_audit
from app.services.export_service import build_export_workbook
from app.services.pip_service import close_pip, ensure_can_act, ensure_open, stamp_updated

router = APIRouter(prefix="/pip", tags=["pip"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _is_broad_access(ctx: CurrentContext) -> bool:
    return bool(BROAD_ACCESS_ROLES & set(ctx.role_codes))


def _apply_scope(query, ctx: CurrentContext):
    if _is_broad_access(ctx):
        return query
    if "MANAGER" in ctx.role_codes:
        return query.filter(PIP.ManagerID == ctx.employee_id)
    return query.filter(PIP.EmployeeID == ctx.employee_id)


def _get_scoped_pip(db: Session, pip_id: int, ctx: CurrentContext) -> PIP:
    pip = _apply_scope(db.query(PIP).filter(PIP.PIPID == pip_id), ctx).one_or_none()
    if pip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="PIP not found or outside your access scope")
    return pip


def _to_out(pip: PIP) -> PIPOut:
    return PIPOut(
        pip_id=pip.PIPID, employee_id=pip.EmployeeID, employee_name=pip.employee.FullName,
        performance_gap=pip.PerformanceGap, expected_performance=pip.ExpectedPerformance,
        improvement_target=pip.ImprovementTarget, action_plan=pip.ActionPlan, training=pip.Training,
        manager_id=pip.ManagerID, manager_name=pip.manager.FullName if pip.manager else None,
        review_date=pip.ReviewDate, pip_start_date=pip.PIPStartDate, pip_end_date=pip.PIPEndDate,
        outcome=pip.Outcome, comments=pip.Comments, created_at=pip.CreatedAt, updated_at=pip.UpdatedAt,
    )


@router.get("", response_model=list[PIPOut])
def list_pips(
    employee_id: int | None = None, open_only: bool = False,
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("PIP.VIEW")),
):
    query = _apply_scope(db.query(PIP), ctx)
    if employee_id is not None:
        query = query.filter(PIP.EmployeeID == employee_id)
    if open_only:
        query = query.filter(PIP.Outcome.is_(None))
    return [_to_out(p) for p in query.all()]


@router.get("/{pip_id}", response_model=PIPOut)
def get_pip(pip_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("PIP.VIEW"))):
    return _to_out(_get_scoped_pip(db, pip_id, ctx))


@router.post("", response_model=PIPOut, status_code=status.HTTP_201_CREATED)
def create_pip(
    payload: PIPCreate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PIP.EDIT")),
):
    if not _is_broad_access(ctx):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only HR (or an equivalent role) may open a new PIP"
        )
    pip = PIP(
        EmployeeID=payload.employee_id, PerformanceGap=payload.performance_gap,
        ExpectedPerformance=payload.expected_performance, ImprovementTarget=payload.improvement_target,
        ActionPlan=payload.action_plan, Training=payload.training, ManagerID=payload.manager_id,
        ReviewDate=payload.review_date, PIPStartDate=payload.pip_start_date, PIPEndDate=payload.pip_end_date,
    )
    db.add(pip)
    db.commit()
    db.refresh(pip)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="CREATE", module="PIP", record_id=str(pip.PIPID),
        new_value=f"EmployeeID={pip.EmployeeID}, ManagerID={pip.ManagerID}", ip_address=_client_ip(request),
    )
    return _to_out(pip)


@router.put("/{pip_id}", response_model=PIPOut)
def update_pip(
    pip_id: int, payload: PIPUpdate, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PIP.EDIT")),
):
    pip = _get_scoped_pip(db, pip_id, ctx)
    ensure_can_act(pip, ctx.employee_id, _is_broad_access(ctx))
    ensure_open(pip)

    old_value = f"ActionPlan={pip.ActionPlan}"

    if payload.performance_gap is not None:
        pip.PerformanceGap = payload.performance_gap
    if payload.expected_performance is not None:
        pip.ExpectedPerformance = payload.expected_performance
    if payload.improvement_target is not None:
        pip.ImprovementTarget = payload.improvement_target
    if payload.action_plan is not None:
        pip.ActionPlan = payload.action_plan
    if payload.training is not None:
        pip.Training = payload.training
    if payload.manager_id is not None:
        pip.ManagerID = payload.manager_id
    if payload.review_date is not None:
        pip.ReviewDate = payload.review_date
    if payload.pip_start_date is not None:
        pip.PIPStartDate = payload.pip_start_date
    if payload.pip_end_date is not None:
        pip.PIPEndDate = payload.pip_end_date

    stamp_updated(pip)
    db.commit()
    db.refresh(pip)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="EDIT", module="PIP", record_id=str(pip.PIPID),
        old_value=old_value, new_value=f"ActionPlan={pip.ActionPlan}", ip_address=_client_ip(request),
    )
    return _to_out(pip)


@router.post("/{pip_id}/close", response_model=PIPOut)
def close_pip_endpoint(
    pip_id: int, payload: PIPCloseRequest, request: Request, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PIP.EDIT")),
):
    pip = _get_scoped_pip(db, pip_id, ctx)
    ensure_can_act(pip, ctx.employee_id, _is_broad_access(ctx))
    ensure_open(pip)

    old_status = pip.Outcome
    close_pip(pip, payload.outcome, payload.comments)
    db.commit()
    db.refresh(pip)

    write_audit(
        db, user_id=ctx.user_id, ad_username=ctx.ad_username, employee_id=ctx.employee_id,
        action="WORKFLOW_TRANSITION", module="PIP", record_id=str(pip.PIPID),
        old_value=str(old_status), new_value=pip.Outcome, reason=payload.comments, ip_address=_client_ip(request),
    )
    return _to_out(pip)


@router.get("/{pip_id}/export")
def export_pip(pip_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("PIP.VIEW"))):
    """Export for a single PIP (spec Section 36A)."""
    pip = _get_scoped_pip(db, pip_id, ctx)

    rows = [[
        pip.employee.FullName, pip.PerformanceGap or "", pip.ImprovementTarget or "",
        pip.manager.FullName if pip.manager else "",
        pip.PIPStartDate.isoformat() if pip.PIPStartDate else "",
        pip.PIPEndDate.isoformat() if pip.PIPEndDate else "",
        pip.Outcome or "OPEN", pip.Comments or "",
    ]]

    content = build_export_workbook(
        sheet_title="PIP",
        headers=["Employee", "Performance Gap", "Improvement Target", "Manager", "Start Date", "End Date", "Outcome", "Comments"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"PIP - {pip.employee.FullName}",
        filter_criteria=f"Outcome={pip.Outcome or 'OPEN'}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=PIP_{pip.employee.EmployeeCode}_{pip.PIPID}.xlsx"},
    )

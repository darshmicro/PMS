"""
Workflow Engine endpoints (M19). Read-only - see the service module's
docstring for what this module does and, deliberately, does not enforce.
Scoping mirrors assignments.py/scoring_engine.py's own _apply_scope
(self/reports/dept/broad-access): seeing a record's workflow status and
history is the same visibility question as seeing the record itself.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.workflow_history import WorkflowHistory
from app.schemas.workflow_engine import WorkflowHistoryEntryOut, WorkflowStatusOut
from app.services.workflow_engine_service import compute_sla_status, get_next_stages

router = APIRouter(prefix="/workflow-engine", tags=["workflow-engine"])

BROAD_ACCESS_ROLES = {"HR", "HR_ADMIN", "PLANT_HEAD", "MD", "SYS_ADMIN"}


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


@router.get("/{performance_id}/status", response_model=WorkflowStatusOut)
def get_workflow_status(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("WORKFLOW_ENGINE.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    next_stages = get_next_stages(performance.Status)
    sla = compute_sla_status(performance)
    history = (
        db.query(WorkflowHistory)
        .filter(WorkflowHistory.PerformanceID == performance_id)
        .order_by(WorkflowHistory.ActionedAt)
        .all()
    )
    return WorkflowStatusOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName, cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName, current_status=performance.Status, is_locked=performance.IsLocked,
        next_forward_stages=next_stages["forward"], next_return_stages=next_stages["return"],
        window_start=sla.window_start, window_end=sla.window_end,
        is_overdue=sla.is_overdue, days_overdue=sla.days_overdue,
        history=[
            WorkflowHistoryEntryOut(
                from_status=h.FromStatus, to_status=h.ToStatus, actioned_by=h.ActionedBy,
                actioned_at=h.ActionedAt, comments=h.Comments,
            )
            for h in history
        ],
    )

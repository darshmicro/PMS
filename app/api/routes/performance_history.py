"""
Performance History endpoints (spec Section 7 / M27). Two endpoints,
matching the two callers this module has: GET /performance-history/me
(always self, no scope check needed - it is inherently one's own record)
and GET /performance-history/{employee_id} (any other target, gated by
can_view_employee_history - see performance_history_service.py's
docstring for the full reasoning, including why System Administrator is
denied outright).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.employee import Employee
from app.schemas.performance_history import PerformanceHistoryOut
from app.services.performance_history_service import build_history, can_view_employee_history

router = APIRouter(prefix="/performance-history", tags=["performance-history"])


@router.get("/me", response_model=PerformanceHistoryOut)
def my_performance_history(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("PERFORMANCE_HISTORY.VIEW")),
):
    if ctx.employee_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No employee record linked to this account")
    return PerformanceHistoryOut(employee_id=ctx.employee_id, records=build_history(db, ctx.employee_id))


@router.get("/{employee_id}", response_model=PerformanceHistoryOut)
def employee_performance_history(
    employee_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("PERFORMANCE_HISTORY.VIEW")),
):
    target = db.get(Employee, employee_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if not can_view_employee_history(db, ctx, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Outside your performance-history access scope")
    return PerformanceHistoryOut(employee_id=employee_id, records=build_history(db, employee_id))

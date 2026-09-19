"""
Dashboard endpoints (spec Section 5/7 / M24). Two endpoints, matching the
two different shapes the RBAC matrix's "Dashboards" row actually
describes (see service module docstring): GET /dashboard/summary for the
seven business roles (Own/Team/Dept/Org/Plant per role) and GET
/dashboard/system-health for System Administrator's technical-only view.
Each rejects the other's role explicitly, in-handler, rather than via two
separate permission codes - DASHBOARD.VIEW is the single permission every
role holds, and which endpoint applies to which caller is a business rule
(the matrix row itself), not a grant.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.schemas.dashboard import DashboardSummaryOut, SystemHealthOut
from app.services.dashboard_service import apply_dashboard_scope, summarize, system_health

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    cycle_id: int | None = None, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("DASHBOARD.VIEW")),
):
    if "SYS_ADMIN" in ctx.role_codes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="System Administrator has a system-health dashboard, not a business one - see GET /dashboard/system-health",
        )

    query = db.query(EmployeePerformance)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    scoped_query, scope = apply_dashboard_scope(query, ctx)
    records = scoped_query.all()

    data = summarize(db, records, ctx.role_codes)
    return DashboardSummaryOut(scope=scope, **data)


@router.get("/system-health", response_model=SystemHealthOut)
def dashboard_system_health(
    db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_permission("DASHBOARD.VIEW")),
):
    if "SYS_ADMIN" not in ctx.role_codes:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only System Administrator has a system-health dashboard - see GET /dashboard/summary",
        )
    return SystemHealthOut(**system_health(db))

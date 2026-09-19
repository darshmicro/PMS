"""
Scoring Engine endpoints (spec Section 8 / M18). Read-only - this module's
real work happens automatically inside MD Approval's /approve (M17), via
app.services.scoring_engine_service.run_scoring_engine(). This router only
exposes the resulting Performance_Scores/Performance_Ratings for viewing,
scoped the same way as the underlying appraisal record itself (mirroring
assignments.py's own _apply_scope: self/reports/dept/broad-access), since
seeing a final score and rating is a natural extension of the same
visibility every other stage of the same record already has.
"""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_permission
from app.db.base import get_db
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import RatingMaster
from app.models.performance_score import PerformanceRating, PerformanceScore
from app.schemas.scoring_engine import PerformanceRatingOut, PerformanceScoreOut
from app.services.export_service import build_export_workbook

router = APIRouter(prefix="/scoring-engine", tags=["scoring-engine"])

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


def _to_out(db: Session, performance: EmployeePerformance) -> PerformanceRatingOut:
    scores = (
        db.query(PerformanceScore)
        .filter(PerformanceScore.PerformanceID == performance.PerformanceID)
        .order_by(PerformanceScore.CalculatedAt)
        .all()
    )
    rating_row = (
        db.query(PerformanceRating).filter(PerformanceRating.PerformanceID == performance.PerformanceID).one_or_none()
    )
    rating_master = db.get(RatingMaster, rating_row.RatingID) if rating_row else None
    return PerformanceRatingOut(
        performance_id=performance.PerformanceID, employee_id=performance.EmployeeID,
        employee_name=performance.employee.FullName, cycle_id=performance.CycleID,
        cycle_name=performance.cycle.CycleName,
        final_score_pct=performance.FinalScorePct,
        rating_id=performance.FinalRatingID,
        rating_label=rating_master.RatingLabel if rating_master else None,
        finalized_at=rating_row.FinalizedAt if rating_row else None,
        scores=[
            PerformanceScoreOut(score_type=s.ScoreType, score_value=float(s.ScoreValue), calculated_at=s.CalculatedAt)
            for s in scores
        ],
    )


@router.get("/{performance_id}", response_model=PerformanceRatingOut)
def get_scoring_result(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SCORING_ENGINE.VIEW")),
):
    performance = _get_scoped_performance(db, performance_id, ctx)
    return _to_out(db, performance)


@router.get("/{performance_id}/export")
def export_scoring_result(
    performance_id: int, db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_permission("SCORING_ENGINE.VIEW")),
):
    """Stage-wise export for the final score/rating (spec Section 36A)."""
    performance = _get_scoped_performance(db, performance_id, ctx)
    out = _to_out(db, performance)
    score_by_type = {s.score_type: s.score_value for s in out.scores}

    rows = [[
        performance.employee.FullName, performance.cycle.CycleName,
        score_by_type.get("KPI_WEIGHTED", ""), score_by_type.get("COMPETENCY_WEIGHTED", ""),
        out.final_score_pct if out.final_score_pct is not None else "",
        out.rating_label or "",
    ]]

    content = build_export_workbook(
        sheet_title="Final Score & Rating",
        headers=["Employee", "Cycle", "KPI Weighted %", "Competency Weighted %", "Final Score %", "Rating"],
        rows=rows,
        generated_by=ctx.ad_username,
        context_label=f"Scoring Engine - {performance.employee.FullName} ({performance.cycle.CycleName})",
        filter_criteria=f"Status={performance.Status}",
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=Final_Score_{performance.employee.EmployeeCode}_{performance.cycle.CycleName}.xlsx"
        },
    )

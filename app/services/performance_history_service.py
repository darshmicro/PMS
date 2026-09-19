"""
Performance History (spec Section 7 / M27: "read-only historical record
aggregation"). No RBAC matrix row exists for this module either -
Section 5's matrix never mentions it - but Section 7's Employee screen
#8, "My Performance History," gives it a concrete anchor: a read-only,
cross-cycle view of one employee's own past appraisal outcomes.

DESIGN NOTE on what "aggregation" means here: Dashboards (M24) aggregates
*counts* across many employees' current records; Reports (M25) produces a
*roster* of current records, one row each. Neither drills into a single
record's own history. This module does the opposite: for one employee,
across every cycle they've ever been appraised in, it pulls together
three things that already exist but have never been assembled in one
place before - the Employee_Performance summary itself (status, final
score, final rating, lock state), the Performance_Scores breakdown
(KPI_WEIGHTED/COMPETENCY_WEIGHTED/FINAL, from M18's scoring engine) and
the Workflow_History timeline (every stage transition the record went
through, from M19) - giving a genuine "how did we get to this score, and
when" history per record, not just a list of past cycles.

DESIGN NOTE on visibility: with no matrix row to read literally (unlike
Dashboards/Reports, which had one each), this module reuses M24's
apply_dashboard_scope-equivalent tiering rather than inventing a sixth
version of self/team/dept/org/plant - but as a single-employee boolean
check (can_view_employee_history), not a list-level SQL filter, since
GET /performance-history/{employee_id} always names exactly one employee
up front rather than asking "which of many records can I see." System
Administrator is denied outright (mirrors M25's Reports & Exports, not
M24's Dashboards system-health carve-out) - performance history is
business content (scores, ratings), and this codebase's running
principle since M2 is that System Administrator "has no business
approval rights."
"""
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext
from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.performance_masters import RatingMaster
from app.models.performance_score import PerformanceScore
from app.models.workflow_history import WorkflowHistory


def can_view_employee_history(db: Session, ctx: CurrentContext, target_employee: Employee) -> bool:
    role_codes = set(ctx.role_codes)
    if "SYS_ADMIN" in role_codes:
        return False
    if role_codes & {"HR", "MD", "HR_ADMIN"}:
        return True
    if "PLANT_HEAD" in role_codes:
        acting = db.get(Employee, ctx.employee_id) if ctx.employee_id is not None else None
        return (
            acting is not None and acting.PlantID is not None
            and target_employee.PlantID is not None and acting.PlantID == target_employee.PlantID
        )
    if "HOD" in role_codes:
        return ctx.employee_id is not None and target_employee.HODID == ctx.employee_id
    if "MANAGER" in role_codes:
        return ctx.employee_id is not None and target_employee.ManagerID == ctx.employee_id
    return ctx.employee_id is not None and target_employee.EmployeeID == ctx.employee_id


def build_history(db: Session, employee_id: int) -> list[dict]:
    records = (
        db.query(EmployeePerformance)
        .filter(EmployeePerformance.EmployeeID == employee_id)
        .order_by(EmployeePerformance.CreatedAt.asc())
        .all()
    )
    if not records:
        return []

    performance_ids = [r.PerformanceID for r in records]
    scores_by_performance: dict[int, list[PerformanceScore]] = {pid: [] for pid in performance_ids}
    for score in (
        db.query(PerformanceScore).filter(PerformanceScore.PerformanceID.in_(performance_ids))
        .order_by(PerformanceScore.CalculatedAt.asc()).all()
    ):
        scores_by_performance[score.PerformanceID].append(score)

    transitions_by_performance: dict[int, list[WorkflowHistory]] = {pid: [] for pid in performance_ids}
    for transition in (
        db.query(WorkflowHistory).filter(WorkflowHistory.PerformanceID.in_(performance_ids))
        .order_by(WorkflowHistory.ActionedAt.asc()).all()
    ):
        transitions_by_performance[transition.PerformanceID].append(transition)

    rating_ids = {r.FinalRatingID for r in records if r.FinalRatingID is not None}
    rating_labels = {
        rating.RatingID: rating.RatingLabel
        for rating in (db.query(RatingMaster).filter(RatingMaster.RatingID.in_(rating_ids)).all() if rating_ids else [])
    }

    history = []
    for r in records:
        history.append({
            "performance_id": r.PerformanceID,
            "cycle_name": r.cycle.CycleName,
            "status": r.Status,
            "final_score_pct": float(r.FinalScorePct) if r.FinalScorePct is not None else None,
            "final_rating_label": rating_labels.get(r.FinalRatingID) if r.FinalRatingID is not None else None,
            "is_locked": r.IsLocked,
            "score_breakdown": [
                {"score_type": s.ScoreType, "score_value": float(s.ScoreValue)}
                for s in scores_by_performance[r.PerformanceID]
            ],
            "transitions": [
                {
                    "from_status": t.FromStatus, "to_status": t.ToStatus, "actioned_at": t.ActionedAt,
                    "comments": t.Comments,
                }
                for t in transitions_by_performance[r.PerformanceID]
            ],
        })
    return history

"""
HOD Review business rules (spec Section 11 / M14). See the model module's
docstring for the design note on why this is a whole-record review (one
HODScore per Employee_Performance) rather than per-KPI, and how the
Section 8.2 weighted formula is reused here as a reference figure.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hod_review import HODReview
from app.models.manager_review import ManagerReview
from app.services.workflow_engine_service import ensure_within_stage_window

MANAGER_REVIEW_STAGE = "MANAGER_REVIEW"
HOD_REVIEW_STAGE = "HOD_REVIEW"
HR_REVIEW_STAGE = "HR_REVIEW"
SELF_ASSESSMENT_STAGE = "SELF_ASSESSMENT"

SCORE_TOLERANCE = 0.01


def compute_manager_weighted_score_pct(performance: EmployeePerformance, manager_reviews: list[ManagerReview]) -> float | None:
    """Section 8.2: Weighted KPI Score % = KPIScore x KPIWeightage / MaxScore(5),
    summed across every KPI. Returns None (rather than a partial figure)
    unless every assigned KPI has a manager score - a partial sum would
    misleadingly look like a real percentage of the whole appraisal."""
    reviews_by_kpi = {r.EmployeeKPIID: r for r in manager_reviews}
    total = 0.0
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            review = reviews_by_kpi.get(kpi.EmployeeKPIID)
            if review is None or review.ManagerScore is None:
                return None
            total += float(review.ManagerScore) * float(kpi.Weightage) / 5.0
    return round(total, 2)


def validate_hod_score(value: float) -> None:
    if value < 0 or value > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"HOD score must be between 0 and 100, got {value}")


def validate_override_has_comments(hod_score: float, reference_pct: float | None, hod_comments: str | None) -> None:
    """"Never silently" (Section 8.1's principle, applied at the record
    grain this table actually offers - see model docstring)."""
    if reference_pct is not None and round(abs(hod_score - reference_pct), 2) > SCORE_TOLERANCE and not (
        hod_comments and hod_comments.strip()
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"HOD score ({hod_score}) differs from the manager-weighted reference score ({reference_pct}%); "
                "HODComments explaining the difference is required."
            ),
        )


def ensure_is_reviewing_hod(performance: EmployeePerformance, db: Session, employee_id: int | None) -> None:
    """RBAC matrix: HOD Review is C,V,E,A,R for HOD only - Employee and
    Manager get no access at all (not even View) to this stage, unlike
    Manager Review where HOD/HR/Plant Head/MD could at least view."""
    employee = db.get(Employee, performance.EmployeeID)
    if employee is None or employee.HODID != employee_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only this employee's HOD may edit their HOD Review"
        )


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status != HOD_REVIEW_STAGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"HOD Review is not editable in the current status ({performance.Status}). "
                f"It can only be edited while the record is at the {HOD_REVIEW_STAGE} stage."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def ensure_approve_ready(hod_review: HODReview | None) -> None:
    if hod_review is None or hod_review.HODScore is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="An HOD score must be recorded before the record can be forwarded to HR Review"
        )


def stamp_action(hod_review: HODReview, action: str, actioned_by_user_id: int | None) -> None:
    now = datetime.now(timezone.utc)
    hod_review.Action = action
    hod_review.ActionedAt = now
    hod_review.ActionedBy = actioned_by_user_id
    hod_review.UpdatedAt = now

"""
Manager Review business rules (spec Section 11 / M13), built on top of
Section 8.1's override rule: a manager may keep or override the employee's
raw self-assessed KPI score, but an override is never silent - it requires
non-empty ManagerComments explaining the change.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.manager_review import ManagerReview
from app.models.self_assessment import SelfAssessment
from app.services.workflow_engine_service import ensure_within_stage_window

MANAGER_REVIEW_STAGE = "MANAGER_REVIEW"
SELF_ASSESSMENT_STAGE = "SELF_ASSESSMENT"
HOD_REVIEW_STAGE = "HOD_REVIEW"


def validate_manager_score(value: int) -> None:
    if value < 1 or value > 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Manager score must be between 1 and 5, got {value}")


def validate_override_has_comments(manager_score: int, self_score: int | None, manager_comments: str | None) -> None:
    """"Never silently" (Section 8.1): if the manager's score differs from
    the employee's own self-assessed score, ManagerComments must explain
    why. When the employee never recorded a self score at all, there is
    nothing to "override," so this check doesn't apply."""
    if self_score is not None and manager_score != self_score and not (manager_comments and manager_comments.strip()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Manager score ({manager_score}) differs from the employee's self score ({self_score}); "
                "ManagerComments explaining the override is required."
            ),
        )


def ensure_is_reviewing_manager(performance: EmployeePerformance, db: Session, employee_id: int | None) -> None:
    """Only the employee's own direct Manager may create/edit a review for
    them (RBAC matrix: Manager Review is C,V,E,R for Manager, View-only for
    everyone else in the chain, including HR/Plant Head/MD despite their
    broader business-admin rights elsewhere)."""
    employee = db.get(Employee, performance.EmployeeID)
    if employee is None or employee.ManagerID != employee_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only this employee's direct Manager may edit their Manager Review"
        )


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status != MANAGER_REVIEW_STAGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Manager Review is not editable in the current status ({performance.Status}). "
                f"It can only be edited while the record is at the {MANAGER_REVIEW_STAGE} stage."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def validate_submission_ready(
    performance: EmployeePerformance,
    manager_reviews: list[ManagerReview],
    self_assessments: list[SelfAssessment],
) -> None:
    """Every assigned KPI must have a ManagerScore before the record can
    move on to HOD Review; any score that overrides the employee's self
    score must already carry comments (checked at write time by
    validate_override_has_comments, re-checked here defensively in case a
    row was ever created outside the normal edit path)."""
    reviews_by_kpi = {r.EmployeeKPIID: r for r in manager_reviews}
    self_by_kpi = {s.EmployeeKPIID: s for s in self_assessments}

    missing = []
    unexplained_overrides = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            review = reviews_by_kpi.get(kpi.EmployeeKPIID)
            if review is None or review.ManagerScore is None:
                missing.append(kpi.kpi.KPIName)
                continue
            self_assessment = self_by_kpi.get(kpi.EmployeeKPIID)
            self_score = self_assessment.SelfScore if self_assessment else None
            if self_score is not None and review.ManagerScore != self_score and not (
                review.ManagerComments and review.ManagerComments.strip()
            ):
                unexplained_overrides.append(kpi.kpi.KPIName)

    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Every assigned KPI must have a manager score before submission. Missing for: {', '.join(missing)}",
        )
    if unexplained_overrides:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Manager score overrides the employee's self score without comments for: "
                f"{', '.join(unexplained_overrides)}"
            ),
        )


def stamp_action(manager_reviews: list[ManagerReview], action: str, actioned_by_user_id: int | None) -> None:
    now = datetime.now(timezone.utc)
    for review in manager_reviews:
        review.Action = action
        review.ActionedAt = now
        review.ActionedBy = actioned_by_user_id
        review.UpdatedAt = now

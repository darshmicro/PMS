"""
Plant Head Approval business rules (spec Section 11 / M16). See the model
module's docstring for the design note on why this module carries no score
field at all (a pure approve/return authorization gate on the HR-calibrated
score) and why the ownership check compares plants rather than people.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.employee import Employee
from app.models.hr_review import HRReview
from app.models.plant_head_approval import PlantHeadApproval
from app.services.workflow_engine_service import ensure_within_stage_window

HR_REVIEW_STAGE = "HR_REVIEW"
PLANT_HEAD_APPROVAL_STAGE = "PLANT_HEAD_APPROVAL"
MD_APPROVAL_STAGE = "MD_APPROVAL"


def get_hr_score(db: Session, performance_id: int) -> float:
    """Plant Head Approval always follows HR Review & Calibration in the
    workflow, so a completed HR_Reviews row (with HRScore set) should
    always exist by the time a record reaches PLANT_HEAD_APPROVAL - if it
    doesn't, that's a data-integrity problem worth surfacing loudly (409),
    the same pattern used for the missing-HOD-score guard in M15."""
    hr_review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    if hr_review is None or hr_review.HRScore is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This record has no completed HR Review & Calibration score to approve",
        )
    return float(hr_review.HRScore)


def ensure_is_reviewing_plant_head(performance: EmployeePerformance, db: Session, employee_id: int | None) -> None:
    """RBAC matrix: Plant Head Approval is C,V,A,R for Plant Head only.
    Unlike HOD (a direct Employee.HODID FK), Plant Head has no equivalent
    per-employee FK, so the check compares plants: the acting Plant Head's
    own Employee.PlantID must match the reviewed employee's PlantID."""
    reviewed_employee = db.get(Employee, performance.EmployeeID)
    plant_head_employee = db.get(Employee, employee_id) if employee_id is not None else None
    if (
        reviewed_employee is None
        or plant_head_employee is None
        or reviewed_employee.PlantID is None
        or plant_head_employee.PlantID is None
        or reviewed_employee.PlantID != plant_head_employee.PlantID
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only this employee's Plant Head may act on their Plant Head Approval"
        )


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status != PLANT_HEAD_APPROVAL_STAGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Plant Head Approval is not actionable in the current status ({performance.Status}). "
                f"It can only be acted on while the record is at the {PLANT_HEAD_APPROVAL_STAGE} stage."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def validate_return_has_comments(comments: str | None) -> None:
    """A return sends the whole record back to HR for reconsideration, so
    - matching the mandatory-reason pattern for every "return" action since
    M13 - Comments (this table's only free-text field) must be non-empty."""
    if not comments or not comments.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A reason (Comments) is required to return this record")


def stamp_decision(approval: PlantHeadApproval, decision: str, comments: str | None, actioned_by_user_id: int | None) -> None:
    now = datetime.now(timezone.utc)
    approval.Decision = decision
    approval.Comments = comments
    approval.ActionedAt = now
    approval.ActionedBy = actioned_by_user_id
    approval.UpdatedAt = now

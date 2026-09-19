"""
HR Review & Calibration business rules (spec Section 11 / M15). See the
model module's docstring for the design note on why HRScore is derived
(HODScore + CalibrationAdjustment) rather than independently entered, and
why this stage has only one exit.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.hod_review import HODReview
from app.models.hr_review import HRReview
from app.services.workflow_engine_service import ensure_within_stage_window

HR_REVIEW_STAGE = "HR_REVIEW"
PLANT_HEAD_APPROVAL_STAGE = "PLANT_HEAD_APPROVAL"


def get_hod_score(db: Session, performance_id: int) -> float:
    """HR Review always follows HOD Review in the workflow, so an
    HOD_Reviews row with a score should always exist by the time a record
    reaches HR_REVIEW - if it doesn't, that's a data-integrity problem
    worth surfacing loudly rather than silently treating as a zero base."""
    hod_review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    if hod_review is None or hod_review.HODScore is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This record has no completed HOD Review score to calibrate from",
        )
    return float(hod_review.HODScore)


def validate_calibration_adjustment_reason(adjustment: float, reason: str | None) -> None:
    """Spec Section 8.6: "CalibrationAdjustment <> 0 requires non-empty AdjustmentReason"."""
    if adjustment != 0 and not (reason and reason.strip()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"A non-empty adjustment reason is required when the calibration adjustment ({adjustment}) is non-zero",
        )


def compute_hr_score(hod_score: float, adjustment: float) -> float:
    return round(hod_score + adjustment, 2)


def validate_hr_score_bounds(value: float) -> None:
    if value < 0 or value > 100:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The calibrated HR score ({value}) falls outside the valid 0-100 range - "
                "reduce the calibration adjustment"
            ),
        )


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status != HR_REVIEW_STAGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"HR Review is not editable in the current status ({performance.Status}). "
                f"It can only be edited while the record is at the {HR_REVIEW_STAGE} stage."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def ensure_complete_ready(hr_review: HRReview | None) -> None:
    if hr_review is None or hr_review.HRScore is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Calibration must be recorded (even a zero adjustment) before this record can be forwarded to Plant Head Approval",
        )


def stamp_completed(hr_review: HRReview, actioned_by_user_id: int | None) -> None:
    now = datetime.now(timezone.utc)
    hr_review.ActionedAt = now
    hr_review.ActionedBy = actioned_by_user_id
    hr_review.UpdatedAt = now

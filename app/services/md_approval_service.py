"""
MD Final Approval business rules (spec Section 11 / M17). See the model
module's docstring for the design note on the actor-less
FINAL_APPROVED -> LOCKED arrow and why this module treats locking as an
immediate consequence of approval rather than a separate stage.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.hr_review import HRReview
from app.models.md_approval import MDApproval
from app.services.workflow_engine_service import ensure_within_stage_window

MD_APPROVAL_STAGE = "MD_APPROVAL"
PLANT_HEAD_APPROVAL_STAGE = "PLANT_HEAD_APPROVAL"
FINAL_APPROVED_STAGE = "FINAL_APPROVED"


def get_hr_score(db: Session, performance_id: int) -> float:
    """Nothing between HR Review (M15) and here adds or changes the score
    - Plant Head Approval (M16) is itself a score-less gate - so the
    figure MD is approving is still HR_Reviews.HRScore. A record should
    never legitimately reach MD_APPROVAL without one, so a missing score
    is a 409 data-integrity signal, the same pattern used at every prior
    approval stage since M15."""
    hr_review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()
    if hr_review is None or hr_review.HRScore is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This record has no completed HR Review & Calibration score to approve",
        )
    return float(hr_review.HRScore)


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status != MD_APPROVAL_STAGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"MD Approval is not actionable in the current status ({performance.Status}). "
                f"It can only be acted on while the record is at the {MD_APPROVAL_STAGE} stage."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def validate_return_has_comments(comments: str | None) -> None:
    """A return sends the whole record back to Plant Head Approval for
    reconsideration, so - matching the mandatory-reason pattern for every
    "return" action since M13 - Comments (this table's only free-text
    field) must be non-empty."""
    if not comments or not comments.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A reason (Comments) is required to return this record")


def stamp_decision(approval: MDApproval, decision: str, comments: str | None, actioned_by_user_id: int | None) -> None:
    now = datetime.now(timezone.utc)
    approval.Decision = decision
    approval.Comments = comments
    approval.ActionedAt = now
    approval.ActionedBy = actioned_by_user_id
    approval.UpdatedAt = now


def finalize_and_lock(performance: EmployeePerformance) -> None:
    """FINAL_APPROVED -> LOCKED (spec workflow diagram) has no separate
    actor or table of its own - "System locks record" is a mechanical
    consequence of reaching FINAL_APPROVED, not a human decision point.
    So this sets Status and IsLocked together, in the same call.

    NOT done here: computing FinalScorePct or deriving a FinalRatingID
    (Rating_Master band lookup -> Performance_Ratings). Spec Section 8.5
    ties that derivation to this same transition, but the actual
    weighted-score computation is explicitly the Scoring Engine's job
    (this codebase's own build-order table lists it as a separate,
    later module) - Employee_Performance.FinalScorePct/FinalRatingID
    stay NULL here and are populated by that module, which will need to
    hook into this exact transition point."""
    performance.Status = FINAL_APPROVED_STAGE
    performance.IsLocked = True
    performance.UpdatedAt = datetime.now(timezone.utc)

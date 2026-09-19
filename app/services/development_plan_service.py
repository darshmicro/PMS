"""
Development Plan business rules (spec Section 4.5 / M20). See the model
module's docstring for the design decisions this leans on: there's no
stage/lock gate here (development tracking outlives the appraisal
cycle), and CompletionStatus's vocabulary is inferred, not read off a
DDL enum.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.development_plan import COMPLETION_STATUSES, DevelopmentPlan


def validate_completion_status(value: str) -> None:
    if value not in COMPLETION_STATUSES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"CompletionStatus must be one of {', '.join(COMPLETION_STATUSES)}, got '{value}'",
        )


def stamp_updated(plan: DevelopmentPlan) -> None:
    plan.UpdatedAt = datetime.now(timezone.utc)

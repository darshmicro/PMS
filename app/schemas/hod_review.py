from datetime import datetime

from pydantic import BaseModel

from app.schemas.rating_breakdown import RatingBreakdownOut


class HODReviewUpdate(BaseModel):
    hod_score: float | None = None
    hod_comments: str | None = None
    development_recommendation: str | None = None
    training_requirement: str | None = None


class HODReviewReturnRequest(BaseModel):
    reason: str


class HODReviewOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    employee_photo_url: str | None = None
    cycle_id: int
    cycle_name: str
    status: str
    manager_weighted_score_pct: float | None
    hod_score: float | None
    hod_comments: str | None
    development_recommendation: str | None
    training_requirement: str | None
    action: str | None
    actioned_at: datetime | None
    rating_breakdown: RatingBreakdownOut | None = None

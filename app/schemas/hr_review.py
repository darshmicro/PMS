from datetime import datetime

from pydantic import BaseModel

from app.schemas.rating_breakdown import RatingBreakdownOut


class HRReviewUpdate(BaseModel):
    calibration_adjustment: float | None = None
    adjustment_reason: str | None = None
    hr_comments: str | None = None
    training_recommendation: str | None = None
    career_development_recommendation: str | None = None


class HRReviewOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    employee_photo_url: str | None = None
    cycle_id: int
    cycle_name: str
    status: str
    hod_score: float | None
    calibration_adjustment: float
    hr_score: float | None
    adjustment_reason: str | None
    hr_comments: str | None
    training_recommendation: str | None
    career_development_recommendation: str | None
    actioned_at: datetime | None
    rating_breakdown: RatingBreakdownOut | None = None

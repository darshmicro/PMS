from datetime import datetime

from pydantic import BaseModel

from app.schemas.rating_breakdown import RatingBreakdownOut


class PlantHeadApprovalActionRequest(BaseModel):
    comments: str | None = None


class PlantHeadApprovalOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    employee_photo_url: str | None = None
    cycle_id: int
    cycle_name: str
    status: str
    hr_score: float | None
    decision: str | None
    comments: str | None
    actioned_at: datetime | None
    rating_breakdown: RatingBreakdownOut | None = None

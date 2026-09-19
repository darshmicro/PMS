from datetime import datetime

from pydantic import BaseModel


class PerformanceScoreOut(BaseModel):
    score_type: str
    score_value: float
    calculated_at: datetime


class PerformanceRatingOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    cycle_id: int
    cycle_name: str
    final_score_pct: float | None
    rating_id: int | None
    rating_label: str | None
    finalized_at: datetime | None
    scores: list[PerformanceScoreOut]

from datetime import datetime

from pydantic import BaseModel


class ScoreBreakdownEntryOut(BaseModel):
    score_type: str
    score_value: float


class TransitionEntryOut(BaseModel):
    from_status: str | None
    to_status: str | None
    actioned_at: datetime
    comments: str | None


class PerformanceHistoryRecordOut(BaseModel):
    performance_id: int
    cycle_name: str
    status: str
    final_score_pct: float | None
    final_rating_label: str | None
    is_locked: bool
    score_breakdown: list[ScoreBreakdownEntryOut]
    transitions: list[TransitionEntryOut]


class PerformanceHistoryOut(BaseModel):
    employee_id: int
    records: list[PerformanceHistoryRecordOut]

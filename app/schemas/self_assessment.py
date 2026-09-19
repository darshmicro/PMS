from datetime import datetime

from pydantic import BaseModel


class SelfAssessmentKPIUpdate(BaseModel):
    achievement: float | None = None
    self_score: int | None = None  # required input for non-numeric measurement types; ignored (recomputed) for numeric types
    employee_comments: str | None = None
    development_need: str | None = None


class SelfAssessmentKPIOut(BaseModel):
    employee_kpi_id: int
    kpi_id: int
    kpi_name: str
    measurement_type: str
    target: float | None
    weightage: float
    achievement: float | None
    achievement_pct: float | None
    self_score: int | None
    employee_comments: str | None
    development_need: str | None
    status: str
    submitted_at: datetime | None


class SelfAssessmentOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    cycle_id: int
    cycle_name: str
    status: str
    kpis: list[SelfAssessmentKPIOut]

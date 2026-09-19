from datetime import datetime

from pydantic import BaseModel


class ManagerReviewKPIUpdate(BaseModel):
    manager_score: int | None = None
    manager_comments: str | None = None
    development_requirement: str | None = None


class ManagerReviewKPIOut(BaseModel):
    employee_kpi_id: int
    kpi_id: int
    kpi_name: str
    weightage: float
    self_achievement: float | None
    self_achievement_pct: float | None
    self_score: int | None
    manager_score: int | None
    manager_comments: str | None
    development_requirement: str | None
    action: str | None
    actioned_at: datetime | None


class ManagerReviewReturnRequest(BaseModel):
    reason: str


class ManagerReviewOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    employee_photo_url: str | None = None
    cycle_id: int
    cycle_name: str
    status: str
    kpis: list[ManagerReviewKPIOut]

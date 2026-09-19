from datetime import date, datetime

from pydantic import BaseModel


class PIPCreate(BaseModel):
    employee_id: int
    performance_gap: str | None = None
    expected_performance: str | None = None
    improvement_target: str | None = None
    action_plan: str | None = None
    training: str | None = None
    manager_id: int | None = None
    review_date: date | None = None
    pip_start_date: date | None = None
    pip_end_date: date | None = None


class PIPUpdate(BaseModel):
    performance_gap: str | None = None
    expected_performance: str | None = None
    improvement_target: str | None = None
    action_plan: str | None = None
    training: str | None = None
    manager_id: int | None = None
    review_date: date | None = None
    pip_start_date: date | None = None
    pip_end_date: date | None = None


class PIPCloseRequest(BaseModel):
    outcome: str
    comments: str | None = None


class PIPOut(BaseModel):
    pip_id: int
    employee_id: int
    employee_name: str
    performance_gap: str | None
    expected_performance: str | None
    improvement_target: str | None
    action_plan: str | None
    training: str | None
    manager_id: int | None
    manager_name: str | None
    review_date: date | None
    pip_start_date: date | None
    pip_end_date: date | None
    outcome: str | None
    comments: str | None
    created_at: datetime
    updated_at: datetime | None

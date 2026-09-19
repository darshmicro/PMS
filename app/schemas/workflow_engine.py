from datetime import date, datetime

from pydantic import BaseModel


class WorkflowHistoryEntryOut(BaseModel):
    from_status: str | None
    to_status: str | None
    actioned_by: int | None
    actioned_at: datetime
    comments: str | None


class WorkflowStatusOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    cycle_id: int
    cycle_name: str
    current_status: str
    is_locked: bool
    next_forward_stages: list[str]
    next_return_stages: list[str]
    window_start: date | None
    window_end: date | None
    is_overdue: bool
    days_overdue: int | None
    history: list[WorkflowHistoryEntryOut]

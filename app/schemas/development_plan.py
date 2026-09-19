from datetime import date, datetime

from pydantic import BaseModel


class DevelopmentPlanCreate(BaseModel):
    performance_id: int
    development_area: str | None = None
    skill_gap: str | None = None
    training_required: str | None = None
    action_plan: str | None = None
    responsible_person_id: int | None = None
    target_date: date | None = None
    review_comments: str | None = None


class DevelopmentPlanUpdate(BaseModel):
    development_area: str | None = None
    skill_gap: str | None = None
    training_required: str | None = None
    action_plan: str | None = None
    responsible_person_id: int | None = None
    target_date: date | None = None
    completion_status: str | None = None
    review_comments: str | None = None


class DevelopmentPlanOut(BaseModel):
    dev_plan_id: int
    performance_id: int
    employee_id: int
    employee_name: str
    cycle_id: int
    cycle_name: str
    development_area: str | None
    skill_gap: str | None
    training_required: str | None
    action_plan: str | None
    responsible_person_id: int | None
    responsible_person_name: str | None
    target_date: date | None
    completion_status: str
    review_comments: str | None
    created_at: datetime
    updated_at: datetime | None

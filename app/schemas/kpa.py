from datetime import date

from pydantic import BaseModel


class KPACreate(BaseModel):
    kpa_code: str
    kpa_name: str
    description: str | None = None
    department_id: int | None = None
    designation_id: int | None = None
    category: str | None = None
    default_weightage: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class KPAUpdate(BaseModel):
    kpa_name: str | None = None
    description: str | None = None
    department_id: int | None = None
    designation_id: int | None = None
    category: str | None = None
    default_weightage: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    reason: str


class KPAOut(BaseModel):
    kpa_id: int
    kpa_code: str
    kpa_name: str
    description: str | None
    department_id: int | None
    department_name: str | None
    designation_id: int | None
    designation_name: str | None
    category: str | None
    default_weightage: float | None
    effective_from: date | None
    effective_to: date | None
    is_active: bool

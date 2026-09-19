from datetime import date, datetime

from pydantic import BaseModel


class AssignmentCreate(BaseModel):
    employee_id: int
    cycle_id: int


class EmployeeKPICreate(BaseModel):
    kpi_id: int
    description: str | None = None
    target: float | None = None
    unit: str | None = None
    weightage: float
    due_date: date | None = None
    evidence_required: bool = False


class EmployeeKPIUpdate(BaseModel):
    description: str | None = None
    target: float | None = None
    unit: str | None = None
    weightage: float | None = None
    due_date: date | None = None
    evidence_required: bool | None = None


class EmployeeKPIOut(BaseModel):
    employee_kpi_id: int
    kpi_id: int
    kpi_name: str
    description: str | None
    target: float | None
    unit: str | None
    measurement_type: str
    weightage: float
    due_date: date | None
    evidence_required: bool


class EmployeeKPACreate(BaseModel):
    kpa_id: int


class EmployeeKPAOut(BaseModel):
    employee_kpa_id: int
    kpa_id: int
    kpa_name: str
    weightage: float
    kpis: list[EmployeeKPIOut]


class AssignmentOut(BaseModel):
    performance_id: int
    employee_id: int
    employee_name: str
    cycle_id: int
    cycle_name: str
    status: str
    total_weightage: float
    is_locked: bool
    kpas: list[EmployeeKPAOut]
    created_at: datetime

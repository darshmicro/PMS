from pydantic import BaseModel


class KPICreate(BaseModel):
    kpi_code: str
    kpi_name: str
    description: str | None = None
    kpa_id: int
    department_id: int | None = None
    designation_id: int | None = None
    measurement_type: str
    unit: str | None = None
    target_type: str | None = None
    default_target: float | None = None
    minimum_target: float | None = None
    expected_target: float | None = None
    stretch_target: float | None = None
    weightage: float | None = None
    scoring_method: str | None = None


class KPIUpdate(BaseModel):
    kpi_name: str | None = None
    description: str | None = None
    kpa_id: int | None = None
    department_id: int | None = None
    designation_id: int | None = None
    measurement_type: str | None = None
    unit: str | None = None
    target_type: str | None = None
    default_target: float | None = None
    minimum_target: float | None = None
    expected_target: float | None = None
    stretch_target: float | None = None
    weightage: float | None = None
    scoring_method: str | None = None
    reason: str


class KPIOut(BaseModel):
    kpi_id: int
    kpi_code: str
    kpi_name: str
    description: str | None
    kpa_id: int
    kpa_name: str
    department_id: int | None
    department_name: str | None
    designation_id: int | None
    designation_name: str | None
    measurement_type: str
    unit: str | None
    target_type: str | None
    default_target: float | None
    minimum_target: float | None
    expected_target: float | None
    stretch_target: float | None
    weightage: float | None
    scoring_method: str | None
    is_active: bool

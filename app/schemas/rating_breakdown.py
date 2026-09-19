from pydantic import BaseModel


class RatingBreakdownKPIOut(BaseModel):
    employee_kpi_id: int
    kpi_name: str
    weightage: float
    self_score: int | None
    self_achievement_pct: float | None
    employee_comments: str | None
    manager_score: int | None
    manager_comments: str | None


class RatingBreakdownOut(BaseModel):
    """Every prior stage's rating for one appraisal record, attached to
    HOD/HR/Plant Head/MD review Out schemas so each downstream reviewer
    sees the full chain, not just their own stage's figure. Fields for a
    stage that hasn't happened yet are simply None."""
    kpis: list[RatingBreakdownKPIOut]
    hod_score: float | None
    hod_comments: str | None
    hr_score: float | None
    calibration_adjustment: float | None
    adjustment_reason: str | None
    hr_comments: str | None
    plant_head_decision: str | None
    plant_head_comments: str | None

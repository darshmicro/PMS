from pydantic import BaseModel


class KPIScoringRuleCreate(BaseModel):
    kpi_id: int | None = None  # None = global default rule set
    min_achievement: float
    max_achievement: float
    score: int


class KPIScoringRuleUpdate(BaseModel):
    min_achievement: float | None = None
    max_achievement: float | None = None
    score: int | None = None
    reason: str


class KPIScoringRuleOut(BaseModel):
    rule_id: int
    kpi_id: int | None
    kpi_name: str | None
    min_achievement: float
    max_achievement: float
    score: int
    is_active: bool


class RatingMasterCreate(BaseModel):
    rating_label: str
    min_percent: float
    max_percent: float


class RatingMasterUpdate(BaseModel):
    rating_label: str | None = None
    min_percent: float | None = None
    max_percent: float | None = None
    reason: str


class RatingMasterOut(BaseModel):
    rating_id: int
    rating_label: str
    min_percent: float
    max_percent: float
    is_active: bool

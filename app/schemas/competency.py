from pydantic import BaseModel


class CompetencyCreate(BaseModel):
    competency_code: str
    competency_name: str
    category: str | None = None
    weightage: float | None = None


class CompetencyUpdate(BaseModel):
    competency_name: str | None = None
    category: str | None = None
    weightage: float | None = None
    reason: str


class CompetencyOut(BaseModel):
    competency_id: int
    competency_code: str
    competency_name: str
    category: str | None
    weightage: float | None
    is_active: bool

    model_config = {"from_attributes": True}

from pydantic import BaseModel


class ReportCatalogEntryOut(BaseModel):
    key: str
    name: str
    module: str
    permission: str
    endpoint_hint: str


class AppraisalStatusRowOut(BaseModel):
    performance_id: int
    employee_code: str
    employee_name: str
    cycle_name: str
    status: str
    final_score_pct: float | None
    final_rating_label: str | None
    is_locked: bool


class AppraisalStatusReportOut(BaseModel):
    scope: str
    rows: list[AppraisalStatusRowOut]

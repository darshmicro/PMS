from datetime import date

from pydantic import BaseModel


class PerformanceCycleCreate(BaseModel):
    cycle_name: str
    year: int | None = None
    kpi_setting_start: date | None = None
    kpi_setting_end: date | None = None
    self_assessment_start: date | None = None
    self_assessment_end: date | None = None
    manager_review_start: date | None = None
    manager_review_end: date | None = None
    hod_review_start: date | None = None
    hod_review_end: date | None = None
    hr_review_start: date | None = None
    hr_review_end: date | None = None
    plant_head_approval_start: date | None = None
    plant_head_approval_end: date | None = None
    md_approval_start: date | None = None
    md_approval_end: date | None = None


class PerformanceCycleUpdate(BaseModel):
    year: int | None = None
    kpi_setting_start: date | None = None
    kpi_setting_end: date | None = None
    self_assessment_start: date | None = None
    self_assessment_end: date | None = None
    manager_review_start: date | None = None
    manager_review_end: date | None = None
    hod_review_start: date | None = None
    hod_review_end: date | None = None
    hr_review_start: date | None = None
    hr_review_end: date | None = None
    plant_head_approval_start: date | None = None
    plant_head_approval_end: date | None = None
    md_approval_start: date | None = None
    md_approval_end: date | None = None
    reason: str


class PerformanceCycleOut(BaseModel):
    cycle_id: int
    cycle_name: str
    year: int | None
    kpi_setting_start: date | None
    kpi_setting_end: date | None
    self_assessment_start: date | None
    self_assessment_end: date | None
    manager_review_start: date | None
    manager_review_end: date | None
    hod_review_start: date | None
    hod_review_end: date | None
    hr_review_start: date | None
    hr_review_end: date | None
    plant_head_approval_start: date | None
    plant_head_approval_end: date | None
    md_approval_start: date | None
    md_approval_end: date | None
    is_active: bool

    model_config = {"from_attributes": True}


# Maps API (snake_case) field names to ORM (PascalCase) column names -
# used by the route to translate both directions without repeating the
# 14-field mapping inline in every handler.
CYCLE_FIELD_MAP = {
    "cycle_name": "CycleName",
    "year": "Year",
    "kpi_setting_start": "KPISettingStart", "kpi_setting_end": "KPISettingEnd",
    "self_assessment_start": "SelfAssessmentStart", "self_assessment_end": "SelfAssessmentEnd",
    "manager_review_start": "ManagerReviewStart", "manager_review_end": "ManagerReviewEnd",
    "hod_review_start": "HODReviewStart", "hod_review_end": "HODReviewEnd",
    "hr_review_start": "HRReviewStart", "hr_review_end": "HRReviewEnd",
    "plant_head_approval_start": "PlantHeadApprovalStart", "plant_head_approval_end": "PlantHeadApprovalEnd",
    "md_approval_start": "MDApprovalStart", "md_approval_end": "MDApprovalEnd",
}

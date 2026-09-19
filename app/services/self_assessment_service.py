"""
Employee Self-Assessment business rules (spec Section 11 / M12), built on
the KPI-level scoring algorithm from Section 8.1:

    1. Employee records Achievement.
    2. AchievementPct computed against Target (per KPI MeasurementType).
    3. Lookup KPI_Scoring_Rules (KPI-specific row if present, else the
       global KPIID=NULL default) matching AchievementPct's range -> Score.
    4. This is the raw KPI score; later stages may override it with their
       own score + mandatory comments (M13+), never silently.

DESIGN NOTE on non-numeric measurement types: step 2 above only makes
sense for the numeric-target types already established in M11
(NUMERIC/PERCENTAGE/RATIO/QTY/COST/REDUCTION - see
assignment_service.NUMERIC_TARGET_TYPES, reused here so both modules
agree on which types are "numeric"). For the remaining types
(YESNO/DATE/MILESTONE/QUALITATIVE) there is no Target to divide against,
so AchievementPct stays NULL and the employee must supply SelfScore (1-5)
directly - there is nothing in the spec to compute it from.

DESIGN NOTE on "no scoring rule matches this achievement": the spec says
scoring bands are configurable and must never be hard-coded, but is silent
on what happens if HR leaves a gap in the configured ranges. Failing loudly
(400, naming the percentage) was chosen over silently defaulting to a
score, since a silent default would misrepresent the employee's actual
achievement in a system whose entire purpose is an accurate, auditable
appraisal.
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.assignment import EmployeeKPI, EmployeePerformance
from app.models.performance_masters import KPIScoringRule
from app.models.self_assessment import SUBMITTED, SelfAssessment
from app.services.assignment_service import NUMERIC_TARGET_TYPES
from app.services.workflow_engine_service import ensure_within_stage_window

KPI_ASSIGNED = "KPI_ASSIGNED"
EMPLOYEE_ACKNOWLEDGED = "EMPLOYEE_ACKNOWLEDGED"
SELF_ASSESSMENT_STAGE = "SELF_ASSESSMENT"
MANAGER_REVIEW = "MANAGER_REVIEW"

# Statuses under which the employee may still create/edit their self-assessment.
# RETURNED is deliberately not included yet - see the model module docstring's
# forward note; it will be added once a later module actually produces it.
EDITABLE_STATUSES = {EMPLOYEE_ACKNOWLEDGED, SELF_ASSESSMENT_STAGE}


def compute_achievement_pct(measurement_type: str, achievement: float | None, target: float | None) -> float | None:
    """Achievement% = Achievement / Target * 100, only meaningful for the
    numeric-target measurement types and only when a target is actually
    set on this Employee_KPI row."""
    if measurement_type not in NUMERIC_TARGET_TYPES:
        return None
    if achievement is None or target is None or target == 0:
        return None
    # SQLAlchemy's Numeric columns round-trip through the DB as
    # decimal.Decimal, not float (that's how Achievement/Target arrive here
    # once an EmployeeKPI/SelfAssessment row has been persisted and
    # re-read) - decimal and float don't mix under Python's / operator, so
    # both operands are coerced to float explicitly before dividing.
    return round((float(achievement) / float(target)) * 100.0, 2)


def lookup_self_score(db: Session, kpi_id: int, achievement_pct: float) -> int:
    """KPI-specific scoring rule wins over the global (KPIID IS NULL)
    default, matching KPI_Scoring_Rules' own design from M8."""
    kpi_specific = (
        db.query(KPIScoringRule)
        .filter(
            KPIScoringRule.KPIID == kpi_id,
            KPIScoringRule.IsActive == True,  # noqa: E712
            KPIScoringRule.MinAchievement <= achievement_pct,
            KPIScoringRule.MaxAchievement >= achievement_pct,
        )
        .first()
    )
    if kpi_specific is not None:
        return kpi_specific.Score

    global_rule = (
        db.query(KPIScoringRule)
        .filter(
            KPIScoringRule.KPIID.is_(None),
            KPIScoringRule.IsActive == True,  # noqa: E712
            KPIScoringRule.MinAchievement <= achievement_pct,
            KPIScoringRule.MaxAchievement >= achievement_pct,
        )
        .first()
    )
    if global_rule is not None:
        return global_rule.Score

    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail=(
            f"No KPI Scoring Rule (specific or global default) covers an achievement of "
            f"{achievement_pct}%. Ask HR/Plant Head/MD to configure a scoring band for this range."
        ),
    )


def validate_self_score(value: int) -> None:
    if value < 1 or value > 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Self score must be between 1 and 5, got {value}")


def ensure_own_record(performance: EmployeePerformance, employee_id: int | None) -> None:
    """Per the RBAC matrix, Own Self-Assessment is Create/View/Edit for the
    employee themselves only (until submit) - unlike KPA/KPI Assignment,
    a Manager/HR user may VIEW but never EDIT on the employee's behalf."""
    if performance.EmployeeID != employee_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only the employee themselves may edit their own self-assessment"
        )


def ensure_stage_editable(performance: EmployeePerformance) -> None:
    if performance.Status not in EDITABLE_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Self-assessment is not editable in the current status ({performance.Status}). "
                f"It can only be edited while acknowledged or in progress."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")
    ensure_within_stage_window(performance)


def validate_submission_ready(performance: EmployeePerformance, self_assessments: list[SelfAssessment]) -> None:
    by_kpi_id = {sa.EmployeeKPIID: sa for sa in self_assessments}
    unassessed = []
    for employee_kpa in performance.kpas:
        for kpi in employee_kpa.kpis:
            sa = by_kpi_id.get(kpi.EmployeeKPIID)
            if sa is None or sa.Achievement is None or sa.SelfScore is None:
                unassessed.append(kpi.kpi.KPIName)
    if unassessed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                "Every assigned KPI must have an achievement and self score recorded before "
                f"submission. Missing for: {', '.join(unassessed)}"
            ),
        )


def mark_all_submitted(db: Session, self_assessments: list[SelfAssessment]) -> None:
    now = datetime.now(timezone.utc)
    for sa in self_assessments:
        sa.Status = SUBMITTED
        sa.SubmittedAt = now
        sa.UpdatedAt = now

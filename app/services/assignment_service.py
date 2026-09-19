"""
KPA/KPI Assignment business rules (spec Section 10). This is the module
whose validation the spec names explicitly:

    "Provide validation to prevent:
     - Weightage >100%
     - Weightage <100%
     - Duplicate KPI
     - Invalid target
     - Missing mandatory KPI"

DESIGN NOTE on what "100%" refers to: the spec's one sentence is "The
total KPI weightage must equal 100% before submission" - a single flat
rule across every KPI assigned to the employee for that cycle, not a
nested "KPA weightages sum to 100, and each KPA's KPIs sum to 100"
rule. That reading also matches Section 13's weighted-score formula,
which treats each KPI's Weightage as its absolute share of the whole
appraisal (`KPI Score x KPI Weightage / Max Score`), not a percentage
relative to its parent KPA. So Employee_KPA.Weightage is a read-only
rollup for display (recomputed here after every change), and the only
value actually validated against 100% is the sum of every active
Employee_KPI.Weightage under the Employee_Performance record.

DESIGN NOTE on "Missing mandatory KPI": the spec doesn't define a
"mandatory" flag anywhere in the KPI Master field list (Section 8), so
there is nothing per-KPI to check. The only structural reading available
is at the KPA level: a KPA the assigner chose to include but never
attached any KPI to is a KPA missing its (mandatory) KPI content, so
submission is blocked until every included KPA has at least one KPI.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeeKPA, EmployeeKPI, EmployeePerformance

WEIGHTAGE_TOLERANCE = 0.01  # absorbs decimal rounding noise (e.g. 33.33 x 3 = 99.99)

# Measurement types where a numeric Target is meaningful and therefore
# required; the rest (YESNO, DATE, MILESTONE, QUALITATIVE) are validated
# through Description/DueDate instead, not a numeric Target.
NUMERIC_TARGET_TYPES = {"NUMERIC", "PERCENTAGE", "RATIO", "QTY", "COST", "REDUCTION"}


def validate_target(measurement_type: str, target: float | None) -> None:
    if measurement_type in NUMERIC_TARGET_TYPES:
        if target is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"A numeric target is required for measurement type '{measurement_type}'",
            )
        if target < 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Target must not be negative")


def validate_row_weightage(weightage: float) -> None:
    if weightage <= 0 or weightage > 100:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Weightage must be greater than 0 and at most 100, got {weightage}"
        )


def check_duplicate_kpi(db: Session, performance_id: int, kpi_id: int, exclude_employee_kpi_id: int | None = None) -> None:
    """A KPI may appear only once across the whole appraisal, regardless
    of which KPA it's filed under (spec: "Duplicate KPI")."""
    query = (
        db.query(EmployeeKPI)
        .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .filter(EmployeeKPA.PerformanceID == performance_id, EmployeeKPI.KPIID == kpi_id)
    )
    if exclude_employee_kpi_id is not None:
        query = query.filter(EmployeeKPI.EmployeeKPIID != exclude_employee_kpi_id)
    if query.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This KPI is already assigned to this employee for this cycle")


def recompute_rollups(db: Session, performance_id: int) -> EmployeePerformance:
    """Recomputes Employee_KPA.Weightage (sum of its own KPIs) and
    Employee_Performance.TotalWeightage (sum of every KPI) after any
    add/edit/remove. Called at the end of every mutating operation so the
    stored rollups never drift from the rows they summarize."""
    performance = db.get(EmployeePerformance, performance_id)
    total = 0.0
    for employee_kpa in performance.kpas:
        kpa_total = sum(float(kpi.Weightage) for kpi in employee_kpa.kpis)
        employee_kpa.Weightage = kpa_total
        total += kpa_total
    performance.TotalWeightage = total
    db.commit()
    db.refresh(performance)
    return performance


def ensure_editable(performance: EmployeePerformance) -> None:
    if performance.Status != "DRAFT":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This assignment is no longer editable (status: {performance.Status}). "
                "Only a DRAFT assignment can have its KPAs/KPIs changed."
            ),
        )
    if performance.IsLocked:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This appraisal record is locked")


def validate_submission_ready(performance: EmployeePerformance) -> None:
    """The three submission-time checks from spec Section 10."""
    if not performance.kpas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="At least one KPA must be assigned before submission")

    empty_kpas = [ek.kpa.KPAName for ek in performance.kpas if not ek.kpis]
    if empty_kpas:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Missing mandatory KPI: the following assigned KPA(s) have no KPI attached: {', '.join(empty_kpas)}",
        )

    total = float(performance.TotalWeightage)
    # Round the delta to 2dp (Weightage's own precision) before comparing to
    # the tolerance band - raw float subtraction can leave noise like
    # 100.0 - 99.99 == 0.010000000000005, which would fail a strict ">"
    # check against a 0.01 tolerance even though the values are equal to
    # every decimal place that actually matters.
    if round(abs(total - 100.0), 2) > WEIGHTAGE_TOLERANCE:
        comparison = "exceeds" if total > 100.0 else "is less than"
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Total KPI weightage {comparison} 100% (currently {total:.2f}%). It must equal exactly 100% before submission.",
        )

"""
Cross-stage rating visibility. At HOD Review, HR Review & Calibration,
Plant Head Approval and MD Approval, the reviewer should be able to see
every prior stage's rating - not just the single rolled-up figure their
own stage's Out schema already carried (e.g. MDApprovalOut's hr_score
alone). build_rating_breakdown() aggregates Self-Assessment (per KPI),
Manager Review (per KPI), HOD Review and HR Review into one payload for a
given PerformanceID; a caller that also wants Plant Head's decision (MD
Approval's view) merges that in separately with
RatingBreakdownOut.model_copy(update=...), since Plant Head Approval
carries no score of its own to fold into this generic per-table join.

Every field here is simply whatever the corresponding stage has already
produced by the time a downstream reviewer opens the record - at an
earlier stage nothing exists yet for the fields still to come, so those
resolve to None rather than being hidden or erroring. Nothing here widens
who can reach this data: it's attached only to HOD/HR/Plant Head/MD Out
schemas, and every one of those routes already requires that stage's own
.VIEW permission before this function is ever called - a plain Employee
never holds any of those permissions (see each stage's sql/0NN seed) and
never reaches these endpoints at all, so "an employee sees only their own
rating" continues to be enforced the same way it already was everywhere
else in this codebase: by permission grants, not by an extra check here.
"""
from sqlalchemy.orm import Session

from app.models.assignment import EmployeeKPA, EmployeeKPI
from app.models.hod_review import HODReview
from app.models.hr_review import HRReview
from app.models.manager_review import ManagerReview
from app.models.self_assessment import SelfAssessment
from app.schemas.rating_breakdown import RatingBreakdownKPIOut, RatingBreakdownOut


def build_rating_breakdown(db: Session, performance_id: int) -> RatingBreakdownOut:
    kpi_rows = (
        db.query(EmployeeKPI)
        .join(EmployeeKPA, EmployeeKPI.EmployeeKPAID == EmployeeKPA.EmployeeKPAID)
        .filter(EmployeeKPA.PerformanceID == performance_id)
        .all()
    )
    employee_kpi_ids = [k.EmployeeKPIID for k in kpi_rows]

    self_by_kpi = {
        sa.EmployeeKPIID: sa
        for sa in (
            db.query(SelfAssessment).filter(SelfAssessment.EmployeeKPIID.in_(employee_kpi_ids)).all()
            if employee_kpi_ids else []
        )
    }
    manager_by_kpi = {
        mr.EmployeeKPIID: mr
        for mr in (
            db.query(ManagerReview).filter(ManagerReview.EmployeeKPIID.in_(employee_kpi_ids)).all()
            if employee_kpi_ids else []
        )
    }

    kpis = []
    for k in kpi_rows:
        self_row = self_by_kpi.get(k.EmployeeKPIID)
        manager_row = manager_by_kpi.get(k.EmployeeKPIID)
        kpis.append(RatingBreakdownKPIOut(
            employee_kpi_id=k.EmployeeKPIID,
            kpi_name=k.kpi.KPIName,
            weightage=float(k.Weightage),
            self_score=self_row.SelfScore if self_row else None,
            self_achievement_pct=(
                float(self_row.AchievementPct) if self_row and self_row.AchievementPct is not None else None
            ),
            employee_comments=self_row.EmployeeComments if self_row else None,
            manager_score=manager_row.ManagerScore if manager_row else None,
            manager_comments=manager_row.ManagerComments if manager_row else None,
        ))

    hod_review = db.query(HODReview).filter(HODReview.PerformanceID == performance_id).one_or_none()
    hr_review = db.query(HRReview).filter(HRReview.PerformanceID == performance_id).one_or_none()

    return RatingBreakdownOut(
        kpis=kpis,
        hod_score=float(hod_review.HODScore) if hod_review and hod_review.HODScore is not None else None,
        hod_comments=hod_review.HODComments if hod_review else None,
        hr_score=float(hr_review.HRScore) if hr_review and hr_review.HRScore is not None else None,
        calibration_adjustment=float(hr_review.CalibrationAdjustment) if hr_review else None,
        adjustment_reason=hr_review.AdjustmentReason if hr_review else None,
        hr_comments=hr_review.HRComments if hr_review else None,
        plant_head_decision=None,
        plant_head_comments=None,
    )

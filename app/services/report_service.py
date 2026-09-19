"""
Reports & Export Center (spec Section 5/7/36A / M25: "PDF/Excel/CSV,
stage-wise export"). Section 10's own build sequence note already says
what this module actually is: "M25's Excel export endpoints (Sec 36A)
added incrementally as each stage module ships, not deferred to the
end." Every module since M3 has, in fact, shipped its own GET .../export
endpoint using export_service.build_export_workbook() as it was built -
26 of them exist by M24. So M25 does not rebuild those; it adds the two
things no earlier module had reason to build on its own:

1. A catalog (REPORT_CATALOG / list_available_reports) - the "Reports &
   Export Center" screen (Section 7 #38) needs one place that lists every
   export the *caller* can actually reach, filtered by the permissions
   they hold, rather than making them already know which of 26 endpoints
   exists and guess whether they're allowed to call it.

2. One genuinely new, cross-cutting report - a consolidated, role-scoped
   roster of appraisal status across every record the caller can see at
   once (build_appraisal_status_rows). Every existing export is scoped to
   *one* record (one self-assessment, one review, one approval); nothing
   before this module produces a multi-record "stage-wise" listing, which
   is what Section 7's Export Center screen and the "PDF/Excel/CSV"
   format list actually imply - a report you'd hand to an auditor or a
   Plant Head, not a single form's PDF.

DESIGN NOTE on scope: the RBAC matrix's "Reports/Exports" row -
"Own | Team-scoped | Dept-scoped | Org-scoped | Plant-scoped | Org-scoped
| Org-scoped | X" for Employee/Manager/HOD/HR/Plant Head/MD/HR
Administrator/System Administrator - is structurally identical to M24's
Dashboards row with one difference: System Administrator gets X here
(nothing), not "system health only". So this module reuses M24's own
dashboard_service.apply_dashboard_scope() directly for scope resolution
(Plant Head narrowed to Plant, not Org - see that module's own docstring
for why it isn't the shared BROAD_ACCESS_ROLES grouping) rather than
re-deriving the same tiering a second time, and simply denies
SYS_ADMIN outright instead of routing it to a technical view the way
Dashboards did.
"""
import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext
from app.models.assignment import EmployeePerformance
from app.models.performance_masters import PerformanceCycle, RatingMaster
from app.services.dashboard_service import apply_dashboard_scope

# One entry per export endpoint already shipped (M3-M24), plus this
# module's own new consolidated report. "permission" is the exact
# PermissionCode that already gates the underlying endpoint (per the RBAC
# matrix note: "every row's export permission mirrors its View scope") -
# this catalog invents no new access rule, it only surfaces what already
# exists.
REPORT_CATALOG: list[dict] = [
    {"key": "org_masters", "name": "Org Masters Export (Company/Plant/Department/Section/Designation/Grade/Category)", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/masters/{type}/export"},
    {"key": "employee_master", "name": "Employee Master Export", "module": "EMPLOYEE_MASTER", "permission": "EMPLOYEE_MASTER.VIEW", "endpoint_hint": "/employees/export"},
    {"key": "performance_cycle", "name": "Performance Cycle Export", "module": "PERFORMANCE_CYCLE", "permission": "PERFORMANCE_CYCLE.VIEW", "endpoint_hint": "/performance-cycles/export"},
    {"key": "kpa_master", "name": "KPA Master Export", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/kpa/export"},
    {"key": "kpi_master", "name": "KPI Master Export", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/kpi/export"},
    {"key": "scoring_rules", "name": "Scoring Rules Export", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/scoring/scoring-rules/export"},
    {"key": "rating_master", "name": "Rating Master Export", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/scoring/ratings/export"},
    {"key": "competency_master", "name": "Competency Master Export", "module": "MASTERS", "permission": "MASTERS.VIEW", "endpoint_hint": "/competency/export"},
    {"key": "assignment", "name": "KPA/KPI Assignment Export (per record)", "module": "ASSIGNMENT", "permission": "ASSIGNMENT.VIEW", "endpoint_hint": "/assignments/{performance_id}/export"},
    {"key": "self_assessment", "name": "Self-Assessment Export (per record)", "module": "SELF_ASSESSMENT", "permission": "SELF_ASSESSMENT.VIEW", "endpoint_hint": "/self-assessments/{performance_id}/export"},
    {"key": "manager_review", "name": "Manager Review Export (per record)", "module": "MANAGER_REVIEW", "permission": "MANAGER_REVIEW.VIEW", "endpoint_hint": "/manager-reviews/{performance_id}/export"},
    {"key": "hod_review", "name": "HOD Review Export (per record)", "module": "HOD_REVIEW", "permission": "HOD_REVIEW.VIEW", "endpoint_hint": "/hod-reviews/{performance_id}/export"},
    {"key": "hr_review", "name": "HR Review & Calibration Export (per record)", "module": "HR_REVIEW", "permission": "HR_REVIEW.VIEW", "endpoint_hint": "/hr-reviews/{performance_id}/export"},
    {"key": "plant_head_approval", "name": "Plant Head Approval Export (per record)", "module": "PLANT_HEAD_APPROVAL", "permission": "PLANT_HEAD_APPROVAL.VIEW", "endpoint_hint": "/plant-head-approvals/{performance_id}/export"},
    {"key": "md_approval", "name": "MD Approval Export (per record)", "module": "MD_APPROVAL", "permission": "MD_APPROVAL.VIEW", "endpoint_hint": "/md-approvals/{performance_id}/export"},
    {"key": "scoring_engine", "name": "Scoring Result Export (per record)", "module": "SCORING_ENGINE", "permission": "SCORING_ENGINE.VIEW", "endpoint_hint": "/scoring-engine/{performance_id}/export"},
    {"key": "development_plan", "name": "Development Plan Export (per record)", "module": "DEVELOPMENT_PLAN", "permission": "DEVELOPMENT_PLAN.VIEW", "endpoint_hint": "/development-plans/performance/{performance_id}/export"},
    {"key": "pip", "name": "PIP Export (per record)", "module": "PIP", "permission": "PIP.VIEW", "endpoint_hint": "/pip/{pip_id}/export"},
    {"key": "attachments", "name": "Attachments Manifest Export", "module": "ATTACHMENT", "permission": "ATTACHMENT.VIEW", "endpoint_hint": "/attachments/export/list"},
    {"key": "notifications", "name": "My Notifications Export", "module": "NOTIFICATION", "permission": "NOTIFICATION.VIEW", "endpoint_hint": "/notifications/export"},
    {"key": "appraisal_status", "name": "Consolidated Appraisal Status Report (role-scoped, multi-record)", "module": "REPORT", "permission": "REPORT.VIEW", "endpoint_hint": "/reports/appraisal-status"},
]


def list_available_reports(permission_codes: set[str]) -> list[dict]:
    return [entry for entry in REPORT_CATALOG if entry["permission"] in permission_codes]


def build_appraisal_status_rows(
    db: Session, ctx: CurrentContext, cycle_id: int | None = None,
    employee_id: int | None = None, year: int | None = None,
) -> tuple[list[dict], str]:
    """The one new multi-record report - see module docstring. Reuses
    M24's apply_dashboard_scope() rather than re-deriving Own/Team/Dept/
    Org/Plant tiering a second time.

    employee_id/year are additive search filters on top of the same
    role-based scope - they narrow what a caller can already see, never
    widen it, so they're applied to the query before apply_dashboard_scope
    just like cycle_id already was."""
    query = db.query(EmployeePerformance)
    if cycle_id is not None:
        query = query.filter(EmployeePerformance.CycleID == cycle_id)
    if employee_id is not None:
        query = query.filter(EmployeePerformance.EmployeeID == employee_id)
    if year is not None:
        query = query.join(PerformanceCycle, EmployeePerformance.CycleID == PerformanceCycle.CycleID).filter(
            PerformanceCycle.Year == year
        )
    scoped_query, scope = apply_dashboard_scope(query, ctx)
    records = scoped_query.all()

    rating_ids = {r.FinalRatingID for r in records if r.FinalRatingID is not None}
    rating_labels = {
        rating.RatingID: rating.RatingLabel
        for rating in (db.query(RatingMaster).filter(RatingMaster.RatingID.in_(rating_ids)).all() if rating_ids else [])
    }

    rows = [
        {
            "performance_id": r.PerformanceID,
            "employee_code": r.employee.EmployeeCode,
            "employee_name": r.employee.FullName,
            "cycle_name": r.cycle.CycleName,
            "status": r.Status,
            "final_score_pct": float(r.FinalScorePct) if r.FinalScorePct is not None else None,
            "final_rating_label": rating_labels.get(r.FinalRatingID) if r.FinalRatingID is not None else None,
            "is_locked": r.IsLocked,
        }
        for r in records
    ]
    return rows, scope


def render_csv(headers: list[str], rows: list[list]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def render_pdf(*, title: str, headers: list[str], rows: list[list], generated_by: str, context_label: str) -> bytes:
    """Minimal, table-only PDF (spec Section 9's format list: "PDF/Excel/
    CSV") - landscape letter so a typical roster's columns fit without
    per-report layout tuning."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()

    # Same identifying header block as build_export_workbook()'s Excel
    # exports (spec Section 36A: "Export Generated By", "Export
    # Date/Time", "Context"), kept consistent across formats.
    header_lines = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"Export Generated By: {generated_by}", styles["Normal"]),
        Paragraph(f"Export Date/Time: {datetime.now(timezone.utc).isoformat()}", styles["Normal"]),
        Paragraph(f"Context: {context_label}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data = [headers] + [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    doc.build([*header_lines, table])
    return buffer.getvalue()

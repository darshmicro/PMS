"""
Dashboard aggregation (spec Section 5/7 / M24: "role-specific dashboards,
7 roles"). Unlike Development Plan/PIP/Attachments/Notifications before
it, this module has an *explicit* RBAC matrix row to build against -
"Dashboards | Own | Team | Dept | Org | Plant | Org | Org | System health
only" - rather than one inferred from screen names and adjacent DDL.

DESIGN NOTE on Plant Head's scope: every prior module's shared
BROAD_ACCESS_ROLES constant ({"HR", "HR_ADMIN", "PLANT_HEAD", "MD",
"SYS_ADMIN"}) treats Plant Head as org-wide, because every *other* row of
the RBAC matrix gives Plant Head full business-admin rights equal to
HR/MD (spec Section 4's own note: "Plant Head and MD get full business
admin rights... except system-level config"). The Dashboards row is the
first place the spec narrows that: Plant Head's own column reads "Plant,"
not "Org" - matching Plant Head Approval's (M16) plant-matching ownership
rule rather than the broader org-wide rows. So this module does NOT reuse
BROAD_ACCESS_ROLES; it builds its own scope resolution below, with Plant
Head deliberately split out from HR/MD/HR Administrator.

DESIGN NOTE on System Administrator: "System health only" is a different
kind of dashboard entirely, not a narrower business one - matching this
codebase's running principle that Sys Admin is "a distinct technical role
with no business approval rights" (spec Section 3-4, quoted in the Role
model's own docstring). Rather than force it through the same
DashboardSummaryOut shape with every business field null, this module
gives it its own endpoint and schema (GET /dashboard/system-health) that
never exposes individual scores, ratings or appraisal content - only
technical/operational counts.

DESIGN NOTE on scope: the RBAC matrix's "Reports/Exports" row is separate
from "Dashboards," so stage-wise Excel exports (spec Section 36A) stay
with M25, not here - this module is read-only, live, in-app summaries.
"""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext
from app.models.assignment import EmployeePerformance
from app.models.audit import AuditLog
from app.models.employee import Employee
from app.models.notification import Notification
from app.models.performance_masters import RatingMaster
from app.models.rbac import User
from app.services.workflow_engine_service import compute_sla_status

SCOPE_OWN = "OWN"
SCOPE_TEAM = "TEAM"
SCOPE_DEPT = "DEPT"
SCOPE_ORG = "ORG"
SCOPE_PLANT = "PLANT"

# Which stage(s) each role's own dashboard treats as "waiting on me" -
# mirrors the transition endpoints each role can act on (M13-M17), not a
# new authority rule of its own. HR Administrator has no row here (like
# Plant Head/MD in every OTHER module, HR Administrator holds full
# business-admin rights everywhere *except* actually approving a stage
# itself - it never appears as an actor in the workflow diagram, only as
# a universal View/Export role), so its pending-action count is always 0.
ACTIONABLE_STAGES_BY_ROLE: dict[str, set[str]] = {
    "EMPLOYEE": {"EMPLOYEE_ACKNOWLEDGED", "SELF_ASSESSMENT"},
    "MANAGER": {"MANAGER_REVIEW"},
    "HOD": {"HOD_REVIEW"},
    "HR": {"HR_REVIEW"},
    "PLANT_HEAD": {"PLANT_HEAD_APPROVAL"},
    "MD": {"MD_APPROVAL"},
}

# Statuses that are still "in flight" - excluded is DRAFT/KPI_ASSIGNED
# (pre-workflow setup, no SLA window yet per M19's STAGE_WINDOWS) and
# FINAL_APPROVED (already done, nothing to be overdue about).
_OVERDUE_ELIGIBLE_STATUSES = {
    "EMPLOYEE_ACKNOWLEDGED", "SELF_ASSESSMENT", "MANAGER_REVIEW", "HOD_REVIEW",
    "HR_REVIEW", "PLANT_HEAD_APPROVAL", "MD_APPROVAL",
}


def apply_dashboard_scope(query, ctx: CurrentContext) -> tuple:
    """Returns (scoped_query, scope_label) per the Dashboards RBAC row -
    see module docstring for why this does not reuse the shared
    BROAD_ACCESS_ROLES grouping used everywhere else in this codebase.
    Checked broadest-to-narrowest, same ordering convention as every
    other module's _apply_scope."""
    role_codes = set(ctx.role_codes)
    if role_codes & {"HR", "MD", "HR_ADMIN"}:
        return query, SCOPE_ORG
    if "PLANT_HEAD" in role_codes:
        acting = None
        if ctx.employee_id is not None:
            # A single-row lookup against the caller's own Employee record
            # to read their PlantID - mirrors M16's ensure_is_reviewing_
            # plant_head() plant-matching rule exactly, rather than a
            # per-record join (there is exactly one caller per request).
            acting = query.session.get(Employee, ctx.employee_id)
        plant_id = acting.PlantID if acting is not None else None
        query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
        return query.filter(Employee.PlantID == plant_id), SCOPE_PLANT
    if "HOD" in role_codes:
        query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
        return query.filter(Employee.HODID == ctx.employee_id), SCOPE_DEPT
    if "MANAGER" in role_codes:
        query = query.join(Employee, EmployeePerformance.EmployeeID == Employee.EmployeeID)
        return query.filter(Employee.ManagerID == ctx.employee_id), SCOPE_TEAM
    return query.filter(EmployeePerformance.EmployeeID == ctx.employee_id), SCOPE_OWN


def summarize(db: Session, records: list[EmployeePerformance], role_codes: list[str]) -> dict:
    status_breakdown: dict[str, int] = {}
    for r in records:
        status_breakdown[r.Status] = status_breakdown.get(r.Status, 0) + 1

    rated = [r for r in records if r.FinalScorePct is not None]
    average_final_score_pct = (
        round(sum(float(r.FinalScorePct) for r in rated) / len(rated), 2) if rated else None
    )

    rating_ids = {r.FinalRatingID for r in records if r.FinalRatingID is not None}
    rating_labels = {
        rating.RatingID: rating.RatingLabel
        for rating in (db.query(RatingMaster).filter(RatingMaster.RatingID.in_(rating_ids)).all() if rating_ids else [])
    }
    rating_distribution: dict[str, int] = {}
    for r in records:
        if r.FinalRatingID is not None:
            label = rating_labels.get(r.FinalRatingID, f"RatingID {r.FinalRatingID}")
            rating_distribution[label] = rating_distribution.get(label, 0) + 1

    overdue_count = sum(
        1 for r in records if r.Status in _OVERDUE_ELIGIBLE_STATUSES and compute_sla_status(r).is_overdue
    )

    actionable_statuses: set[str] = set()
    for role in role_codes:
        actionable_statuses |= ACTIONABLE_STAGES_BY_ROLE.get(role, set())
    pending_my_action_count = sum(1 for r in records if r.Status in actionable_statuses)

    return {
        "total_appraisals": len(records),
        "status_breakdown": status_breakdown,
        "rating_distribution": rating_distribution,
        "average_final_score_pct": average_final_score_pct,
        "overdue_count": overdue_count,
        "pending_my_action_count": pending_my_action_count,
    }


def system_health(db: Session) -> dict:
    """Sys Admin's own dashboard - technical/operational counts only, no
    business content (individual scores, ratings, appraisal comments) -
    see module docstring."""
    active_employees = db.query(Employee).filter(Employee.IsActive == True).count()  # noqa: E712
    active_users = db.query(User).filter(User.IsActive == True).count()  # noqa: E712

    appraisals_by_status: dict[str, int] = {}
    for (status_value, count) in (
        db.query(EmployeePerformance.Status, func.count(EmployeePerformance.PerformanceID))
        .group_by(EmployeePerformance.Status)
        .all()
    ):
        appraisals_by_status[status_value] = count

    total_audit_log_entries = db.query(AuditLog).count()
    most_recent_audit = db.query(AuditLog).order_by(AuditLog.ActionedAt.desc()).first()
    total_notifications_sent = db.query(Notification).count()

    return {
        "active_employees": active_employees,
        "active_users": active_users,
        "appraisals_by_status": appraisals_by_status,
        "total_audit_log_entries": total_audit_log_entries,
        "most_recent_audit_at": most_recent_audit.ActionedAt if most_recent_audit is not None else None,
        "total_notifications_sent": total_notifications_sent,
    }

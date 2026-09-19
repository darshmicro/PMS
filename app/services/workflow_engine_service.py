"""
Workflow Engine (spec build-order table: "Stage sequencing, SLA,
escalation, return-routing" / M19). Three things, each independently
usable:

1. STAGE_WINDOWS / ensure_within_stage_window(): the per-stage Start/End
   date columns on Performance_Cycles have existed since M5, and that
   model's own docstring already commits to this: "The workflow engine
   (M19) reads these dates to gate which stage is currently open - they
   are not just informational." So this module is what makes that promise
   real, and every stage's ensure_stage_editable() (M12-M17) now calls
   ensure_within_stage_window() as its last check.

2. WORKFLOW_GRAPH / get_next_stages(): a single declarative map of every
   forward and return edge in the workflow, matching exactly what M12-M17
   already implement ad hoc (one transition endpoint per edge). This
   isn't a new enforcement layer - each module's own transition endpoints
   keep validating and executing their own edges exactly as before, to
   avoid a large, risky rewrite of six already-shipped, already-tested
   modules. What this adds is a single place that *describes* the whole
   graph, for the read-only status endpoint below and for later modules
   (Dashboards/M24, Notifications/M23) to query instead of re-deriving it.

3. record_transition()/WorkflowHistory: a dedicated per-record transition
   log (see model docstring for how this differs from Audit_Log), written
   by every existing transition endpoint alongside the write_audit() call
   it already makes.

DESIGN NOTE on gating early vs. late: a stage window's Start date is
enforced as a hard gate (acting before a stage has opened means the data
it depends on may not even exist yet, e.g. before ManagerReviewStart the
self-assessment window may still be running). A stage window's End date
is deliberately NOT a hard gate - blocking action after the End date
would strand a record with no forward path, since no "reopen" workflow
event has been built (spec references one but this design doc, as
delivered, never actually defines it - see README_M19.md). Lateness is
instead surfaced as data (compute_sla_status()) for a human or a later
Notifications/escalation module to act on, not silently enforced as a
dead end.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assignment import EmployeePerformance
from app.models.performance_masters import PerformanceCycle
from app.models.workflow_history import WorkflowHistory

# status -> (CycleStartColumn, CycleEndColumn). Statuses with no configured
# window here (DRAFT, KPI_ASSIGNED, FINAL_APPROVED) are simply never gated.
STAGE_WINDOWS: dict[str, tuple[str, str]] = {
    "EMPLOYEE_ACKNOWLEDGED": ("SelfAssessmentStart", "SelfAssessmentEnd"),
    "SELF_ASSESSMENT": ("SelfAssessmentStart", "SelfAssessmentEnd"),
    "MANAGER_REVIEW": ("ManagerReviewStart", "ManagerReviewEnd"),
    "HOD_REVIEW": ("HODReviewStart", "HODReviewEnd"),
    "HR_REVIEW": ("HRReviewStart", "HRReviewEnd"),
    "PLANT_HEAD_APPROVAL": ("PlantHeadApprovalStart", "PlantHeadApprovalEnd"),
    "MD_APPROVAL": ("MDApprovalStart", "MDApprovalEnd"),
}

# The whole workflow graph, forward and return edges, exactly as built in
# M12 (Self-Assessment) through M17 (MD Approval). Reference/documentation
# data for get_next_stages() and later modules - not itself an enforcement
# path (each module's own transition endpoints keep doing that).
WORKFLOW_GRAPH: dict[str, dict[str, list[str]]] = {
    "DRAFT": {"forward": ["KPI_ASSIGNED"], "return": []},
    "KPI_ASSIGNED": {"forward": ["EMPLOYEE_ACKNOWLEDGED"], "return": []},
    "EMPLOYEE_ACKNOWLEDGED": {"forward": ["SELF_ASSESSMENT"], "return": []},
    "SELF_ASSESSMENT": {"forward": ["MANAGER_REVIEW"], "return": []},
    "MANAGER_REVIEW": {"forward": ["HOD_REVIEW"], "return": ["SELF_ASSESSMENT"]},
    "HOD_REVIEW": {"forward": ["HR_REVIEW"], "return": ["MANAGER_REVIEW", "SELF_ASSESSMENT"]},
    "HR_REVIEW": {"forward": ["PLANT_HEAD_APPROVAL"], "return": []},
    "PLANT_HEAD_APPROVAL": {"forward": ["MD_APPROVAL"], "return": ["HR_REVIEW"]},
    "MD_APPROVAL": {"forward": ["FINAL_APPROVED"], "return": ["PLANT_HEAD_APPROVAL"]},
    "FINAL_APPROVED": {"forward": [], "return": []},
}


def get_next_stages(current_status: str) -> dict[str, list[str]]:
    return WORKFLOW_GRAPH.get(current_status, {"forward": [], "return": []})


def ensure_within_stage_window(performance: EmployeePerformance, today: date | None = None) -> None:
    """Blocks acting on a record before its current stage's configured
    window has opened. See module docstring for why the End date is
    deliberately not enforced the same way. A stage with no configured
    window at all (either bound left NULL) is never gated - the spec's
    own date columns are all nullable, and an admin who hasn't set them
    yet shouldn't accidentally lock every record in that stage."""
    window = STAGE_WINDOWS.get(performance.Status)
    if window is None:
        return
    start_col, _end_col = window
    cycle: PerformanceCycle | None = performance.cycle
    if cycle is None:
        return
    start_date = getattr(cycle, start_col)
    if start_date is None:
        return
    effective_today = today or datetime.now(timezone.utc).date()
    if effective_today < start_date:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"The {performance.Status} stage for cycle '{cycle.CycleName}' does not open until "
                f"{start_date.isoformat()}"
            ),
        )


@dataclass
class SLAStatus:
    stage: str
    window_start: date | None
    window_end: date | None
    is_overdue: bool
    days_overdue: int | None


def compute_sla_status(performance: EmployeePerformance, today: date | None = None) -> SLAStatus:
    """Read-only - see module docstring for why lateness is surfaced as
    data rather than enforced as a hard block."""
    window = STAGE_WINDOWS.get(performance.Status)
    cycle: PerformanceCycle | None = performance.cycle
    if window is None or cycle is None:
        return SLAStatus(stage=performance.Status, window_start=None, window_end=None, is_overdue=False, days_overdue=None)
    start_col, end_col = window
    window_start = getattr(cycle, start_col)
    window_end = getattr(cycle, end_col)
    effective_today = today or datetime.now(timezone.utc).date()
    if window_end is not None and effective_today > window_end:
        return SLAStatus(
            stage=performance.Status, window_start=window_start, window_end=window_end,
            is_overdue=True, days_overdue=(effective_today - window_end).days,
        )
    return SLAStatus(stage=performance.Status, window_start=window_start, window_end=window_end, is_overdue=False, days_overdue=None)


def record_transition(
    db: Session, performance_id: int, from_status: str | None, to_status: str | None,
    actioned_by_user_id: int | None, comments: str | None = None,
) -> WorkflowHistory:
    """Called by every existing transition endpoint (M12-M17) alongside
    the write_audit() call it already makes - see model module's
    docstring for why this is a separate table from Audit_Log. Commits
    its own row immediately, mirroring write_audit()'s own self-contained
    commit, since both are called after the main record change has
    already been committed."""
    entry = WorkflowHistory(
        PerformanceID=performance_id, FromStatus=from_status, ToStatus=to_status,
        ActionedBy=actioned_by_user_id, ActionedAt=datetime.now(timezone.utc), Comments=comments,
    )
    db.add(entry)
    db.commit()
    return entry

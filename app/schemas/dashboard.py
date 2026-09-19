from datetime import datetime

from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    scope: str
    total_appraisals: int
    status_breakdown: dict[str, int]
    rating_distribution: dict[str, int]
    average_final_score_pct: float | None
    overdue_count: int
    pending_my_action_count: int


class SystemHealthOut(BaseModel):
    active_employees: int
    active_users: int
    appraisals_by_status: dict[str, int]
    total_audit_log_entries: int
    most_recent_audit_at: datetime | None
    total_notifications_sent: int

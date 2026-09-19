"""
Workflow_History (spec Section 4.5, M19). A dedicated, insert-only log of
every stage transition a record goes through - FromStatus, ToStatus,
who, when, and any comments/reason - distinct from the general-purpose
Audit_Log (which already records a WORKFLOW_TRANSITION action alongside
every other kind of action, across every module, for compliance/security
auditing per Section 32). The two tables serve different readers: Audit_Log
is the "everything that happened, by anyone, anywhere" compliance trail;
Workflow_History is "this one record's stage journey," meant to be read
back as a single ordered list per Employee_Performance - the natural data
source for a "workflow timeline" UI element, and for M19's own
stage-sequencing/return-routing reference logic.

One row per transition (never updated or deleted, matching Audit_Log's
own insert-only convention).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkflowHistory(Base):
    __tablename__ = "Workflow_History"

    WorkflowHistoryID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)
    FromStatus: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ToStatus: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ActionedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    Comments: Mapped[str | None] = mapped_column(String(500), nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])

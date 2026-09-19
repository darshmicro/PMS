"""
PIP - Performance Improvement Plan (spec Section 4.5 / M21). Unlike every
other transactional table built so far, this one is scoped directly to
`EmployeeID`, not `PerformanceID` - a PIP is not tied to one appraisal
cycle the way Development Plans (M20) or the review/approval chain are;
it can be opened at any time an employee's performance needs formal,
sustained improvement, independent of where they sit in a given cycle's
workflow.

DESIGN NOTE on scope/authority: like Development Plan (M20) before it,
this table has **no row in the spec's own RBAC matrix**. What the spec
does give: Section 7 places "18. PIP management list + PIP form" squarely
under the **HR** screen section (not Manager's, not HOD's), and the
table's own `ManagerID` column names a specific assigned manager for each
PIP - not necessarily read from `Employee.ManagerID`'s org-chart
reporting line, but the person HR has assigned to run this particular
improvement plan (usually the same person, but the schema treats it as
its own field, so this module does too). Reading those together:
creating and closing a PIP is HR's call (plus the broader business-admin
roles - Plant Head, MD, HR Administrator - that hold equivalent authority
elsewhere in this codebase); the assigned manager may view and update the
day-to-day fields (action plan, training, comments) for PIPs they're
personally assigned to, checked against `PIP.ManagerID` directly rather
than `Employee.ManagerID`; the employee who is its subject may view their
own PIP (a matter this consequential shouldn't be invisible to the person
it's about) but never edit it.

DESIGN NOTE on Outcome/lifecycle: `Outcome` is nullable and stays NULL
while a PIP is open/in progress - only a dedicated `/close` action (not a
generic PUT) sets it, to one of `SUCCESSFUL`/`UNSUCCESSFUL`/`EXTENDED`
(see pip_service.py for why this vocabulary, like Development Plan's
CompletionStatus, is inferred rather than read off the DDL). Once set,
the PIP is treated as closed and no longer editable - the one place this
module genuinely has the "lifecycle" the build-order table promises,
unlike Development Plan's open-ended field-level editing.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PIP(Base):
    __tablename__ = "PIP"

    PIPID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=False)

    PerformanceGap: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ExpectedPerformance: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ImprovementTarget: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ActionPlan: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    Training: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ManagerID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    ReviewDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    PIPStartDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    PIPEndDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    Outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)  # NULL = open; see module docstring
    Comments: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[EmployeeID])
    manager: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[ManagerID])

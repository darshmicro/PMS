"""
Manager Review (spec Section 11 continued / M13). One Manager_Review row
per Employee_KPI, mirroring Self_Assessment's shape (M12) but recording the
manager's own evaluation on a separate table rather than overwriting the
employee's - per Section 8.1's "Manager/HOD/HR may override with their own
score + mandatory comments (never silently)", both perspectives must
survive side by side for later stages (HOD/HR/Plant Head/MD) to see.

Workflow note: unlike Self-Assessment's three-state split (M12), the
design doc's diagram (Section 6) gives Manager Review only one status with
two possible exits:

    MANAGER_REVIEW --[manager submits]--> HOD_REVIEW
    MANAGER_REVIEW --[manager returns to employee]--> SELF_ASSESSMENT

There is no diagrammed "manager acknowledges" sub-state the way Self-
Assessment has EMPLOYEE_ACKNOWLEDGED, so this module does not require a
separate acknowledge call before editing - manager_review_service.py's
update endpoint creates a Manager_Review row lazily (get-or-create) on
first edit instead of requiring the record be seeded up front.

Resolves the forward note left in M12's README/model docstring about
Employee_Performance ever needing a generic "RETURNED" status: it does
not. The diagram's labelled return arrows already each name a concrete
target status (MANAGER_REVIEW -> SELF_ASSESSMENT here; HOD_REVIEW ->
MANAGER_REVIEW or -> SELF_ASSESSMENT in M14), which is what this module
actually transitions to - "RETURNED" is only ever a per-row informational
status on Self_Assessments/Manager_Reviews themselves (to distinguish "sent
back for rework" from "never touched"), never a whole-record status. No
change was needed to self_assessment_service.EDITABLE_STATUSES because
SELF_ASSESSMENT was already in that set.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

SUBMIT = "SUBMIT"
RETURN = "RETURN"


class ManagerReview(Base):
    __tablename__ = "Manager_Reviews"
    __table_args__ = (UniqueConstraint("EmployeeKPIID", name="UQ_ManagerReview_EmployeeKPI"),)

    ManagerReviewID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeKPIID: Mapped[int] = mapped_column(ForeignKey("Employee_KPI.EmployeeKPIID"), nullable=False)

    ManagerScore: Mapped[int | None] = mapped_column(nullable=True)  # 1-5
    ManagerComments: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    DevelopmentRequirement: Mapped[str | None] = mapped_column(String(500), nullable=True)

    Action: Mapped[str | None] = mapped_column(String(20), nullable=True)  # SUBMIT, RETURN - set at whole-record transition
    ActionedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    employee_kpi: Mapped["EmployeeKPI"] = relationship("EmployeeKPI", foreign_keys=[EmployeeKPIID])

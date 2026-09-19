"""
Employee Self-Assessment (spec Section 11 / M12). One Self_Assessment row
per Employee_KPI - the employee records what they achieved against that
KPI's target, and the system derives an achievement percentage and a raw
score from the configurable KPI_Scoring_Rules bands (spec Section 8.1),
the same lookup mechanism the manager/HOD/HR stages (M13+) will reuse with
their own Achievement/Score columns on their own review tables.

Workflow note: the design doc's state diagram (Section 6) has three
distinct states between "KPI assigned" and "manager review":

    KPI_ASSIGNED -> EMPLOYEE_ACKNOWLEDGED -> SELF_ASSESSMENT -> MANAGER_REVIEW

This module owns all three transitions:
  - acknowledge():  KPI_ASSIGNED -> EMPLOYEE_ACKNOWLEDGED (seeds one DRAFT
    Self_Assessment row per Employee_KPI)
  - the first edit of any KPI's self-assessment: EMPLOYEE_ACKNOWLEDGED ->
    SELF_ASSESSMENT (idempotent afterward)
  - submit():       SELF_ASSESSMENT -> MANAGER_REVIEW (only once every KPI
    has been assessed)

The diagram's RETURNED state (any later stage sending the record back to
the employee) is out of scope here - it will be wired up by whichever
module (M13 Manager Review onward) is the one doing the returning, at
which point this module's ensure_stage_editable() will need to accept
Status == "RETURNED" too. Documented as a forward note in README_M12.md
rather than guessed at now, since the spec gives no detail yet on how a
returned record's Self_Assessment rows should be marked.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
RETURNED = "RETURNED"


class SelfAssessment(Base):
    __tablename__ = "Self_Assessments"
    __table_args__ = (UniqueConstraint("EmployeeKPIID", name="UQ_SelfAssessment_EmployeeKPI"),)

    SelfAssessmentID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeKPIID: Mapped[int] = mapped_column(ForeignKey("Employee_KPI.EmployeeKPIID"), nullable=False)

    Achievement: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    AchievementPct: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    SelfScore: Mapped[int | None] = mapped_column(nullable=True)  # 1-5
    EmployeeComments: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    DevelopmentNeed: Mapped[str | None] = mapped_column(String(500), nullable=True)

    Status: Mapped[str] = mapped_column(String(20), nullable=False, default=DRAFT)
    SubmittedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    employee_kpi: Mapped["EmployeeKPI"] = relationship("EmployeeKPI", foreign_keys=[EmployeeKPIID])

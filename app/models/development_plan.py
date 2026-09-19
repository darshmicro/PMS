"""
Development_Plans (spec Section 4.5 / M20). One or more rows per
Employee_Performance - unlike every review/approval table built so far,
there is no UniqueConstraint on PerformanceID here: a record can have
several skill gaps, each with its own training/action plan and target
date, tracked independently to completion.

DESIGN NOTE on scope/authority: unlike every prior workflow stage, this
table has **no row in the spec's own RBAC matrix** (Section 5 lists Own
Self-Assessment through Audit Log, but nothing named "Development Plan" -
the same kind of gap M18 found with Employee_Competency). What the spec
does give: a screen list entry for Employees ("9. My Development Plan",
Section 7) implying employees can at least view their own, and both
ManagerReview and HODReview already capture DevelopmentRecommendation/
TrainingRequirement free-text fields during their own review stages
(M13/M14). Reading those together, this module treats Development Plan
authorship as belonging to the same roles that already produce those
recommendations and own assignment-level decisions for a record -
Manager, HOD, HR, Plant Head, MD, HR Administrator - reusing exactly the
ASSIGNMENT.EDIT/.VIEW role split from M11 rather than inventing a new,
narrower one with no textual basis. Employees themselves get View only
(matching the "My Development Plan" screen), never Edit - nothing in the
spec suggests employees author their own development plan, only that
they can see it.

DESIGN NOTE on CompletionStatus's vocabulary: the DDL only gives a
default ('PENDING') and no CHECK constraint, so the spec never actually
enumerates the allowed values. PENDING / IN_PROGRESS / COMPLETED is the
minimum vocabulary that makes "track training completion over time"
(this module's stated purpose per the build-order table) meaningful, and
is applied here as a CHECK constraint (defense in depth) plus a service-
layer validator - flagged explicitly since, unlike every other validated
vocabulary in this codebase (measurement types, workflow statuses, RBAC
actions), this one is inferred rather than read off the DDL/diagram.

DESIGN NOTE on locking: this table is NOT gated by Employee_Performance's
workflow Status or IsLocked flag. A development plan's whole purpose -
tracking a skill gap through to a training TargetDate - routinely
outlives the appraisal cycle that created it (FINAL_APPROVED/LOCKED could
happen weeks before a training TargetDate arrives). Blocking
CompletionStatus updates once the appraisal record locks would break the
one thing this table exists to track, so - unlike every review/approval
stage's own ensure_stage_editable() - there is no lock check here at all.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

PENDING = "PENDING"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
COMPLETION_STATUSES = (PENDING, IN_PROGRESS, COMPLETED)


class DevelopmentPlan(Base):
    __tablename__ = "Development_Plans"

    DevPlanID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)

    DevelopmentArea: Mapped[str | None] = mapped_column(String(200), nullable=True)
    SkillGap: Mapped[str | None] = mapped_column(String(500), nullable=True)
    TrainingRequired: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ActionPlan: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ResponsiblePersonID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    TargetDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    CompletionStatus: Mapped[str] = mapped_column(String(20), nullable=False, default=PENDING)
    ReviewComments: Mapped[str | None] = mapped_column(String(500), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])
    responsible_person: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[ResponsiblePersonID])

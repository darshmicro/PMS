"""
HOD Review (spec Section 11 continued / M14). Unlike Self-Assessment (M12)
and Manager Review (M13), which both keep one row per Employee_KPI,
HOD_Reviews is one row per Employee_Performance - the ER diagram and DDL
(spec Section 3) give HOD a single whole-record HODScore (DECIMAL(6,2), a
percentage) rather than a 1-5 per-KPI score.

DESIGN NOTE on the tension with Section 8.1: that section's narrative says
"Manager/HOD/HR may override with their own score" as if HOD re-scores
each KPI the way Manager does. But the schema HOD_Reviews actually defines
has no per-KPI HOD score - only one aggregate HODScore per record. Since
the schema is what actually gets built and persisted (and the narrative is
describing the *general* override principle, not a literal per-table
requirement), this module follows the schema: HOD reviews the record as a
whole, informed by (not overwriting) the Manager-scored KPIs.

To give HOD something concrete to compare their own score against - and
to preserve the spirit of "never silently" at this coarser grain - the
service layer computes a reference figure using Section 8.2's own weighted
formula (`ManagerScore x KPIWeightage / 5`, summed across every KPI) and
surfaces it as read-only context. If HOD's own HODScore differs from that
reference by more than a small rounding tolerance, HODComments become
mandatory - the same override discipline M13 applies at KPI level, applied
here at record level since that's the grain this table actually offers.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

APPROVE_FORWARD = "APPROVE_FORWARD"
RETURN_TO_MANAGER = "RETURN_TO_MANAGER"
RETURN_TO_EMPLOYEE = "RETURN_TO_EMPLOYEE"


class HODReview(Base):
    __tablename__ = "HOD_Reviews"
    __table_args__ = (UniqueConstraint("PerformanceID", name="UQ_HODReview_Performance"),)

    HODReviewID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)

    HODScore: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    HODComments: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    DevelopmentRecommendation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    TrainingRequirement: Mapped[str | None] = mapped_column(String(500), nullable=True)

    Action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ActionedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])

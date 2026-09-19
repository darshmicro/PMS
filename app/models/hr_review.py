"""
HR Review & Calibration (spec Section 11 continued / M15). One row per
Employee_Performance, like HOD_Reviews (M14) - the ER diagram/DDL give HR
a single whole-record review, not a per-KPI one.

DESIGN NOTE on HRScore vs CalibrationAdjustment: the spec names this stage
"HR Review & Calibration" and Section 8.4's final-score formula explicitly
lists "+ HR Calibration Adjustment, if any, with reason" as something
added on top of the KPI+Competency component sum. Read together with
Section 8.6's rule ("CalibrationAdjustment <> 0 requires non-empty
AdjustmentReason"), the natural reading is that HR's job here is not to
enter an independent score from scratch, but to apply an adjustment to the
score the record already carries from HOD Review - for cross-department
rating-distribution calibration, the stated purpose of this stage. So
HRScore is *derived* (HODScore + CalibrationAdjustment), recomputed by the
service layer whenever the adjustment changes, rather than a value HR
types in directly.

DESIGN NOTE on workflow: unlike every review stage so far, the diagram
gives HR_REVIEW exactly one exit ("HR completes calibration" ->
PLANT_HEAD_APPROVAL) and no return arrow of its own - the RBAC matrix
confirms this: HR Review/Calibration is "C,V,E" for HR, with no
Approve/Return columns the way HOD/Plant Head/MD rows have. A return path
INTO this stage does exist (PLANT_HEAD_APPROVAL -> HR_REVIEW, built in
M16), but that reuses the same HR_REVIEW status value this module already
treats as editable, so - continuing the pattern established in M13/M14 -
no forward-looking change is needed here for that to work once M16 exists.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class HRReview(Base):
    __tablename__ = "HR_Reviews"
    __table_args__ = (UniqueConstraint("PerformanceID", name="UQ_HRReview_Performance"),)

    HRReviewID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)

    HRScore: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    CalibrationAdjustment: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    AdjustmentReason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    HRComments: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    TrainingRecommendation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    CareerDevelopmentRecommendation: Mapped[str | None] = mapped_column(String(500), nullable=True)

    ActionedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])

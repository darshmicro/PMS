"""
Performance_Scores and Performance_Ratings (spec Section 8.4/8.5, M18).
Performance_Scores stores one row per computed component ("KPI_WEIGHTED",
"COMPETENCY_WEIGHTED") plus one "FINAL" row, per Employee_Performance -
an audit trail of how the final figure was reached, independent of the
Employee_Performance.FinalScorePct convenience column it's copied to.

Performance_Ratings is the rating-band lookup result, inserted exactly
once, only at the FINAL_APPROVED transition (spec Section 8.5). Per that
same section, once inserted the row is immutable - "any correction after
LOCKED requires a new audited reopen workflow event ... never an in-place
edit." This module's service layer never updates or deletes an existing
Performance_Ratings row; a UniqueConstraint on PerformanceID enforces
"at most one" at the database level too.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

KPI_WEIGHTED = "KPI_WEIGHTED"
COMPETENCY_WEIGHTED = "COMPETENCY_WEIGHTED"
FINAL = "FINAL"


class PerformanceScore(Base):
    __tablename__ = "Performance_Scores"

    ScoreID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)
    EmployeeKPIID: Mapped[int | None] = mapped_column(ForeignKey("Employee_KPI.EmployeeKPIID"), nullable=True)
    ScoreType: Mapped[str] = mapped_column(String(20), nullable=False)  # KPI_WEIGHTED, COMPETENCY_WEIGHTED, FINAL
    ScoreValue: Mapped[float] = mapped_column(Numeric(9, 4), nullable=False)
    CalculatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])


class PerformanceRating(Base):
    __tablename__ = "Performance_Ratings"
    __table_args__ = (UniqueConstraint("PerformanceID", name="UQ_PerformanceRating_Performance"),)

    PerformanceRatingID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)
    FinalScorePct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    RatingID: Mapped[int] = mapped_column(ForeignKey("Rating_Master.RatingID"), nullable=False)
    FinalizedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])
    rating: Mapped["RatingMaster"] = relationship("RatingMaster", foreign_keys=[RatingID])

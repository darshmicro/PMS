"""
Performance Masters (spec Section 6/7/8/9/12/14/21): Performance Cycle,
KPA, KPI, KPI Scoring Rules, Rating, Competency. These differ from the
org masters (M3) in that several carry real business rules beyond
Add/Edit/View/Activate/Deactivate - date sequencing on a Cycle, weightage
and applicability on KPA/KPI, non-overlapping bands on Scoring Rules and
Rating - so M5-M10's services layer adds validation on top of the same
generic master_service used by M3.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PerformanceCycle(Base):
    """
    Spec Section 9. One row per appraisal year, holding the start/end date
    for every workflow stage. The workflow engine (M19) reads these dates
    to gate which stage is currently open - they are not just informational.
    """
    __tablename__ = "Performance_Cycles"

    CycleID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    CycleName: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # e.g. '2026-27'
    # Added for report search-by-year (CycleName is a free-text unique
    # string, e.g. '2026-27' or 'SAMPLE-2026-27', not reliably parseable) -
    # nullable so it's additive over any cycle created before this column
    # existed; new cycles should always set it going forward.
    Year: Mapped[int | None] = mapped_column(nullable=True)

    KPISettingStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    KPISettingEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    SelfAssessmentStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    SelfAssessmentEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    ManagerReviewStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    ManagerReviewEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    HODReviewStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    HODReviewEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    HRReviewStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    HRReviewEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    PlantHeadApprovalStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    PlantHeadApprovalEnd: Mapped[date | None] = mapped_column(Date, nullable=True)
    MDApprovalStart: Mapped[date | None] = mapped_column(Date, nullable=True)
    MDApprovalEnd: Mapped[date | None] = mapped_column(Date, nullable=True)

    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


class KPAMaster(Base):
    """Spec Section 7."""
    __tablename__ = "KPA_Master"

    KPAID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    KPACode: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    KPAName: Mapped[str] = mapped_column(String(150), nullable=False)
    Description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    DepartmentID: Mapped[int | None] = mapped_column(ForeignKey("Departments.DepartmentID"), nullable=True)
    DesignationID: Mapped[int | None] = mapped_column(ForeignKey("Designations.DesignationID"), nullable=True)
    Category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    DefaultWeightage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    EffectiveFrom: Mapped[date | None] = mapped_column(Date, nullable=True)
    EffectiveTo: Mapped[date | None] = mapped_column(Date, nullable=True)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    department: Mapped["Department | None"] = relationship("Department", foreign_keys=[DepartmentID])
    designation: Mapped["Designation | None"] = relationship("Designation", foreign_keys=[DesignationID])


class KPIMaster(Base):
    """Spec Section 8."""
    __tablename__ = "KPI_Master"

    KPIID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    KPICode: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    KPIName: Mapped[str] = mapped_column(String(150), nullable=False)
    Description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    KPAID: Mapped[int] = mapped_column(ForeignKey("KPA_Master.KPAID"), nullable=False)
    DepartmentID: Mapped[int | None] = mapped_column(ForeignKey("Departments.DepartmentID"), nullable=True)
    DesignationID: Mapped[int | None] = mapped_column(ForeignKey("Designations.DesignationID"), nullable=True)

    # NUMERIC, PERCENTAGE, RATIO, YESNO, DATE, MILESTONE, QTY, COST, REDUCTION, QUALITATIVE
    MeasurementType: Mapped[str] = mapped_column(String(30), nullable=False)
    Unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    TargetType: Mapped[str | None] = mapped_column(String(20), nullable=True)
    DefaultTarget: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    MinimumTarget: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ExpectedTarget: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    StretchTarget: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    Weightage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ScoringMethod: Mapped[str | None] = mapped_column(String(30), nullable=True)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    kpa: Mapped["KPAMaster"] = relationship("KPAMaster", foreign_keys=[KPAID])
    department: Mapped["Department | None"] = relationship("Department", foreign_keys=[DepartmentID])
    designation: Mapped["Designation | None"] = relationship("Designation", foreign_keys=[DesignationID])


MEASUREMENT_TYPES = (
    "NUMERIC", "PERCENTAGE", "RATIO", "YESNO", "DATE", "MILESTONE", "QTY", "COST", "REDUCTION", "QUALITATIVE",
)


class KPIScoringRule(Base):
    """
    Spec Section 12. KPIID=NULL means a global default rule set applied
    when a KPI has no KPI-specific rules of its own (see scoring_service.py).
    """
    __tablename__ = "KPI_Scoring_Rules"

    RuleID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    KPIID: Mapped[int | None] = mapped_column(ForeignKey("KPI_Master.KPIID"), nullable=True)
    MinAchievement: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    MaxAchievement: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    Score: Mapped[int] = mapped_column(nullable=False)  # 1..5
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    kpi: Mapped["KPIMaster | None"] = relationship("KPIMaster", foreign_keys=[KPIID])


class RatingMaster(Base):
    """Spec Section 21."""
    __tablename__ = "Rating_Master"

    RatingID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    RatingLabel: Mapped[str] = mapped_column(String(60), nullable=False)
    MinPercent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    MaxPercent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)


class CompetencyMaster(Base):
    """Spec Section 14."""
    __tablename__ = "Competency_Master"

    CompetencyID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    CompetencyCode: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    CompetencyName: Mapped[str] = mapped_column(String(150), nullable=False)
    Category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    Weightage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

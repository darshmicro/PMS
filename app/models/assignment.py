"""
KPA/KPI Assignment (spec Section 10). One Employee_Performance row per
(employee, cycle) - the appraisal "envelope" that M12-M20 will attach
self-assessment, reviews, scores and approvals to. Employee_KPA groups
the assigned KPIs by KPA for display/rollup; Employee_KPI is the actual
per-employee target/weightage record the spec's field list describes.

DESIGN NOTE on weightage (see assignment_service.py's docstring for the
full reasoning): spec Section 10 states one flat rule - "total KPI
weightage must equal 100%". Employee_KPA.Weightage is therefore treated
as a READ-ONLY rollup (sum of its own Employee_KPI rows), recomputed by
the service layer on every change, not an independently-editable or
independently-validated field. The 100% check applies once, across every
Employee_KPI under the whole Employee_Performance.

DESIGN NOTE on MeasurementType: snapshotted onto Employee_KPI from
KPI_Master at assignment time (not read live via the KPIID FK), so that
a later edit to the KPI Master's measurement type never silently
reinterprets an achievement already recorded against an in-flight or
historical appraisal (spec Section 28/35: "historical approved records
must not be overwritten").
"""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Only the statuses this module can produce/consume; later modules (M12+)
# extend the workflow further using the full vocabulary from spec Section 15.
DRAFT = "DRAFT"
KPI_ASSIGNED = "KPI_ASSIGNED"


class EmployeePerformance(Base):
    __tablename__ = "Employee_Performance"
    __table_args__ = (UniqueConstraint("EmployeeID", "CycleID", name="UQ_EmployeePerformance_Employee_Cycle"),)

    PerformanceID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=False)
    CycleID: Mapped[int] = mapped_column(ForeignKey("Performance_Cycles.CycleID"), nullable=False)
    Status: Mapped[str] = mapped_column(String(30), nullable=False, default=DRAFT)
    TotalWeightage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    FinalScorePct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    FinalRatingID: Mapped[int | None] = mapped_column(ForeignKey("Rating_Master.RatingID"), nullable=True)
    IsLocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[EmployeeID])
    cycle: Mapped["PerformanceCycle"] = relationship("PerformanceCycle", foreign_keys=[CycleID])
    kpas: Mapped[list["EmployeeKPA"]] = relationship(
        "EmployeeKPA", back_populates="performance", cascade="all, delete-orphan"
    )


class EmployeeKPA(Base):
    __tablename__ = "Employee_KPA"
    __table_args__ = (UniqueConstraint("PerformanceID", "KPAID", name="UQ_EmployeeKPA_Performance_KPA"),)

    EmployeeKPAID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)
    KPAID: Mapped[int] = mapped_column(ForeignKey("KPA_Master.KPAID"), nullable=False)
    # Read-only rollup - see module docstring. Never set directly by a request payload.
    Weightage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", back_populates="kpas")
    kpa: Mapped["KPAMaster"] = relationship("KPAMaster", foreign_keys=[KPAID])
    kpis: Mapped[list["EmployeeKPI"]] = relationship(
        "EmployeeKPI", back_populates="employee_kpa", cascade="all, delete-orphan"
    )


class EmployeeKPI(Base):
    __tablename__ = "Employee_KPI"
    __table_args__ = (UniqueConstraint("EmployeeKPAID", "KPIID", name="UQ_EmployeeKPI_EmployeeKPA_KPI"),)

    EmployeeKPIID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeKPAID: Mapped[int] = mapped_column(ForeignKey("Employee_KPA.EmployeeKPAID"), nullable=False)
    KPIID: Mapped[int] = mapped_column(ForeignKey("KPI_Master.KPIID"), nullable=False)
    Description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    Target: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    Unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    MeasurementType: Mapped[str] = mapped_column(String(30), nullable=False)  # snapshot, see module docstring
    Weightage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    DueDate: Mapped[date | None] = mapped_column(Date, nullable=True)
    EvidenceRequired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    employee_kpa: Mapped["EmployeeKPA"] = relationship("EmployeeKPA", back_populates="kpis")
    kpi: Mapped["KPIMaster"] = relationship("KPIMaster", foreign_keys=[KPIID])

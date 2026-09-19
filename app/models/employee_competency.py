"""
Employee Competency (spec Section 14/Section 8.3, ERD lines 144-145). This
table has existed in the design doc's DDL since the ER diagram, but no
module in the M1-M17 build sequence ever created it - M10 (Competency
Master) only built the *master* list of competencies an organization can
assign (`Competency_Master`), and M11 (KPA/KPI Assignment) only covers, as
its own name says, KPA/KPI - never competencies. Section 8.3's formula
("Employee_Competency.Score x Weightage / 5") needs this table to exist,
so M18 (Scoring Engine) creates it now, as the minimum needed to make that
formula computable at all.

DESIGN NOTE (flagged prominently in README_M18.md too): this module
deliberately does NOT build a full assignment/scoring workflow for this
table - no dedicated review stage, no return/approve actions - because
the spec's own module table never allocated one, and inventing workflow
authority rules for a module the user hasn't asked for risks conflicting
with how they'd actually want it designed. What Scoring Engine needs is
narrower: to be able to *read* whatever Employee_Competency rows already
exist for a record and fold them into the weighted calculation, treating
"no competencies assigned" as a valid state (a record's Competency
component is simply 0 in that case) rather than an error. Reusing
ASSIGNMENT.EDIT/VIEW (M11's own permission codes) to gate a minimal
create/list here was considered but is left out for the same reason -
that's a real design decision about who may assign competencies and
when, better made deliberately in its own module than bolted onto this
one's scope.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EmployeeCompetency(Base):
    __tablename__ = "Employee_Competency"

    EmployeeCompetencyID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)
    CompetencyID: Mapped[int] = mapped_column(ForeignKey("Competency_Master.CompetencyID"), nullable=False)
    Weightage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    Score: Mapped[int | None] = mapped_column(nullable=True)  # 1..5, same scale as KPI scores
    Comments: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])
    competency: Mapped["CompetencyMaster"] = relationship("CompetencyMaster", foreign_keys=[CompetencyID])

"""
Plant Head Approval (spec Section 11 continued / M16). Mirrors the
PlantHead_Approvals DDL exactly in shape - ApprovalID, PerformanceID,
Decision, Comments, ActionedAt, ActionedBy - and that shape is the
headline design fact of this module: unlike every review stage before it
(Manager Review/M13, HOD Review/M14, HR Review & Calibration/M15), there
is no score column at all here. The RBAC matrix's own row for this stage
("Plant Head Approval: C,V,A,R" - Create/View/Approve/Return, no Edit)
agrees: Plant Head does not touch the score, they authorize or reject the
record as a whole, based on the HR-calibrated score that already exists
by the time a record reaches PLANT_HEAD_APPROVAL. So this table (and this
module) is a pure decision gate: Decision is APPROVE or RETURN, Comments
is the accompanying note/reason, and that's the entire record.

One row per Employee_Performance (a UniqueConstraint added here, as with
HOD_Reviews/M14 and HR_Reviews/M15, beyond the literal DDL) - the row is
reused/overwritten across repeated approve/return cycles rather than
appending a new row each time, consistent with those two tables.

DESIGN NOTE on scoping: HOD Review scoped by Employee.HODID - a direct
"who is this employee's HOD" foreign key. Plant Head has no equivalent
direct FK; Employee only carries its own PlantID (added in M4). So the
Plant Head ownership check in the service layer compares *plants*, not
people: the acting Plant Head's own Employee.PlantID must match the
reviewed employee's PlantID - "Plant-wide approve/return" (per this
module's own line in the build-order table) is naturally a plant-scoped
check rather than a person-scoped one.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

APPROVE = "APPROVE"
RETURN = "RETURN"


class PlantHeadApproval(Base):
    __tablename__ = "PlantHead_Approvals"
    __table_args__ = (UniqueConstraint("PerformanceID", name="UQ_PlantHeadApproval_Performance"),)

    ApprovalID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)

    Decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    Comments: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    ActionedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])

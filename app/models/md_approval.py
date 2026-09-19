"""
MD Final Approval (spec Section 11 continued / M17). The design doc's DDL
for `MD_Approvals` is structurally identical to `PlantHead_Approvals`
(M16) - ApprovalID, PerformanceID, Decision, Comments, ActionedAt,
ActionedBy - and the same reasoning applies: no score column, because MD
does not re-score anything, they authorize or reject the record as a
whole based on the score it already carries.

What's genuinely new at this stage is that an MD approval is the
workflow's *final* one. The diagram gives two exits from MD_APPROVAL:

    MD_APPROVAL --[MD approves]--> FINAL_APPROVED
    MD_APPROVAL --[MD returns for clarification]--> PLANT_HEAD_APPROVAL

and a further, actor-less arrow straight out of FINAL_APPROVED:

    FINAL_APPROVED --> LOCKED : System locks record

That third arrow has no human decision attached to it ("System locks
record", not "X approves/returns") - it is a mechanical consequence of
reaching FINAL_APPROVED, not a separate workflow stage with its own
table or RBAC row. So this module treats it as immediate: the same
service call that sets Status = FINAL_APPROVED also flips the existing
`Employee_Performance.IsLocked` flag to True in the same transaction,
rather than modelling "LOCKED" as a distinct Status value. IsLocked has
been checked by every stage's `ensure_stage_editable()` since M11, but
this is the first module that actually sets it.

One row per Employee_Performance, reused/overwritten across repeated
approve/return cycles, exactly as PlantHead_Approvals does.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

APPROVE = "APPROVE"
RETURN = "RETURN"


class MDApproval(Base):
    __tablename__ = "MD_Approvals"
    __table_args__ = (UniqueConstraint("PerformanceID", name="UQ_MDApproval_Performance"),)

    ApprovalID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    PerformanceID: Mapped[int] = mapped_column(ForeignKey("Employee_Performance.PerformanceID"), nullable=False)

    Decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    Comments: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    ActionedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ActionedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)

    CreatedAt: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    UpdatedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    performance: Mapped["EmployeePerformance"] = relationship("EmployeePerformance", foreign_keys=[PerformanceID])

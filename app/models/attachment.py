"""
Attachments/Evidence (spec Section 4.5 / M22). The spec's own ER diagram
(Section 3) models only `EMPLOYEE_KPI ||--o{ ATTACHMENTS : "evidence for"` -
matching Section 7's "Self-Assessment form (per KPI, with evidence upload)"
and `Employee_KPI.EvidenceRequired` (M11) - but the DDL (Section 4.5) also
carries a second, nullable `RelatedEmployeeID` FK that never appears in the
ER diagram at all. Flagging this explicitly (the same DDL-vs-narrative gap
this codebase has resolved before, e.g. M14/M15/M18): rather than discard a
field the DDL literally specifies, this module treats it as the
general-purpose case - an attachment scoped directly to an employee rather
than to one specific KPI's evidence (a PIP supporting document, say, which
has no `EmployeeKPIID` to hang off of at all). Exactly one of
`EmployeeKPIID`/`RelatedEmployeeID` is required per row, enforced in the
service layer (`ensure_exactly_one_target`) - a row is either evidence for
a KPI or a general employee-scoped attachment, never both, never neither.

DESIGN NOTE on versioning: `FileVersion` (the DDL's own column) is the only
versioning signal given - no history/superseded-by table, no `IsLatest`
flag. This module keeps every version as its own row (never overwrites
`StoredPath` in place - matching every other insert-only/immutable pattern
already in this codebase: `Audit_Log`, `Performance_Ratings`, `PIP.Outcome`
once closed) and computes the next `FileVersion` as
`max(existing FileVersion for the same logical slot) + 1`, where "the same
logical slot" is `(EmployeeKPIID, RelatedEmployeeID, FileName)` -
re-uploading a file under the same original name against the same KPI/
employee creates version 2, 3, ...; a different `FileName` is a distinct
attachment, versioned independently of any other.

DESIGN NOTE on storage: physical bytes are written under
`settings.FILE_STORAGE_PATH` (declared in M1's config.py but unused until
now - see its own "used by later modules" comment) using a generated,
collision-proof disk filename, never the caller-supplied one, per spec
Section 9's file-upload control list: extension allow-list, size cap,
stored outside web-root, filename sanitization, virus-scan hook point (see
attachment_service.py for each of these). `StoredPath` is that generated
relative path; `FileName` is the original, sanitized, user-facing name
kept for display and download.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Attachment(Base):
    __tablename__ = "Attachments"

    AttachmentID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeKPIID: Mapped[int | None] = mapped_column(ForeignKey("Employee_KPI.EmployeeKPIID"), nullable=True)
    FileName: Mapped[str] = mapped_column(String(255), nullable=False)
    StoredPath: Mapped[str] = mapped_column(String(500), nullable=False)
    UploadedBy: Mapped[int] = mapped_column(ForeignKey("Users.UserID"), nullable=False)
    UploadedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    RelatedEmployeeID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    FileVersion: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    employee_kpi: Mapped["EmployeeKPI | None"] = relationship("EmployeeKPI", foreign_keys=[EmployeeKPIID])
    related_employee: Mapped["Employee | None"] = relationship("Employee", foreign_keys=[RelatedEmployeeID])
    uploaded_by_user: Mapped["User"] = relationship("User", foreign_keys=[UploadedBy])

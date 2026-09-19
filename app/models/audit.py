from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# BIGINT in production (SQL Server) - a high-volume audit table can outgrow
# INT. SQLite (used only by the test suite) only auto-increments a primary
# key declared as exactly INTEGER, not BIGINT, so it gets the narrower type
# there; this affects test storage only, never the SQL Server schema.
_AuditIdType = BigInteger().with_variant(Integer, "sqlite")


class AuditLog(Base):
    """
    Insert-only audit trail (spec Section 32). The application's DB login
    must be granted INSERT + SELECT only on this table - no UPDATE/DELETE -
    enforced at the SQL Server grant level (see sql/001_..._tables.sql).
    """
    __tablename__ = "Audit_Log"

    AuditID: Mapped[int] = mapped_column(_AuditIdType, primary_key=True, autoincrement=True)
    UserID: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ADUsername: Mapped[str | None] = mapped_column(String(100), nullable=True)
    EmployeeID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    Action: Mapped[str] = mapped_column(String(30), nullable=False)
    Module: Mapped[str] = mapped_column(String(60), nullable=False)
    RecordID: Mapped[str | None] = mapped_column(String(50), nullable=True)
    OldValue: Mapped[str | None] = mapped_column(Text, nullable=True)
    NewValue: Mapped[str | None] = mapped_column(Text, nullable=True)
    Reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ActionedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    IPAddress: Mapped[str | None] = mapped_column(String(45), nullable=True)

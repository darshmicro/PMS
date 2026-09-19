"""
Notifications (spec Section 4.5/7 / M23). See notification_service.py's
docstring for the retrofit strategy (stage-based triggers hung off M19's
existing record_transition() call sites) and the visibility design note
(every role, self-scoped only - Section 7's "Notifications panel" is a
Common screen, not a role-tiered one the way every other screen in that
list is).
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Notification(Base):
    __tablename__ = "Notifications"

    NotificationID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    EmployeeID: Mapped[int] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=False)
    Message: Mapped[str] = mapped_column(String(500), nullable=False)
    Module: Mapped[str | None] = mapped_column(String(60), nullable=True)
    IsRead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    employee: Mapped["Employee"] = relationship("Employee", foreign_keys=[EmployeeID])

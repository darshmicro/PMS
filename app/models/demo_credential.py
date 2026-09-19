"""
Demo_Login (demo-only, added for the Windows 11 Home / no-AD local demo
deployment - NOT part of the M1-M28 production build). See
demo_auth_service.py's docstring for the full reasoning and, critically,
the ENVIRONMENT=production guard that stops this path from ever being
reachable in a real deployment.

One row per User with a demo password set, holding a salted bcrypt hash
(passlib) - never the plaintext password, and never logged or returned by
any endpoint.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DemoCredential(Base):
    __tablename__ = "Demo_Login"

    DemoCredentialID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    UserID: Mapped[int] = mapped_column(ForeignKey("Users.UserID"), nullable=False, unique=True)
    PasswordHash: Mapped[str] = mapped_column(String(255), nullable=False)
    UpdatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[UserID])

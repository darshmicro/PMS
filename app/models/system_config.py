"""
System_Config (spec Section 5/7 row 545 / M28: "System Configuration -
SMTP, AD server, storage path"; screen #37). App-wide, non-secret
operational settings, editable by System Administrator only - the final
row in the whole RBAC matrix, and the only row where every other role
(including MD and HR Administrator, who otherwise get near-org-wide reach
everywhere else) is flatly "X". Section 3-4's own note makes the reason
explicit: "System Administrator is a distinct technical role with no
business approval rights" - and the mirror image is also true here: no
business role has system-configuration rights either.

DESIGN NOTE on "SMTP, AD server, storage path" vs. real secrets: the
spec's own Section 33/42 principle (already the header comment on
app/core/config.py) is that "all environment-specific values (DB, AD,
secrets) come from environment variables / .env - never hard-coded."
Taking the matrix row literally and building an editable DB-backed screen
for *every* Settings field would mean storing DB_PASSWORD/AD_BIND_PASSWORD/
SESSION_SECRET_KEY in a table any System Administrator with DB access can
read in plaintext - a direct contradiction of that principle, and a real
security regression this module must not introduce. Resolved by scoping
System_Config to exactly the non-secret subset the matrix row itself
names by example (SMTP relay host/port/from-address, AD server/domain,
file storage path, upload size limit) - see system_config_service.py's
NON_SECRET_KEYS allowlist - and rejecting any attempt to store a
credential-shaped key outright, rather than silently accepting it.

One row per named setting (key/value), not one column per setting, so
that new settings can be added without a migration - matching this
codebase's existing preference for extensibility over rigid schema
(compare Attachment's dual-nullable-FK design, M22).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SystemConfig(Base):
    __tablename__ = "System_Config"

    ConfigID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ConfigKey: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    ConfigValue: Mapped[str | None] = mapped_column(String(500), nullable=True)
    Description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ModifiedBy: Mapped[int | None] = mapped_column(ForeignKey("Users.UserID"), nullable=True)
    ModifiedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )

    modified_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[ModifiedBy])

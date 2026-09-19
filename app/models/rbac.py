from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(Base):
    __tablename__ = "Roles"

    RoleID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    RoleCode: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    RoleName: Mapped[str] = mapped_column(String(100), nullable=False)
    # Distinguishes Plant Head/MD/HR (business approval authority) from
    # System Administrator (technical-only, no approval rights) - spec Sec 3/4.
    IsBusinessRole: Mapped[bool] = mapped_column(default=True, nullable=False)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "Permissions"

    PermissionID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # e.g. "KPI_MASTER.EDIT", "HOD_REVIEW.APPROVE", "EXPORT.HR_REVIEW"
    PermissionCode: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    Module: Mapped[str] = mapped_column(String(60), nullable=False)
    Description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(back_populates="permission")


class RolePermission(Base):
    __tablename__ = "Role_Permissions"

    RoleID: Mapped[int] = mapped_column(ForeignKey("Roles.RoleID"), primary_key=True)
    PermissionID: Mapped[int] = mapped_column(ForeignKey("Permissions.PermissionID"), primary_key=True)

    role: Mapped["Role"] = relationship(back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")


class User(Base):
    __tablename__ = "Users"

    UserID: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ADUsername: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    EmployeeID: Mapped[int | None] = mapped_column(ForeignKey("Employees.EmployeeID"), nullable=True)
    IsActive: Mapped[bool] = mapped_column(default=True, nullable=False)
    LastLoginAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    employee: Mapped["Employee | None"] = relationship("Employee", back_populates="user")
    user_roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "User_Roles"
    __table_args__ = (UniqueConstraint("UserID", "RoleID", name="UQ_UserRole"),)

    UserID: Mapped[int] = mapped_column(ForeignKey("Users.UserID"), primary_key=True)
    RoleID: Mapped[int] = mapped_column(ForeignKey("Roles.RoleID"), primary_key=True)

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="user_roles")

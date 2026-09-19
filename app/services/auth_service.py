"""
Implements the mapping chain from spec Section 5:
DOMAIN\\username -> AD auth -> Users table -> Employee -> Department/Manager/HOD -> Roles -> Dashboard
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.rbac import Role, User
from app.services.profile_service import company_logo_url, employee_photo_url


class LoginError(Exception):
    pass


@dataclass
class AuthenticatedContext:
    user_id: int
    ad_username: str
    employee_id: int | None
    employee_name: str | None
    manager_id: int | None
    hod_id: int | None
    photo_url: str | None = None
    company_logo_url: str | None = None
    role_codes: list[str] = field(default_factory=list)
    is_business_role: bool = False


def resolve_user_context(db: Session, ad_username: str) -> AuthenticatedContext:
    """
    Step 3-7 of the AD mapping chain: look up the Users row for this AD
    username, ensure it (and its linked Employee) are active, load roles.
    Raises LoginError with a message safe to show the user - never leaks
    internal detail (spec Section 45).
    """
    user = db.query(User).filter(User.ADUsername == ad_username).one_or_none()
    if user is None:
        raise LoginError(
            "Your Windows account is not yet mapped to an employee record. "
            "Please contact your HR Administrator."
        )
    if not user.IsActive:
        raise LoginError("Your access has been deactivated. Please contact your HR Administrator.")

    employee = None
    if user.EmployeeID is not None:
        employee = db.get(Employee, user.EmployeeID)
        if employee is not None and not employee.IsActive:
            raise LoginError("Your employee record is inactive. Please contact HR.")

    role_codes = [ur.role.RoleCode for ur in user.user_roles if ur.role.IsActive]
    if not role_codes:
        raise LoginError("Your account has no active role assigned. Please contact your HR Administrator.")

    is_business_role = any(
        ur.role.IsBusinessRole for ur in user.user_roles if ur.role.IsActive
    )

    user.LastLoginAt = datetime.now(timezone.utc)
    db.commit()

    return AuthenticatedContext(
        user_id=user.UserID,
        ad_username=user.ADUsername,
        employee_id=employee.EmployeeID if employee else None,
        employee_name=employee.FullName if employee else None,
        manager_id=employee.ManagerID if employee else None,
        hod_id=employee.HODID if employee else None,
        photo_url=employee_photo_url(employee),
        company_logo_url=company_logo_url(employee.plant.company) if employee and employee.plant else None,
        role_codes=role_codes,
        is_business_role=is_business_role,
    )


def default_dashboard_route(role_codes: list[str]) -> str:
    """Highest-privilege role present determines the landing dashboard (Sec 5 diagram)."""
    priority = ["MD", "PLANT_HEAD", "HR_ADMIN", "HR", "HOD", "MANAGER", "EMPLOYEE", "SYS_ADMIN"]
    for role in priority:
        if role in role_codes:
            return f"/dashboard/{role.lower()}"
    return "/dashboard/employee"

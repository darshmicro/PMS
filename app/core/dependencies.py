"""
Every protected route in every module depends on `get_current_context` (who
is calling) and, where the route changes or discloses data, `require_permission`
(are they allowed to). Authorization is enforced here at the server, never
trusted from the client, even though the UI also hides buttons the user
can't use (spec Section 33: "server-side authorization checks").
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.session import SESSION_COOKIE_NAME, read_session_token
from app.db.base import get_db
from app.models.rbac import Permission, Role, RolePermission, User


@dataclass
class CurrentContext:
    user_id: int
    ad_username: str
    employee_id: int | None
    role_codes: list[str]
    permission_codes: set[str]


def get_current_context(request: Request, db: Session = Depends(get_db)) -> CurrentContext:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = read_session_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Session expired, please log in again")

    user = db.get(User, user_id)
    if user is None or not user.IsActive:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account is not active")

    active_roles = [ur.role for ur in user.user_roles if ur.role.IsActive]
    role_codes = [r.RoleCode for r in active_roles]

    permission_codes: set[str] = set()
    if active_roles:
        role_ids = [r.RoleID for r in active_roles]
        rows = (
            db.query(Permission.PermissionCode)
            .join(RolePermission, RolePermission.PermissionID == Permission.PermissionID)
            .filter(RolePermission.RoleID.in_(role_ids))
            .all()
        )
        permission_codes = {code for (code,) in rows}

    return CurrentContext(
        user_id=user.UserID,
        ad_username=user.ADUsername,
        employee_id=user.EmployeeID,
        role_codes=role_codes,
        permission_codes=permission_codes,
    )


def require_permission(permission_code: str):
    """
    Route dependency factory: usage `Depends(require_permission("KPI_MASTER.EDIT"))`.
    Raises 403 if the current user's roles don't grant this permission.
    """
    def _check(ctx: CurrentContext = Depends(get_current_context)) -> CurrentContext:
        if permission_code not in ctx.permission_codes:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return ctx

    return _check


def require_any_permission(*permission_codes: str):
    """
    Route dependency factory for an endpoint two different roles reach
    under two different permissions (e.g. Manager/HR's ASSIGNMENT.EDIT and
    Employee's own-record ASSIGNMENT.PROPOSE both landing on the same
    POST /assignments/{id}/kpas route) - `require_permission` only ever
    checks one code. Raises 403 if none of the given codes are granted.
    """
    def _check(ctx: CurrentContext = Depends(get_current_context)) -> CurrentContext:
        if not set(permission_codes) & ctx.permission_codes:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return ctx

    return _check


def require_any_role(*role_codes: str):
    """Route dependency factory for role-gated pages (e.g. admin screens)."""
    def _check(ctx: CurrentContext = Depends(get_current_context)) -> CurrentContext:
        if not set(role_codes) & set(ctx.role_codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access restricted to specific roles.")
        return ctx

    return _check

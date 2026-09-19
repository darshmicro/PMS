"""
Backend for the "AD Username <-> Employee <-> Role" admin screen (spec
Section 5). Originally restricted to HR Administrator and System
Administrator; widened at the user's explicit request so HR and Plant
Head can also create logins and (re)assign roles - including promoting
someone to PLANT_HEAD or MD - since this system's day-to-day user
administration (new joiners, role changes) is done by HR/Plant Head, not
a dedicated admin team. This remains one of the most sensitive screens in
the system, so every change is still fully audited (write_audit calls
below) regardless of which of these four roles made it.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_any_role
from app.db.base import get_db
from app.models.employee import Employee
from app.models.rbac import Role, User, UserRole
from app.schemas.rbac import UserAdminCreate, UserAdminOut, UserAdminUpdate
from app.services.audit_service import write_audit
from app.services.profile_service import employee_photo_url

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

ADMIN_ROLES = ("HR_ADMIN", "SYS_ADMIN", "HR", "PLANT_HEAD")


def _to_out(user: User) -> UserAdminOut:
    return UserAdminOut(
        user_id=user.UserID,
        ad_username=user.ADUsername,
        employee_id=user.EmployeeID,
        employee_name=user.employee.FullName if user.employee else None,
        employee_photo_url=employee_photo_url(user.employee),
        role_codes=[ur.role.RoleCode for ur in user.user_roles],
        is_active=user.IsActive,
    )


@router.get("", response_model=list[UserAdminOut])
def list_users(
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES)),
):
    users = db.query(User).all()
    return [_to_out(u) for u in users]


@router.post("", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user_mapping(
    payload: UserAdminCreate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES)),
):
    existing = db.query(User).filter(User.ADUsername == payload.ad_username).one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This AD username is already mapped")

    if payload.employee_id is not None and db.get(Employee, payload.employee_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Employee not found")

    roles = db.query(Role).filter(Role.RoleCode.in_(payload.role_codes)).all()
    if len(roles) != len(set(payload.role_codes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="One or more role codes are invalid")

    user = User(ADUsername=payload.ad_username, EmployeeID=payload.employee_id, IsActive=payload.is_active)
    db.add(user)
    db.flush()  # get UserID before creating UserRole rows

    for role in roles:
        db.add(UserRole(UserID=user.UserID, RoleID=role.RoleID))
    db.commit()

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="CREATE",
        module="USER_MANAGEMENT",
        record_id=str(user.UserID),
        new_value=f"ADUsername={payload.ad_username}, roles={payload.role_codes}, active={payload.is_active}",
        ip_address=request.client.host if request.client else None,
    )

    db.refresh(user)
    return _to_out(user)


@router.put("/{user_id}", response_model=UserAdminOut)
def update_user_mapping(
    user_id: int,
    payload: UserAdminUpdate,
    request: Request,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES)),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User mapping not found")

    old_value = (
        f"employee_id={user.EmployeeID}, roles={[ur.role.RoleCode for ur in user.user_roles]}, "
        f"active={user.IsActive}"
    )

    if payload.employee_id is not None:
        if db.get(Employee, payload.employee_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Employee not found")
        user.EmployeeID = payload.employee_id

    if payload.role_codes is not None:
        roles = db.query(Role).filter(Role.RoleCode.in_(payload.role_codes)).all()
        if len(roles) != len(set(payload.role_codes)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="One or more role codes are invalid")
        db.query(UserRole).filter(UserRole.UserID == user.UserID).delete()
        for role in roles:
            db.add(UserRole(UserID=user.UserID, RoleID=role.RoleID))

    if payload.is_active is not None:
        user.IsActive = payload.is_active

    db.commit()
    db.refresh(user)

    new_value = (
        f"employee_id={user.EmployeeID}, roles={[ur.role.RoleCode for ur in user.user_roles]}, "
        f"active={user.IsActive}"
    )

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="EDIT",
        module="USER_MANAGEMENT",
        record_id=str(user.UserID),
        old_value=old_value,
        new_value=new_value,
        reason=payload.reason,
        ip_address=request.client.host if request.client else None,
    )

    return _to_out(user)

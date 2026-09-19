"""
Role & Permission Management (spec Section 40 admin menu). Lets HR
Administrator / System Administrator configure which permissions each
of the 8 roles carries, rather than hard-coding permissions per role in
code - so a future role-permission change is a data change, not a
deployment (consistent with the configurable-workflow principle in Sec 41).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentContext, require_any_role
from app.db.base import get_db
from app.models.rbac import Permission, Role, RolePermission
from app.schemas.rbac import AssignRolePermissionsRequest, PermissionOut, RoleOut
from app.services.audit_service import write_audit

router = APIRouter(prefix="/admin/roles", tags=["admin-roles"])

ADMIN_ROLES = ("HR_ADMIN", "SYS_ADMIN")


@router.get("", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES))):
    roles = db.query(Role).all()
    return [
        RoleOut(
            role_id=r.RoleID, role_code=r.RoleCode, role_name=r.RoleName,
            is_business_role=r.IsBusinessRole, is_active=r.IsActive,
        )
        for r in roles
    ]


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES))):
    perms = db.query(Permission).all()
    return [
        PermissionOut(
            permission_id=p.PermissionID, permission_code=p.PermissionCode,
            module=p.Module, description=p.Description,
        )
        for p in perms
    ]


@router.get("/{role_id}/permissions", response_model=list[PermissionOut])
def get_role_permissions(
    role_id: int, db: Session = Depends(get_db), ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES))
):
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")
    return [
        PermissionOut(
            permission_id=rp.permission.PermissionID,
            permission_code=rp.permission.PermissionCode,
            module=rp.permission.Module,
            description=rp.permission.Description,
        )
        for rp in role.role_permissions
    ]


@router.put("/{role_id}/permissions")
def set_role_permissions(
    role_id: int,
    payload: AssignRolePermissionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    ctx: CurrentContext = Depends(require_any_role(*ADMIN_ROLES)),
):
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Role not found")

    perms = db.query(Permission).filter(Permission.PermissionCode.in_(payload.permission_codes)).all()
    if len(perms) != len(set(payload.permission_codes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="One or more permission codes are invalid")

    old_codes = [rp.permission.PermissionCode for rp in role.role_permissions]

    db.query(RolePermission).filter(RolePermission.RoleID == role_id).delete()
    for perm in perms:
        db.add(RolePermission(RoleID=role_id, PermissionID=perm.PermissionID))
    db.commit()

    write_audit(
        db,
        user_id=ctx.user_id,
        ad_username=ctx.ad_username,
        employee_id=ctx.employee_id,
        action="EDIT",
        module="ROLE_PERMISSIONS",
        record_id=str(role_id),
        old_value=str(old_codes),
        new_value=str(payload.permission_codes),
        reason="Role permission set updated via admin screen",
        ip_address=request.client.host if request.client else None,
    )

    return {"detail": f"Permissions updated for role {role.RoleCode}"}

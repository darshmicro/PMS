from app.models.rbac import Permission, RolePermission, User


def _permission_codes_for(db_session, user: User) -> set[str]:
    """Mirrors the permission-resolution logic in core/dependencies.get_current_context,
    isolated here so it's testable without a live HTTP request."""
    active_roles = [ur.role for ur in user.user_roles if ur.role.IsActive]
    if not active_roles:
        return set()
    role_ids = [r.RoleID for r in active_roles]
    rows = (
        db_session.query(Permission.PermissionCode)
        .join(RolePermission, RolePermission.PermissionID == Permission.PermissionID)
        .filter(RolePermission.RoleID.in_(role_ids))
        .all()
    )
    return {code for (code,) in rows}


def test_hod_role_grants_masters_view_and_edit(seeded_db):
    user = seeded_db.query(User).filter(User.ADUsername == "COMPANY\\active_user").one()
    codes = _permission_codes_for(seeded_db, user)
    assert "MASTERS.VIEW" in codes
    assert "MASTERS.EDIT" in codes


def test_user_with_no_roles_has_no_permissions(seeded_db):
    user = seeded_db.query(User).filter(User.ADUsername == "COMPANY\\no_role_user").one()
    codes = _permission_codes_for(seeded_db, user)
    assert codes == set()

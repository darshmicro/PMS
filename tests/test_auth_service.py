import pytest

from app.services.auth_service import LoginError, default_dashboard_route, resolve_user_context


def test_valid_ad_user_with_active_employee_and_role_resolves(seeded_db):
    ctx = resolve_user_context(seeded_db, "COMPANY\\active_user")
    assert ctx.ad_username == "COMPANY\\active_user"
    assert ctx.employee_name == "Active User"
    assert ctx.role_codes == ["HOD"]


def test_unmapped_ad_username_is_rejected(seeded_db):
    with pytest.raises(LoginError, match="not yet mapped"):
        resolve_user_context(seeded_db, "COMPANY\\nobody")


def test_deactivated_user_account_is_rejected(seeded_db):
    with pytest.raises(LoginError, match="deactivated"):
        resolve_user_context(seeded_db, "COMPANY\\deactivated_account")


def test_inactive_employee_is_rejected_even_if_user_account_active(seeded_db):
    with pytest.raises(LoginError, match="inactive"):
        resolve_user_context(seeded_db, "COMPANY\\inactive_user")


def test_user_with_no_active_role_is_rejected(seeded_db):
    with pytest.raises(LoginError, match="no active role"):
        resolve_user_context(seeded_db, "COMPANY\\no_role_user")


def test_dashboard_route_prioritizes_highest_privilege_role():
    assert default_dashboard_route(["EMPLOYEE", "MD"]) == "/dashboard/md"
    assert default_dashboard_route(["EMPLOYEE"]) == "/dashboard/employee"
    assert default_dashboard_route([]) == "/dashboard/employee"

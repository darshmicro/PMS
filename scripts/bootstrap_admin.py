#!/usr/bin/env python3
"""
Interactive first-admin bootstrap for a brand-new PMS database.

THE GAP THIS CLOSES: every user/role mapping after the very first one is
created through POST /admin/users, which itself requires the caller to
already hold HR_ADMIN or SYS_ADMIN. On a brand-new database nobody can
reach that screen - this script creates exactly one System Administrator
by hand, directly against the same tables POST /admin/users writes to,
so the very first login has a way in.

This replaces hand-editing sql/040_bootstrap_first_admin.sql (AD-mapped
admin, no password - AD or the login form's AD check verifies it) and
sql/demo_only/042_bootstrap_first_admin_demo_local.sql (local admin with
a WELL-KNOWN hardcoded demo password you'd have to remember to change).
This script does both, safely:
  - "ad"    mode never touches or asks for a password at all - the
    identity is verified by AD (ldap_bind/hybrid) or IIS (iis_forwarded)
    at login time, never by this script.
  - "local" mode prompts for a real password with getpass (never echoed,
    never logged, never written to disk by this script) and hashes it
    with the exact same passlib/bcrypt scheme app/services/
    demo_auth_service.py uses at login - not a hardcoded hash pasted into
    a SQL file.

Usage (from the app directory, with the venv active and .env configured -
same environment `uvicorn app.main:app` itself would run in):

    python scripts/bootstrap_admin.py

Safe to re-run: if the username you enter already exists, it offers to
just (re)confirm the SYS_ADMIN role grant (and, for "local" mode, reset
the password) rather than failing or creating a duplicate.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.base import get_session_factory  # noqa: E402
from app.models.rbac import Role, User, UserRole  # noqa: E402
from app.services import demo_auth_service  # noqa: E402
from app.services.ad_service import _normalize_username  # noqa: E402


def _prompt(prompt: str) -> str:
    value = input(prompt).strip()
    if not value:
        print("This value is required.")
        return _prompt(prompt)
    return value


def _prompt_password() -> str:
    while True:
        pw1 = getpass.getpass("New password (min 8 characters, not shown): ")
        if len(pw1) < 8:
            print("Password must be at least 8 characters. Try again.\n")
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 != pw2:
            print("Passwords did not match. Try again.\n")
            continue
        return pw1


def main() -> None:
    print("=" * 70)
    print("PMS - First Admin Bootstrap")
    print("=" * 70)
    print(
        "\nThis creates ONE System Administrator (SYS_ADMIN) login so you can\n"
        "sign in for the first time and create every other user from the\n"
        "app's own Users & Roles screen. Run this once per new database.\n"
    )

    print("How will this first admin log in?")
    print("  1) An Active Directory account (recommended if you have AD reachable -")
    print("     AUTH_MODE=ldap_bind, hybrid, or iis_forwarded)")
    print("  2) A local, non-AD account (AUTH_MODE=demo_local or hybrid only)")
    choice = ""
    while choice not in ("1", "2"):
        choice = input("Enter 1 or 2: ").strip()

    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        sys_admin_role = db.query(Role).filter(Role.RoleCode == "SYS_ADMIN").one_or_none()
        if sys_admin_role is None:
            print(
                "\nERROR: the SYS_ADMIN role was not found. Run the database setup\n"
                "scripts (000_FULL_DATABASE_SETUP.sql, or 001-041 in order) first."
            )
            sys.exit(1)

        if choice == "1":
            raw_username = _prompt("\nAD username (DOMAIN\\username form, e.g. COMPANY\\jdoe): ")
            username = _normalize_username(raw_username)
            existing = db.query(User).filter(User.ADUsername == username).one_or_none()
            if existing is None:
                user = User(ADUsername=username, EmployeeID=None, IsActive=True)
                db.add(user)
                db.flush()
                print(f"\nCreated new user mapping for {username}.")
            else:
                user = existing
                user.IsActive = True
                print(f"\n{username} already exists - ensuring it is active and holds SYS_ADMIN.")

        else:
            username = _prompt("\nLocal username (any label you like, e.g. LOCAL\\sysadmin or svc_admin): ")
            existing = db.query(User).filter(User.ADUsername == username).one_or_none()
            if existing is None:
                user = User(ADUsername=username, EmployeeID=None, IsActive=True)
                db.add(user)
                db.flush()
                print(f"\nCreated new local user {username}.")
            else:
                user = existing
                user.IsActive = True
                print(f"\n{username} already exists - you can reset its password below.")

            password = _prompt_password()
            demo_auth_service.set_password(db, user.UserID, password)
            print("Password set.")

        already_has_role = (
            db.query(UserRole)
            .filter(UserRole.UserID == user.UserID, UserRole.RoleID == sys_admin_role.RoleID)
            .one_or_none()
        )
        if already_has_role is None:
            db.add(UserRole(UserID=user.UserID, RoleID=sys_admin_role.RoleID))
        db.commit()

        print("\n" + "=" * 70)
        print(f"Done. {username} now holds SYS_ADMIN and can log in.")
        if choice == "1":
            print(
                "Next: log in as this user at /app/login.html (their real AD password\n"
                "is verified live by AD/IIS - this script never touched it), confirm\n"
                "GET /auth/me shows SYS_ADMIN, then create every other user from the\n"
                "Users & Roles screen."
            )
        else:
            print(
                "Next: log in as this user at /app/login.html with the password you\n"
                "just set, confirm GET /auth/me shows SYS_ADMIN, then create every\n"
                "other user from the Users & Roles screen. Consider changing this\n"
                "password again via 'My Profile' -> account settings once you're in,\n"
                "if anyone else was present while you typed it."
            )
        print("=" * 70)
    finally:
        db.close()


if __name__ == "__main__":
    main()
